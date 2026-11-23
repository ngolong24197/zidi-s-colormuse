"""Scan: point the camera at a piece → colors, recommendations, add to wardrobe."""

from __future__ import annotations

from src.components import ui
from src.components.scanner import render_scanner


@ui.guarded
def render() -> None:
    render_scanner(full_app=True)


render()
