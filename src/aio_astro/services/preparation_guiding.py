"""Suspend guiding output during focus/slew and explicitly settle before resuming."""

from aio_astro.domain.errors import DeviceError


class PreparationGuiding:
    def __init__(self, guider):
        self.guider = guider
        self.paused_here = False

    async def pause(self):
        if self.guider is None:
            return
        state = await self.guider.call("get_app_state")
        paused = await self.guider.call("get_paused")
        if type(paused) is not bool or state not in (
            "Stopped",
            "Selected",
            "Calibrating",
            "Guiding",
            "LostLock",
            "Paused",
            "Looping",
        ):
            raise DeviceError("PHD2 returned an invalid state; preparation stopped")
        if state == "Calibrating":
            raise DeviceError("Finish PHD2 calibration before preparing capture")
        if state in ("Guiding", "LostLock", "Paused") and not paused:
            self.paused_here = True
            await self.guider.call("set_paused", [True, "full"])
            if await self.guider.call("get_paused") is not True:
                raise DeviceError("PHD2 did not confirm suspended guiding; preparation stopped")

    async def resume(self, *, guided_sequence=False):
        if self.guider is None:
            return
        if self.paused_here or guided_sequence:
            await self.guider.call("set_paused", [False])
            if await self.guider.call("get_paused") is not False:
                raise DeviceError("PHD2 remains paused; inspect guiding before capture")
            if not guided_sequence:
                # SequenceRunner performs this wait itself for a guided sequence.
                await self.guider.start_guiding()
