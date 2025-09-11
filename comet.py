import asyncio
from uuid import UUID
from bleak import BleakClient, BleakGATTCharacteristic


class Comet:
    __version__ = "0.0.1"
    #     status = "CMDS:01\r"
    __debug = False

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

    # display TOTO localise this
    SAMPLINGS: list[str] = ["NOCLK_DETECT", "NOPLL", "192K", "176.4K", "96K",
                            "88.2K", "48K", "44.1K", "384K", "352.8K", "DSD",
                            "NOCLK"]
    INPUTS: list[str] = ["AES", "SPDIF", "TOSLINK", "ANALOG", "USB", "EXONET",
                         "AIR", "TUNER", "UNKNOWN"]
    OUTPUTS: list[str] = ["MAIN", "HEAD", "EXONET", "UNKNOWN"]
    MUTES: list[str] = ["Unmuted", "Muted", "Reduced"]
    POWERS: list[str] = ["Unknown", "On", "Off"]

    comet_addr: UUID | str = None
    characteristic: BleakGATTCharacteristic = None

    client: BleakClient = None

    firmware_version: str = None
    fpga_version: str = None
    power_status: int = 0
    muted_status: int = 0
    current_input: int = 0
    current_output: int = 0
    sampling_status: int = 0
    volume: int = 0

    def __init__(self, comet_addr: UUID | str):
        self.comet_addr = comet_addr

    def __process_callback(self, sender: BleakGATTCharacteristic,
                           raw_buffer: bytearray) -> None:
        buf = str(raw_buffer, 'utf-8')
        if self.__debug:
            print(f"Processing Buffer")
        # check length of the reply
        if len(buf) == 18:
            if self.__debug:
                print(f"-> {buf[0:4]}")
            if buf.startswith("RP01:"):
                self.volume = int(buf[5:8])
                self.power_status = 1 if buf[8] == "1" else 2
                self.muted_status = int(buf[9])
                self.sampling_status = int(buf[10])
                self.current_input = int(buf[11])
                self.current_output = int(buf[14])
                if self.__debug:
                    print(
                        f"UNKNOWN -> [{bytes(buf[12], "utf-8")[0]:02x}][{bytes(buf[13], "utf-8")[0]:02x}]")
            elif buf.startswith("RP02:"):
                self.firmware_version = buf[5:11]
                self.fpga_version = buf[11:17]
            else:
                if self.__debug:
                    print(f"Processing -> Unrecognized")

    async def __send_command(self, command: str) -> None:
        if self.__debug:
            print(f"Sending command [{command}]")
        if self.client is None or self.client.is_connected == False:
            await self.connect()
        # We reset power status to ensure new values will be populated
        self.power_status = 0
        await self.client.write_gatt_char(self.characteristic,
                                          bytearray("" + command + "\r",
                                                    encoding="utf-8"))
        await asyncio.sleep(0.05)

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
        max_loop: int = 10
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
                    await self.__send_command(self.Q_VOLUME_INC)
                else:
                    await self.__send_command(self.Q_VOLUME_DEC)
                loop_idx = 0
                while self.power_status == 0 and loop_idx < max_loop:
                    await asyncio.sleep(0.05)
                if self.__debug:
                    print(f"Current Volume [{self.volume / 2:g}]")

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

    async def set_input(self, wanted_input: str) -> bool:
        max_loop: int = 10
        wanted_input = wanted_input.upper()
        if wanted_input not in self.INPUTS:
            return False

        target_input = self.INPUTS.index(wanted_input)
        # don't aim for UNKNOWN :)
        if target_input == 8:
            return False

        if self.power_status != 0:
            loop_idx = 0
            while self.power_status == 0 and max_loop < max_loop:
                loop_idx += 1
                await self.get_status()

        orig_input = self.current_input
        while self.current_input != target_input:
            await self.toggle_input()
            loop_idx = 0
            while self.power_status == 0 and loop_idx < max_loop:
                loop_idx += 1
                await asyncio.sleep(0.05)
            if self.current_input == orig_input:
                # we looped, the selected input was not available.
                # and we keep the previously selected one
                return False
        return True

    async def set_output(self, wanted_output: str) -> bool:
        max_loop: int = 10
        wanted_output = wanted_output.upper()
        if wanted_output not in self.OUTPUTS:
            return False
        target_output = self.OUTPUTS.index(wanted_output)
        # don't aim for UNKNOWN :)
        if target_output == 3:
            return False

        if self.power_status != 0:
            loop_idx = 0
            while self.power_status == 0 and max_loop < max_loop:
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
