"""Outfit display helpers shared by Home, Planner, Studio and Saved Looks."""

from __future__ import annotations

import streamlit as st

from src.i18n import _, cname, label
from src.models.domain import Outfit
from src.visualizer import flatlay, mannequin


def mannequin_html(outfit: Outfit, height: int = 420) -> str:
    return f'<div class="cm-mannequin">{mannequin.render_svg(outfit, height=height)}</div>'


def palette_list(outfit: Outfit) -> None:
    from src.components.ui import chip_html, esc

    rows = []
    for it in outfit.items:
        text = it.label or cname(it.color_hex)
        extra = f" · {label('nail', it.variant)}" if it.slot == "nails" else ""
        rows.append(f"<div>{chip_html(it.color_hex, label('slot', it.slot))} "
                    f"<span class='cm-muted'>{esc(text)}{esc(extra)}</span></div>")
    rows.append(f"<div class='cm-muted'>{esc(_('Hair'))}: {esc(label('hair', outfit.hair_style))} · "
                f"{esc(cname(outfit.hair_color))}</div>")
    st.markdown("".join(rows), unsafe_allow_html=True)


def export_buttons(outfit: Outfit, key: str, photo_loader=None, layout: str | None = None) -> None:
    """Two-step export: prepare (render) on demand, then download — avoids rendering every card."""
    ready_key = f"export_ready_{key}"
    if not st.session_state.get(ready_key):
        if st.button(_("Export images"), key=f"prep_{key}", width="stretch"):
            st.session_state[ready_key] = True
            st.rerun()
        return
    with st.spinner(_("Rendering…")):
        flat_png = flatlay.render_png(outfit, layout or outfit.layout, photo_loader=photo_loader)
        mann_png = mannequin.render_png(outfit)
    safe = "".join(c if c.isalnum() else "-" for c in (outfit.name or "look")).strip("-").lower() or "look"
    a, b = st.columns(2)
    a.download_button(_("Flat-lay PNG"), flat_png, f"{safe}-flatlay.png", "image/png", key=f"dl_f_{key}", width="stretch")
    b.download_button(_("Mannequin PNG"), mann_png, f"{safe}-mannequin.png", "image/png", key=f"dl_m_{key}", width="stretch")
