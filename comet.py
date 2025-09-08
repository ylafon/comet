import asyncio
from uuid import UUID
from bleak import BleakClient, BleakGATTCharacteristic


class Comet:
    __version__ = "0.0.1"
    #     status = "CMDS:01\r"
    __debug = True

    # commands
    q_status = "CMDS:01"
    q_version = "CMDS:02"

    # buttons
    q_mute_toggle = "BTNS:08"
    q_input_switch = "BTNS:10"
    q_output_switch = "BTNS:20"
    q_volume_inc = "BTNS:30"
    q_volume_dec = "BTNS:31"
    q_power_off = "BTNS:40"
    q_power_on = "BTNS:41"
    q_power_toggle = "BTNS:42"

    # display TOTO localise this
    samplings = ["NOCLK", "NOPLL", "192K", "176.4K", "96K", "88.2K", "48K",
                 "44.1K", "384K", "352.8K", "DSD", "NOCLK_REAL"]
    inputs = ["AES", "SPDIF", "TOSLINK", "ANALOG", "USB", "UNKNOWN"]
    outputs = ["MAIN", "HEAD", "UNKNOWN"]
    mutes = ["Unmuted", "Muted", "Reduced"]
    powers = ["Unknown", "On", "Off"]

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

    async def __process_callback(self, sender: BleakGATTCharacteristic,
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
        await self.__send_command(self.q_status)

    async def get_firmware_version(self) -> None:
        await self.__send_command(self.q_version)

    async def increase_volume(self) -> None:
        await self.__send_command(self.q_volume_inc)

    async def decrease_volume(self) -> None:
        await self.__send_command(self.q_volume_dec)

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
                    await self.__send_command(self.q_volume_inc)
                else:
                    await self.__send_command(self.q_volume_dec)
                loop_idx = 0
                while self.power_status == 0 and loop_idx < max_loop:
                    await asyncio.sleep(0.05)
                if self.__debug:
                    print(f"Current Volume [{self.volume / 2:g}]")

    async def toggle_mute(self) -> None:
        await self.__send_command(self.q_mute_toggle)

    async def toggle_input(self) -> None:
        await self.__send_command(self.q_input_switch)

    async def toggle_output(self) -> None:
        await self.__send_command(self.q_output_switch)

    async def toggle_power(self, mute: bool) -> None:
        await self.__send_command(self.q_power_toggle)

    async def power_on(self) -> None:
        await self.__send_command(self.q_power_on)

    async def power_off(self) -> None:
        await self.__send_command(self.q_power_off)

    async def set_input(self, wanted_input: str) -> None:
        max_loop: int = 10
        if wanted_input in self.inputs:
            target_input = self.inputs.index(wanted_input)
            # don't aim for UNKNOWN :)
            if target_input == 5:
                return

            if self.power_status != 0:
                loop_idx = 0
                while self.power_status == 0 and max_loop < max_loop:
                    loop_idx += 1
                    await self.get_status()

            while self.current_input != target_input:
                await self.__send_command(self.q_input_switch)
                loop_idx = 0
                while self.power_status == 0 and loop_idx < max_loop:
                    await asyncio.sleep(0.05)


    def display_status(self) -> str:
        if self.power_status == 0:
            return self.powers[0]

        return f"Power is {self.powers[self.power_status]}, {self.mutes[self.muted_status]}, Volume is {self.volume / 2:g}% -{(200 - self.volume) / 4:g}dB , input {self.inputs[self.current_input]}, output {self.outputs[self.current_output]}, sampling {self.samplings[self.sampling_status]}"
