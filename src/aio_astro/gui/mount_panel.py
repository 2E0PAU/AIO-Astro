"""Capability-driven mount controls; the actual operations live in MountController."""

from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPushButton

from aio_astro.domain.mount import MountCapabilities, MountStatus
from aio_astro.gui.device_connection import DeviceConnectionPanel


class MountPanel(DeviceConnectionPanel):
    def __init__(self) -> None:
        super().__init__("Telescope", "Mount")
        self.minimum_altitude = QDoubleSpinBox()
        self.minimum_altitude.setRange(0, 90)
        self.minimum_altitude.setValue(10)
        self.minimum_altitude.setSuffix(" °")
        form = QFormLayout()
        form.addRow("Minimum slew altitude", self.minimum_altitude)
        self.telemetry = QLabel("No mount connected")
        self.telemetry.setWordWrap(True)
        self.tracking = QPushButton("Enable tracking")
        self.park = QPushButton("Park")
        self.unpark = QPushButton("Unpark")
        self.abort = QPushButton("Abort motion")
        self.abort.setStyleSheet("color: #ffbf91; border-color: #a87752;")
        self.use_site = QPushButton("Use mount site in sky view")
        actions = QHBoxLayout()
        for button in (self.tracking, self.park, self.unpark, self.abort, self.use_site):
            button.setEnabled(False)
            actions.addWidget(button)
        layout = self.layout()
        layout.insertLayout(layout.count() - 1, form)
        layout.insertWidget(layout.count() - 1, self.telemetry)
        layout.insertLayout(layout.count() - 1, actions)
        info = QLabel(
            "Direct Alpaca: homemade mounts, Seestar or other Alpaca servers.\n"
            "Serial NEQ6: INDIGO SynScan driver → Alpaca agent. "
            "Original StarBook: INDIGO StarBook HTTP driver → Alpaca agent.\n"
            "Configure the actual serial port or StarBook network address in INDIGO. "
            "Sync identifies the already-centred target as the mount's current pointing."
        )
        info.setWordWrap(True)
        info.setObjectName("muted")
        layout.insertWidget(layout.count() - 1, info)

    def show_status(
        self, status: MountStatus, capabilities: MountCapabilities, *, busy: bool
    ) -> None:
        position = status.coordinates
        elevation_source = "configured" if status.elevation_is_configured else "mount"
        self.telemetry.setText(
            f"RA {position.ra_hours:.5f} h · Dec {position.dec_degrees:+.5f}° · "
            f"{status.system.name}\n"
            f"{'PARKED' if status.parked else 'Unparked'} · "
            f"{'SLEWING' if status.slewing else 'Stationary'} · "
            f"Tracking {'on' if status.tracking else 'off'}\n"
            f"Mount site {status.site.latitude:+.4f}°, {status.site.longitude:+.4f}° · "
            f"{status.site.elevation_m:g} m ({elevation_source}) · "
            f"{status.observed_at:%H:%M:%S} UTC"
        )
        self.tracking.setText("Disable tracking" if status.tracking else "Enable tracking")
        idle = not busy and not status.slewing
        self.tracking.setEnabled(idle and capabilities.tracking and not status.parked)
        self.park.setEnabled(idle and capabilities.park and not status.parked)
        self.unpark.setEnabled(idle and capabilities.unpark and status.parked)
        self.abort.setEnabled(True)
        self.use_site.setEnabled(True)
