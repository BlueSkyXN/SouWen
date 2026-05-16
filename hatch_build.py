"""Hatch build hooks for packaging generated assets."""

from __future__ import annotations

from pathlib import Path
from shutil import copyfile

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Ensure the single-file Web Panel is present before building wheels."""

    def initialize(self, version: str, build_data: dict) -> None:
        if self.target_name != "wheel":
            return

        root = Path(self.root)
        panel_html = root / "src" / "souwen" / "server" / "panel.html"
        panel_dist = root / "panel" / "dist" / "index.html"

        if panel_html.is_file():
            return
        if panel_dist.is_file():
            panel_html.parent.mkdir(parents=True, exist_ok=True)
            copyfile(panel_dist, panel_html)
            return

        raise RuntimeError(
            "Missing src/souwen/server/panel.html. "
            "Run `cd panel && npm ci && npm run build:local` before building the wheel."
        )
