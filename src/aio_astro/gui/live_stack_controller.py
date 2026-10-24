"""Bound live-stack work to one running frame and one pending frame."""

import asyncio
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from aio_astro.domain.stacking import RejectionRules
from aio_astro.services.live_stack import LiveStack
from aio_astro.services.preview import stretch


class LiveStackController:
    def __init__(self, panel, launch, log, show_error) -> None:
        self.panel, self.launch, self.log, self.show_error = panel, launch, log, show_error
        self.stack = LiveStack()
        self.rules = RejectionRules()
        self.skipped = 0
        self._pending = self._worker = None
        self._generation = 0
        self._saving = False
        panel.apply.clicked.connect(self.apply_rules)
        panel.reset.clicked.connect(self.reset)
        panel.save.clicked.connect(lambda: self.launch(self.save()))

    def apply_rules(self) -> None:
        try:
            self.rules = self.panel.rules()
            self.panel.rules_status.setText(
                "Rules applied to future frames; existing accepted frames retained"
            )
            self.log("Live-stack rejection rules updated")
        except ValueError as exc:
            self.show_error(str(exc))

    def reset(self) -> None:
        self._generation += 1
        self._pending = None
        self.skipped = 0
        self.stack = LiveStack(binning=self.panel.scale.currentData())
        self.panel.preview._image = None
        self.panel.preview.clear()
        self.panel.preview.setText("Waiting for the next captured light frame")
        self.panel.history.setRowCount(0)
        self.panel.image_info.setText("No accepted frames")
        self.panel.counts.setText("Accepted 0 · rejected 0 · skipped 0 · integration 0 s")
        self.panel.save.setEnabled(False)
        self.log("Started a new live stack; original captures retained")

    def offer(self, frame, path, *, context=None) -> None:
        if not self.panel.enabled.isChecked():
            return
        if self._pending is not None:
            self.skipped += 1
            self.panel.add_history(path, skipped=True)
            self.log(f"Live stack skipped {path.name}: processing queue full; original saved")
            return
        self._pending = self.stack, self._generation, frame, path, self.rules, context
        if self._worker is None or self._worker.done():
            self._worker = self.launch(self._drain())

    async def _drain(self) -> None:
        while self._pending is not None:
            stack, generation, frame, path, rules, context = self._pending
            self._pending = None
            job = asyncio.create_task(
                asyncio.to_thread(stack.add, frame, path, rules, context=context)
            )
            cancelled = False
            try:
                while True:
                    try:
                        result = await asyncio.shield(job)
                        break
                    except asyncio.CancelledError:
                        cancelled = True
                        if job.cancelled():
                            raise
                if cancelled:
                    raise asyncio.CancelledError
                if generation != self._generation:
                    continue
                self.panel.add_history(path, result["decision"])
                self.panel.counts.setText(
                    f"Accepted {result['accepted']} · rejected {result['rejected']} · "
                    f"skipped {self.skipped} · integration {result['integration_seconds']:g} s"
                )
                if not result["decision"].accepted:
                    self.log(
                        f"Live stack rejected {path.name}: "
                        f"{result['decision'].reason}; original saved"
                    )
                    continue
                preview = await asyncio.to_thread(stretch, result["image"])
                if generation == self._generation:
                    self.panel.preview.show_pixels(preview)
                    h, w = result["image"].shape[:2]
                    self.panel.image_info.setText(
                        f"{'SIMULATED · ' if result['simulated'] else ''}"
                        f"{w} × {h} · {result['binning']} × {result['binning']} mean processing · "
                        "linear registered mean · display stretch only"
                    )
                    self.panel.save.setEnabled(not self._saving)
            except Exception as exc:
                self.panel.enabled.setChecked(False)
                self._pending = None
                self.show_error(f"Live stacking stopped; original capture continues: {exc}")

    async def save(self) -> None:
        if self._saving:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self.panel,
            "Save linear live stack",
            str(Path.home() / "Pictures/AIO-Astro/live-stack.fits"),
            "FITS images (*.fits)",
        )
        if not filename:
            return
        self._saving = True
        self.panel.save.setEnabled(False)
        stack, skipped = self.stack, self.skipped
        write = asyncio.create_task(asyncio.to_thread(stack.save, Path(filename), skipped=skipped))
        cancelled = False
        try:
            while True:
                try:
                    await asyncio.shield(write)
                    break
                except asyncio.CancelledError:
                    cancelled = True
                    if write.cancelled():
                        raise
            self.log(f"Saved linear live stack: {filename}")
            if cancelled:
                raise asyncio.CancelledError
        finally:
            self._saving = False
            self.panel.save.setEnabled(self.stack.accepted > 0)
