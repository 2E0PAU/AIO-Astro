"""Discovery and management are shared by camera and telescope connection panels."""

from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.adapters.alpaca.discovery import discover
from aio_astro.gui.device_connection import DeviceConnectionPanel


class DeviceBrowser:
    def __init__(self, panel: DeviceConnectionPanel, launch, log) -> None:
        self.panel, self.log = panel, log
        panel.discover.clicked.connect(lambda: launch(self.discover()))
        panel.query.clicked.connect(lambda: launch(self.query()))

    async def discover(self) -> None:
        panel = self.panel
        panel.discover.setEnabled(False)
        try:
            servers = await discover()
            for server in servers:
                if panel.endpoint.findText(server.url) < 0:
                    panel.endpoint.addItem(server.url)
            if servers:
                panel.endpoint.setCurrentText(servers[0].url)
            self.log(f"Discovery found {len(servers)} Alpaca server(s)")
        finally:
            panel.discover.setEnabled(True)

    async def query(self) -> None:
        self.panel.query.setEnabled(False)
        try:
            async with AlpacaClient(self.panel.endpoint.currentText()) as client:
                self.panel.show_devices(await client.configured_devices())
        finally:
            self.panel.query.setEnabled(True)
