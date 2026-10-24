"""Sky loading and astronomy work run independently from equipment workflows."""

import asyncio

import numpy as np

from aio_astro.domain.models import Target
from aio_astro.gui.sky import SkyPanel
from aio_astro.sky.catalog import load_catalog
from aio_astro.sky.coordinates import horizontal, project
from aio_astro.sky.scene import build_scene
from aio_astro.sky.search import CatalogIndex


class SkyController:
    def __init__(self, panel: SkyPanel) -> None:
        self.panel = panel
        self.index: CatalogIndex | None = None
        self.solution = None

    async def refresh(self) -> None:
        if self.index is None:
            objects = await asyncio.to_thread(load_catalog)
            self.index = await asyncio.to_thread(CatalogIndex, objects)
        site, when = self.panel.inputs()
        scene = await asyncio.to_thread(build_scene, self.index.objects, site, when)
        self.panel.show_scene(scene, self.index)
        await self._refresh_solution(site, when)

    async def set_solution(self, result) -> None:
        self.solution = result
        await self._refresh_solution(*self.panel.inputs())
        points = self.panel.chart.renderer.solved_footprint
        if points is not None:
            if np.any(np.linalg.norm(points, axis=1) > 1):
                self.panel.layer_boxes["show_below"].setChecked(True)
            self.panel.chart.center_on_field(points)

    async def _refresh_solution(self, site, when) -> None:
        if self.solution is None:
            return
        result = self.solution
        targets = [Target("Solved field", ra / 15, dec) for ra, dec in result.solution.footprint]
        positions = await asyncio.to_thread(horizontal, targets, site, when)
        if result is self.solution:
            self.panel.chart.renderer.solved_footprint = np.array([project(p) for p in positions])
            self.panel.solved_info.setText(
                f"Orange outline: measured field from {result.source.name} · HDU {result.hdu}. "
                "Projected for the chart's site/time; this is not live mount pointing."
            )
            self.panel.chart.update()
