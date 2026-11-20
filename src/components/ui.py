"""Reusable visual components (HTML is built only from validated data and escaped text)."""

from __future__ import annotations

import html
import io
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any

import streamlit as st

from src.core.color_convert import normalize_hex
from src.core.color_library import COLOR_LIBRARY, color_name
from src.core.scoring import COMPONENT_LABELS, ScoreBreakdown
from src.database.base import BackendError, BackendUnavailable, NotAuthorized, NotFound
from src.models.domain import CATEGORY_LABELS, OutfitItem, WardrobeItem


def esc(text: Any) -> str:
    return html.escape(str(text if text is not None else ""))


def header(title: str, subtitle: str = "", eyebrow: str = "ColorMuse") -> None:
    st.markdown(
        f'<div class="cm-eyebrow">{esc(eyebrow)}</div><div class="cm-title">{esc(title)}</div>'
        + (f'<div class="cm-sub">{esc(subtitle)}</div>' if subtitle else ""),
        unsafe_allow_html=True,
    )


@contextmanager
def card():
    with st.container(border=True):
        st.markdown('<span class="cm-card-marker"></span>', unsafe_allow_html=True)
        yield


def swatch_html(hex_value: str, name: str | None = None, show_hex: bool = True) -> str:
    hx = normalize_hex(hex_value)
    nm = name or color_name(hx)
    return (f'<div class="cm-swatch"><div class="dot" style="background:{hx}"></div>'
            f'<div class="nm">{esc(nm)}</div>' + (f'<div class="hx">{hx}</div>' if show_hex else "") + "</div>")


def swatches(colors: list[tuple[str, str | None]] | list[str], show_hex: bool = True) -> None:
    parts = []
    for c in colors:
        hx, nm = (c, None) if isinstance(c, str) else c
        parts.append(swatch_html(hx, nm, show_hex))
    st.markdown(f'<div class="cm-swatch-row">{"".join(parts)}</div>', unsafe_allow_html=True)


def chip_html(hex_value: str, label: str | None = None) -> str:
    hx = normalize_hex(hex_value)
    return f'<span class="cm-chip"><i style="background:{hx}"></i>{esc(label or color_name(hx))}</span>'


def chips(colors: list[str]) -> None:
    st.markdown("".join(chip_html(c) for c in colors), unsafe_allow_html=True)


def score_badge(score: float, rule: str | None = None) -> str:
    rule_html = f'<span class="cm-rule">{esc(rule)}</span>' if rule else ""
    return f'<span class="cm-score">{score:.0f}<small>/100</small></span>{rule_html}'


def breakdown_bars(bd: ScoreBreakdown) -> None:
    rows = []
    for key, val in bd.components.items():
        pct = int(round(val * 100))
        w = int(round(bd.weights.get(key, 0) * 100))
        rows.append(
            f'<div class="cm-bar"><span>{esc(COMPONENT_LABELS[key])} · {w}%</span>'
            f'<div class="track"><div class="fill" style="width:{pct}%"></div></div><span>{pct}</span></div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def empty_state(title: str, text: str) -> None:
    st.markdown(f'<div class="cm-empty"><b>{esc(title)}</b>{esc(text)}</div>', unsafe_allow_html=True)


def muted(text: str) -> None:
    st.markdown(f'<div class="cm-muted">{esc(text)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- color input
LIBRARY_OPTIONS = [f"{c.name} · {c.hex}" for c in COLOR_LIBRARY]


def color_input(label: str, key: str, default: str = "#B77E79", help: str | None = None) -> str:
    """Pick from the named library or a free color picker. Returns a hex."""
    mode_key = f"{key}_mode"
    mode = st.radio(label, ["Library", "Custom"], horizontal=True, key=mode_key, help=help)
    if mode == "Library":
        idx = next((i for i, c in enumerate(COLOR_LIBRARY) if c.hex == normalize_hex(default)), None)
        if idx is None:
            near = color_name(default)
            idx = next(i for i, c in enumerate(COLOR_LIBRARY) if c.name == near)
        choice = st.selectbox(f"{label} (library)", LIBRARY_OPTIONS, index=idx, key=f"{key}_lib",
                              label_visibility="collapsed")
        return choice.split("·")[-1].strip()
    return normalize_hex(st.color_picker(f"{label} (custom)", normalize_hex(default), key=f"{key}_pick",
                                         label_visibility="collapsed"))


# ---------------------------------------------------------------- garment thumbnails
@st.cache_data(max_entries=300, show_spinner=False)
def garment_png(variant: str, color_hex: str, pattern: str, secondary: str | None, slot: str = "", size: int = 220) -> bytes:
    """Rendered garment template (no photo yet) as PNG bytes. Pure → safe to cache globally."""
    from PIL import Image

    from src.visualizer.flatlay import _render_template

    item = OutfitItem(slot=slot or "top", color_hex=color_hex, pattern=pattern, secondary_hex=secondary, variant=variant)
    piece = _render_template(item, size - 20, size - 20, max_scale=2.2)
    bg = Image.new("RGBA", (size, size), (255, 253, 251, 255))
    bg.alpha_composite(piece, ((size - piece.width) // 2, (size - piece.height) // 2))
    buf = io.BytesIO()
    bg.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def item_picture(item: WardrobeItem, source: Any | None, width: str | int = "stretch") -> None:
    if source is not None:
        st.image(source, width=width)
    else:
        st.image(garment_png(item.variant, item.primary_color, item.pattern,
                             item.secondary_colors[0] if item.secondary_colors else None, item.slot), width=width)


def item_caption(item: WardrobeItem) -> str:
    fav = "♥ " if item.favorite else ""
    return f"{fav}**{esc(item.name)}**  \n{CATEGORY_LABELS[item.category]}" + (f" · {esc(item.subcategory)}" if item.subcategory else "")


# ---------------------------------------------------------------- error handling
def show_backend_error(exc: Exception) -> None:
    if isinstance(exc, BackendUnavailable):
        st.error(f"☁️ {exc}")
        if st.button("Retry", key=f"retry_{id(exc)}"):
            st.rerun()
    elif isinstance(exc, NotAuthorized):
        from src.services import session

        st.warning(str(exc))
        session.set_session(None)
        if st.button("Sign in again"):
            st.rerun()
    elif isinstance(exc, NotFound):
        st.warning("That record no longer exists. It may have been deleted.")
    else:
        st.error(f"Something went wrong: {exc}")


def guarded(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a page body: backend errors become friendly messages instead of tracebacks."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except BackendError as exc:
            show_backend_error(exc)
            return None
    return wrapper
