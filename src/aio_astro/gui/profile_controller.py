"""Load/save portable equipment combinations without issuing device commands."""

import asyncio

from aio_astro.domain.errors import DeviceError
from aio_astro.services.profiles import ProfileStore, RigProfile


class ProfileController:
    def __init__(
        self, window, equipment, mount_controller, launch, log, store: ProfileStore | None = None
    ) -> None:
        self.window, self.equipment, self.mount_controller = window, equipment, mount_controller
        self.panel = window.equipment.profiles
        self.store = store or ProfileStore()
        self.launch, self.log = launch, log
        self.panel.save.clicked.connect(lambda: launch(self.save()))
        self.panel.load.clicked.connect(lambda: launch(self.load()))

    async def reload(self, selected: str = "") -> None:
        profiles = await asyncio.to_thread(self.store.load)
        self.panel.names.clear()
        self.panel.names.addItems(sorted(profiles))
        if selected:
            self.panel.names.setCurrentText(selected)

    async def save(self) -> None:
        profile = RigProfile(
            self.panel.names.currentText().strip(),
            self.panel.telescope.text().strip(),
            self.window.equipment.configuration(),
            self.window.mount.configuration(),
            self.window.sky.inputs()[0],
            self.window.mount.minimum_altitude.value(),
        )
        await asyncio.to_thread(self.store.save, profile)
        await self.reload(profile.name)
        self.log(f"Saved setup profile: {profile.name}")

    async def load(self) -> None:
        if self.equipment.camera or self.equipment.mount or self.mount_controller.busy:
            raise DeviceError("Disconnect equipment before loading a different setup")
        profiles = await asyncio.to_thread(self.store.load)
        if self.equipment.camera or self.equipment.mount or self.mount_controller.busy:
            raise DeviceError("Disconnect equipment before loading a different setup")
        profile = profiles.get(self.panel.names.currentText())
        if profile is None:
            raise DeviceError("Select a saved setup profile")
        self.panel.telescope.setText(profile.telescope)
        self.window.equipment.apply_configuration(profile.camera)
        self.window.mount.apply_configuration(profile.mount)
        self.window.sky.set_site(profile.site)
        self.window.mount.minimum_altitude.setValue(profile.minimum_altitude)
        self.log(f"Loaded setup profile: {profile.name}; equipment remains disconnected")
