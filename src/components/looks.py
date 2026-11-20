"""Outfit display helpers shared by Home, Planner, Studio and Saved Looks."""

from __future__ import annotations

import streamlit as st

from src.core.color_library import color_name
from src.models.domain import HAIR_STYLES, NAIL_SHAPES, SLOT_LABELS, Outfit
from src.visualizer import flatlay, mannequin


def mannequin_html(outfit: Outfit, height: int = 420) -> str:
    return f'<div class="cm-mannequin">{mannequin.render_svg(outfit, height=height)}</div>'


def palette_list(outfit: Outfit) -> None:
    from src.components.ui import chip_html, esc

    rows = []
    for it in outfit.items:
        label = it.label or color_name(it.color_hex)
        extra = f" · {NAIL_SHAPES.get(it.variant or '', '')}" if it.slot == "nails" else ""
        rows.append(f"<div>{chip_html(it.color_hex, SLOT_LABELS[it.slot])} <span class='cm-muted'>{esc(label)}{esc(extra)}</span></div>")
    rows.append(f"<div class='cm-muted'>Hair: {esc(HAIR_STYLES.get(outfit.hair_style, ''))} · {esc(color_name(outfit.hair_color))}</div>")
    st.markdown("".join(rows), unsafe_allow_html=True)


def export_buttons(outfit: Outfit, key: str, photo_loader=None, layout: str | None = None) -> None:
    """Two-step export: prepare (render) on demand, then download — avoids rendering every card."""
    ready_key = f"export_ready_{key}"
    if not st.session_state.get(ready_key):
        if st.button("Export images", key=f"prep_{key}", width="stretch"):
            st.session_state[ready_key] = True
            st.rerun()
        return
    with st.spinner("Rendering…"):
        flat_png = flatlay.render_png(outfit, layout or outfit.layout, photo_loader=photo_loader)
        mann_png = mannequin.render_png(outfit)
    safe = "".join(c if c.isalnum() else "-" for c in (outfit.name or "look")).strip("-").lower() or "look"
    a, b = st.columns(2)
    a.download_button("Flat-lay PNG", flat_png, f"{safe}-flatlay.png", "image/png", key=f"dl_f_{key}", width="stretch")
    b.download_button("Mannequin PNG", mann_png, f"{safe}-mannequin.png", "image/png", key=f"dl_m_{key}", width="stretch")
