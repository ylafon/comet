import asyncio

from comet import Comet
import argparse
from argparse import ArgumentParser
from uuid import UUID
from bleak import BleakScanner

desired_volume: float
desired_input: str
desired_output: str
desired_mute: str
desired_power_status: str


async def doit(args: argparse.Namespace):
    if hasattr(args, "addr"):
        comet_addr: str = args.addr
    else:
        if args.v:
            print("Scanning for Comet")
        devices = await BleakScanner.discover()
        if args.v:
            print(f"Found {len(devices)} BLE devices")
        for d in devices:
            if d.name is not None:
                if d.name.startswith("Comet_") or d.name == "EXOGAL_Comet_DAC":
                    if args.v:
                        print(d.details)
                    comet_addr: UUID | str = d.address

    if "comet_addr" not in locals():
        print("Comet not detected.")
        return

    comet: Comet = Comet(comet_addr)
    await comet.connect()

    await comet.get_status()
    print(f"Connected to {comet_addr}")
    print(f"Status: {comet.display_status()}")

    if args.s:
        if hasattr(args, "power"):
            # Comet.POWERS[1] is a sad way to say "ON"
            if args.power == Comet.POWERS[1]:
                await comet.power_on()
            else:
                await comet.power_off()
        if hasattr(args, "output"):
            if args.v:
                print(f"Setting output to {args.output}")
            await comet.set_output(args.output)
        if hasattr(args, "input"):
            if args.v:
                print(f"Setting input to {args.input}")
            await comet.set_input(args.input)
        if hasattr(args, "mute"):
            if args.v:
                print(f"Setting mute to {args.mute}")
            await comet.set_mute(args.mute)
        # and finally
        if hasattr(args, "volume"):
            if args.v:
                print(f"Setting volume to {args.volume}")
            await comet.set_volume(args.volume)
        print(f"Final Status: {comet.display_status()}")


if __name__ == "__main__":
    arg_parser: ArgumentParser = argparse.ArgumentParser()
    arg_parser.add_argument("--addr", type=str, default=argparse.SUPPRESS,
                            help="Comet address")
    arg_parser.add_argument("--volume", type=float, default=argparse.SUPPRESS,
                            help="Desired Comet volume")
    arg_parser.add_argument("--input", type=str, default=argparse.SUPPRESS,
                            choices=Comet.INPUTS[:-1], help="Desired Comet input")
    arg_parser.add_argument("--output", type=str, default=argparse.SUPPRESS,
                            choices=Comet.OUTPUTS[:-1], help="Desired Comet output")
    arg_parser.add_argument("--mute", type=str, default=argparse.SUPPRESS,
                            choices=Comet.MUTES,
                            help="Desired Comet mute state")
    arg_parser.add_argument("--power", type=str, default=argparse.SUPPRESS,
                            choices=Comet.POWERS[1:],
                            help="Desired Comet power state")
    arg_parser.add_argument("-s", action="store_true", help="Set values")
    arg_parser.add_argument("-v", action="store_true", help="Verbose")

    arguments = arg_parser.parse_args()

    asyncio.run(doit(arguments))
