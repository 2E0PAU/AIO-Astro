"""Desktop entry point and an explicitly simulated, headless capture demo."""

import argparse
import asyncio
import logging
from pathlib import Path

from aio_astro.adapters.simulator import SimulatedCamera, SimulatedGuider
from aio_astro.domain.errors import AstroError
from aio_astro.domain.models import Exposure, SequencePlan
from aio_astro.services.sequencer import SequenceEvent, SequenceRunner


async def demo(args: argparse.Namespace) -> None:
    camera, guider = SimulatedCamera(), SimulatedGuider()
    plan = SequencePlan(
        Exposure(args.seconds),
        args.frames,
        args.output,
        guiding=args.guided,
        dither_every=args.dither_every,
    )

    def report(event: SequenceEvent) -> None:
        print(f"[{event.state}] {event.message}", flush=True)

    await camera.connect()
    try:
        runner = SequenceRunner(camera, guider=guider, on_event=report)
        await runner.run(plan)
    finally:
        await guider.stop()
        await camera.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="AIO Astro desktop observatory application")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("gui", help="Open the desktop application (default)")
    capture = sub.add_parser(
        "demo", help="Capture simulated images without a GUI or real equipment"
    )
    capture.add_argument("--frames", type=int, default=3)
    capture.add_argument("--seconds", type=float, default=0.1)
    capture.add_argument("--output", type=Path, default=Path("captures"))
    capture.add_argument("--guided", action="store_true", help="Use the simulated guider")
    capture.add_argument("--dither-every", type=int, default=0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        if args.command == "demo":
            asyncio.run(demo(args))
        else:
            from aio_astro.gui.app import run

            run()
    except (AstroError, ValueError, OSError) as exc:
        parser.exit(1, f"aio-astro: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Cancelled\n")


if __name__ == "__main__":
    main()
