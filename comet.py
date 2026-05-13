import sys
import asyncio
import logging
from uuid import UUID
from bleak import BleakClient, BleakGATTCharacteristic

"""
Control EXOGAL Comet DACs
"""

__version__ = "0.0.1"

__all__ = ["Comet"]

class Comet:
    _debug: bool = False
    logger = logging.getLogger(__name__)

    # commands
    Q_STATUS: str = "CMDS:01"
    Q_VERSION: str = "CMDS:02"

    # buttons
    Q_MUTE_TOGGLE: str = "BTNS:08"
    Q_INPUT_SWITCH: str = "BTNS:10"
    Q_OUTPUT_SWITCH: str = "BTNS:20"
    Q_VOLUME_INC: str = "BTNS:30"
    Q_VOLUME_DEC: str = "BTNS:31"
    Q_POWER_OFF: str = "BTNS:40"
    Q_POWER_ON: str = "BTNS:41"
    Q_POWER_TOGGLE: str = "BTNS:42"

    # display/set TODO: localise the display part
    SAMPLINGS: list[str] = ["NOCLK", "NOPLL", "192K", "176.4K", "96K",
                            "88.2K", "48K", "44.1K", "384K", "352.8K", "DSD"]
    INPUTS: list[str] = ["AES", "SPDIF", "TOSLINK", "ANALOG", "USB", "EXONET",
                         "AIR", "TUNER", "UNKNOWN"]
    OUTPUTS: list[str] = ["MAIN", "HEAD", "EXONET", "UNKNOWN"]
    MUTES: list[str] = ["UNMUTED", "MUTED", "REDUCED"]
    POWERS: list[str] = ["UNKNOWN", "ON", "OFF"]


    def __init__(self, comet_addr: UUID | str, debug: bool = False):
        self.comet_addr: UUID | str  = comet_addr
        self._debug = debug
        if debug:
            handler = logging.StreamHandler(sys.stderr)
            handler.setLevel(logging.DEBUG)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)

        self.characteristic: BleakGATTCharacteristic = None
        self.client: BleakClient = None
        self.firmware_version: str = None
        self.fpga_version: str = None
        self.power_status: int = 0
        self.muted_status: int = 0
        self.current_input: int = 0
        self.current_output: int = 0
        self.sampling_status: int = 0
        self.volume: int = 0

    async def __aenter__(self) -> Comet:
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.disconnect()

    def __process_callback(self, sender: BleakGATTCharacteristic,
                           raw_buffer: bytearray) -> None:
        buf = str(raw_buffer, 'utf-8')
        if self._debug:
            self.logger.debug(f"Processing Buffer from {sender}")
        else:
            self.logger.debug(f"NOT IN DEBUG MODE")
        # check length of the reply
        if len(buf) == 18:
            if self._debug:
                self.logger.debug(f"-> {buf[0:4]}")
            if buf.startswith("RP01:"):
                self.volume = int(buf[5:8])
                self.power_status = 1 if buf[8] == "1" else 2
                self.muted_status = int(buf[9])
                self.sampling_status = int(buf[10])
                if self.sampling_status >= len(self.SAMPLINGS):
                    self.sampling_status = 0
                self.current_input = int(buf[11])
                self.current_output = int(buf[14])
                if self._debug:
                    self.logger.debug(f"UNKNOWN[12] -> [{bytes(buf[12], 'utf-8')[0]:02x}]")
                    self.logger.debug(f"UNKNOWN[13] -> [{bytes(buf[13], 'utf-8')[0]:02x}]")
                    self.logger.debug(f"UNKNOWN[15] -> [{bytes(buf[12], 'utf-8')[0]:02x}]")
                    self.logger.debug(f"UNKNOWN[16] -> [{bytes(buf[13], 'utf-8')[0]:02x}]")
                    self.logger.debug(f"UNKNOWN[17] -> [{bytes(buf[12], 'utf-8')[0]:02x}]")
            elif buf.startswith("RP02:"):
                self.firmware_version = buf[5:11]
                self.fpga_version = buf[11:17]
            else:
                if self._debug:
                    self.logger.debug(f"Processing -> Unrecognized")


    async def __send_command(self, command: str, delay: float = 0.05) -> None:
        if self._debug:
            self.logger.debug(f"Sending command [{command}]")
        if self.client is None or self.client.is_connected == False:
            await self.connect()
        # We reset power status to ensure new values will be populated
        self.power_status = 0
        await self.client.write_gatt_char(self.characteristic,
                                          bytearray("" + command + "\r",
                                                    encoding="utf-8"))
        await asyncio.sleep(delay)


    async def connect(self) -> BleakClient:
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:
                # If there was an exception, good riddance!
                pass
        self.client = BleakClient(self.comet_addr)
        await self.client.connect()
        self.characteristic = \
            list(self.client.services.characteristics.values())[0]
        if self._debug:
            self.logger.debug(f"Connected to {self.comet_addr}, characteristic: {self.characteristic}")
        await self.client.start_notify(self.characteristic,
                                       self.__process_callback)
        return self.client

    async def disconnect(self) -> None:
        if self.client is not None:
            await self.client.stop_notify(self.characteristic)
            await self.client.disconnect()

    async def get_status(self) -> None:
        await self.__send_command(self.Q_STATUS)

    async def get_firmware_version(self) -> None:
        await self.__send_command(self.Q_VERSION)

    async def increase_volume(self) -> None:
        await self.__send_command(self.Q_VOLUME_INC)

    async def decrease_volume(self) -> None:
        await self.__send_command(self.Q_VOLUME_DEC)

    async def set_volume(self, volume: float) -> None:
        max_loop: int = 100
        target_volume = round(volume * 2)
        if target_volume < 0:
            target_volume = 0
        elif target_volume > 200:
            target_volume = 200
        loop_idx = 0
        while self.power_status == 0 and loop_idx < max_loop:
            loop_idx += 1
            await self.get_status()

        if self.power_status != 0:
            while self.volume != target_volume:
                if self.volume < target_volume:
                    await self.__send_command(self.Q_VOLUME_INC, 0)
                else:
                    await self.__send_command(self.Q_VOLUME_DEC)
                loop_idx = 0
                while self.power_status == 0 and loop_idx < max_loop:
                    await asyncio.sleep(0.005)
                if self._debug:
                    self.logger.debug(f"Current Volume [{self.volume / 2:g}]")

    async def toggle_mute(self) -> None:
        await self.__send_command(self.Q_MUTE_TOGGLE)

    async def toggle_input(self) -> None:
        await self.__send_command(self.Q_INPUT_SWITCH)

    async def toggle_output(self) -> None:
        await self.__send_command(self.Q_OUTPUT_SWITCH)

    async def toggle_power(self) -> None:
        await self.__send_command(self.Q_POWER_TOGGLE)

    async def power_on(self) -> None:
        await self.__send_command(self.Q_POWER_ON)

    async def power_off(self) -> None:
        await self.__send_command(self.Q_POWER_OFF)

    async def set_mute(self, wanted_mute: str) -> bool:
        max_loop: int = 10
        wanted_mute = wanted_mute.upper()
        if wanted_mute not in self.MUTES:
            return False

        target_mute = self.MUTES.index(wanted_mute)
        if self.power_status != 0:
            loop_idx = 0
            while self.power_status == 0 and loop_idx < max_loop:
                loop_idx += 1
                await self.get_status()

        orig_mute = self.muted_status
        while self.muted_status != target_mute:
            await self.toggle_mute()
            loop_idx = 0
            while self.power_status == 0 and loop_idx < max_loop:
                loop_idx += 1
                await asyncio.sleep(0.05)
            if self.muted_status == orig_mute:
                # we looped, the selected mute was not available.
                # and we keep the previously selected one
                return False
        return True

    async def set_input(self, wanted_input: str) -> bool:
        max_loop: int = 10
        wanted_input = wanted_input.upper()
        if wanted_input not in self.INPUTS[:-1]:
            return False

        target_input = self.INPUTS.index(wanted_input)
        if self.power_status != 0:
            loop_idx = 0
            while self.power_status == 0 and loop_idx < max_loop:
                loop_idx += 1
                await self.get_status()

        orig_input = self.current_input
        while self.current_input != target_input:
            await self.toggle_input()
            loop_idx = 0
            while self.power_status == 0 and loop_idx < max_loop:
                loop_idx += 1
                await asyncio.sleep(0.5)
            if self.current_input == orig_input:
                # we looped, the selected input was not available.
                # and we keep the previously selected one
                return False
        return True

    async def set_output(self, wanted_output: str) -> bool:
        max_loop: int = 10
        wanted_output = wanted_output.upper()
        if wanted_output not in self.OUTPUTS[:-1]:
            return False
        target_output = self.OUTPUTS.index(wanted_output)

        if self.power_status != 0:
            loop_idx = 0
            while self.power_status == 0 and loop_idx < max_loop:
                loop_idx += 1
                await self.get_status()

        orig_output = self.current_output
        while self.current_output != target_output:
            await self.toggle_output()
            loop_idx = 0
            while self.power_status == 0 and loop_idx < max_loop:
                loop_idx += 1
                await asyncio.sleep(0.05)
            if self.current_output == orig_output:
                # we looped, the selected input was not available.
                # and we keep the previously selected one
                return False
        return True

    def display_status(self) -> str:
        if self.power_status == 0:
            return self.POWERS[0]

        return f"Power is {self.POWERS[self.power_status]}, {self.MUTES[self.muted_status]}, Volume is {self.volume / 2:g}% -{(200 - self.volume) / 4:g}dB , input {self.INPUTS[self.current_input]}, output {self.OUTPUTS[self.current_output]}, sampling {self.SAMPLINGS[self.sampling_status]}"
