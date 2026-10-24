"""Own solve/cancel/export tasks independently of capture and mount control."""

import asyncio
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from aio_astro.adapters.astap import ASTAPConfig
from aio_astro.services.plate_solving import SolveService, in_thread, save_solution
from aio_astro.services.solve_images import fits_hints


class PlateSolvingController:
    def __init__(self, window, sky, launch, log, show_error) -> None:
        self.window, self.sky = window, sky
        self.panel = window.plate_solving
        self.launch, self.log, self.show_error = launch, log, show_error
        self.result = self.last_capture = self.task = None
        self.busy = False
        panel = self.panel
        panel.browse.clicked.connect(self.browse)
        panel.latest.clicked.connect(self.use_latest)
        panel.source.textChanged.connect(self.invalidate)
        panel.hdu.valueChanged.connect(self.invalidate)
        panel.solve.clicked.connect(self.start)
        panel.cancel.clicked.connect(self.cancel)
        panel.hints.clicked.connect(lambda: self._launch(self.read_hints))
        panel.save.clicked.connect(lambda: self._launch(self.save))
        panel.show_field.clicked.connect(lambda: self._launch(self.show_field))
        window.open_solve.triggered.connect(self.open_from_menu)

    def _launch(self, operation, *, cancellable=False) -> None:
        if not self.busy:
            self.busy = True
            self.panel.set_busy(True)
            self.panel.cancel.setEnabled(cancellable)
            self.panel.save.setEnabled(False)
            self.panel.show_field.setEnabled(False)
            self.task = self.launch(self._run(operation))

    async def _run(self, operation) -> None:
        try:
            await operation()
        except asyncio.CancelledError:
            self.panel.status.setText("Cancelled · original FITS retained")
            self.log("Plate-solving operation cancelled; no upload or hardware command")
            raise
        except Exception as exc:
            self.panel.status.setText(str(exc))
            self.show_error(f"Plate solving: {exc}")
        finally:
            self.busy = False
            self.panel.set_busy(False)
            self.panel.cancel.setEnabled(False)
            self.panel.save.setEnabled(self.result is not None)
            self.panel.show_field.setEnabled(self.result is not None)

    def invalidate(self) -> None:
        self.result = None
        self.panel.result.clear()
        self.panel.save.setEnabled(False)
        self.panel.show_field.setEnabled(False)
        self.panel.status.setText("Source changed; solve this image to measure its field")

    def browse(self) -> None:
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(
            self.panel,
            "Plate solve a saved FITS image",
            self.panel.source.text(),
            "FITS images (*.fits *.fit *.fts *.fits.fz *.fit.fz);;All files (*)",
        )
        if path:
            self.panel.hdu.setValue(0)
            self.panel.source.setText(path)

    def open_from_menu(self) -> None:
        self.window.tabs.setCurrentWidget(self.panel)
        self.browse()

    def saved_capture(self, path: Path) -> None:
        self.last_capture = path
        self.panel.latest.setEnabled(True)

    def use_latest(self) -> None:
        if self.last_capture and not self.busy:
            self.panel.hdu.setValue(0)
            self.panel.source.setText(str(self.last_capture))

    def start(self) -> None:
        if self.busy:
            return
        try:
            request = self.panel.request()
            config = ASTAPConfig(
                Path(self.panel.executable.text().strip()).expanduser(),
                Path(self.panel.directory.text().strip()).expanduser(),
                self.panel.database.currentData(),
            )
        except ValueError as exc:
            self.show_error(str(exc))
            return
        self.invalidate()
        self.window.error.hide()

        async def solve() -> None:
            self.panel.status.setText(
                f"Solving locally · {request.timeout_seconds:g} s deadline · Cancel available"
            )
            self.log(f"ASTAP local solve: {request.source.name}, HDU {request.hdu}; no upload")
            self.result = await SolveService(config).solve(request)
            value = self.result
            solution = value.solution
            self.panel.result.setPlainText(
                f"{'SIMULATED SOURCE · ' if value.simulated else ''}MEASURED ICRS FIELD\n\n"
                f"Centre RA    {solution.ra_deg / 15:.6f} h  ({solution.ra_deg:.6f}°)\n"
                f"Centre Dec   {solution.dec_deg:+.6f}°\n\n"
                f"Pixel scale X / Y   {solution.scale_x_arcsec:.4f} / "
                f"{solution.scale_y_arcsec:.4f} arcsec/pixel\n"
                f"Field width × height   {solution.width_deg:.5f} × {solution.height_deg:.5f}°\n"
                f"+Y angle east of north   {solution.positive_y_angle_deg:.3f}°\n"
                f"Parity (WCS determinant sign)   {solution.parity:+d}\n\n"
                f"Source   {value.source}\nHDU {value.hdu} · {value.width} × {value.height}\n"
                f"{value.intensity_method}\n\n{value.backend}\n"
                f"Database   {value.database.upper()} · {value.database_tiles:,} tiles\n"
                f"Elapsed   {value.elapsed_seconds:.2f} s\n"
                + ("\nWarnings:\n" + "\n".join(value.warnings) if value.warnings else "")
            )
            self.panel.status.setText("Solved and WCS validated · original FITS unchanged")
            self.log(
                f"Plate solve validated: RA {solution.ra_deg:.6f}°, Dec {solution.dec_deg:+.6f}°"
            )

        self._launch(solve, cancellable=True)

    def cancel(self) -> None:
        if self.task and not self.task.done():
            self.panel.cancel.setEnabled(False)
            self.task.cancel()

    async def read_hints(self) -> None:
        if not self.panel.source.text().strip():
            raise ValueError("Open a saved FITS image first")
        self.invalidate()
        hints = await in_thread(
            fits_hints,
            await in_thread(Path(self.panel.source.text().strip()).expanduser),
            self.panel.hdu.value(),
        )
        if not 0.15 <= hints.field_height_deg <= 20:
            raise ValueError("Header field height is outside the supported 0.15–20 degree range")
        self.panel.ra.setValue(hints.ra_hours)
        self.panel.dec.setValue(hints.dec_deg)
        self.panel.fov.setValue(hints.field_height_deg)
        self.panel.use_position.setChecked(True)
        self.panel.status.setText("FITS search hints loaded · review estimates, then Solve locally")
        self.panel.result.setPlainText(hints.provenance)

    async def save(self) -> None:
        if self.result is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self.panel,
            "Save separate WCS solution",
            str(self.result.source.with_suffix(".wcs")),
            "WCS FITS solution (*.wcs)",
        )
        if filename:
            await in_thread(save_solution, self.result, Path(filename))
            self.log(f"Saved separate WCS solution: {filename}")

    async def show_field(self) -> None:
        if self.result:
            await self.sky.set_solution(self.result)
            self.window.tabs.setCurrentWidget(self.window.sky)
