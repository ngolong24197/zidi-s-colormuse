"""Shared PNG export styling: editorial poster frame, fonts and palette strip."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.core.color_convert import hex_to_rgb
from src.i18n import _ as tr
from src.i18n import cname, get_language, label
from src.models.domain import Outfit

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
IVORY = (248, 244, 239)
CHARCOAL = (48, 43, 43)
DUSTY_ROSE = (183, 126, 121)
BURGUNDY = (113, 62, 74)
TAUPE = (200, 173, 145)


def font(kind: str, size: int, weight: str | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """'serif' (Cormorant Garamond) or 'sans' (Jost).

    Jost has no Vietnamese stacked diacritics (ạ, ề, ố…), so Vietnamese text uses
    Cormorant Garamond, which covers them (verified by a test).
    """
    return _font(kind, size, weight, get_language())


@lru_cache(maxsize=48)
def _font(kind: str, size: int, weight: str | None, lang: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    serif = kind == "serif" or lang == "vi"
    path = FONT_DIR / ("CormorantGaramond.ttf" if serif else "Jost.ttf")
    if serif and kind != "serif" and weight in ("Light", "Regular"):
        weight = "Medium"  # keep small sans-replacement text legible
    try:
        f = ImageFont.truetype(str(path), size)
        if weight:
            try:
                f.set_variation_by_name(weight)
            except (OSError, ValueError, AttributeError):
                pass
        return f
    except OSError:
        return ImageFont.load_default(size)


def _text_w(draw: ImageDraw.ImageDraw, text: str, f) -> int:
    l, _, r, _ = draw.textbbox((0, 0), text, font=f)
    return r - l


def _fit(draw: ImageDraw.ImageDraw, text: str, f, max_w: int) -> str:
    if _text_w(draw, text, f) <= max_w:
        return text
    while text and _text_w(draw, text + "…", f) > max_w:
        text = text[:-1]
    return text + "…"


def palette_strip(draw: ImageDraw.ImageDraw, outfit: Outfit, box: tuple[int, int, int, int]) -> None:
    """Row of round swatches with slot labels and color names."""
    x0, y0, x1, y1 = box
    items = outfit.items[:8]
    if not items:
        return
    cell = (x1 - x0) / len(items)
    r = int(min(cell * 0.22, (y1 - y0) * 0.24))
    small = font("sans", max(11, int(r * 0.55)), "Regular")
    tiny = font("sans", max(10, int(r * 0.48)), "Light")
    for n, it in enumerate(items):
        cx = int(x0 + cell * (n + 0.5))
        cy = y0 + r + 4
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=hex_to_rgb(it.color_hex), outline=(220, 205, 196), width=2)
        slot_text = _fit(draw, label("slot", it.slot), small, int(cell - 6))
        draw.text((cx, cy + r + 8), slot_text, font=small, fill=CHARCOAL, anchor="ma")
        name = _fit(draw, cname(it.color_hex), tiny, int(cell - 6))
        draw.text((cx, cy + r + 8 + small.size + 4), name, font=tiny, fill=(110, 100, 98), anchor="ma")


def poster(outfit: Outfit, art: Image.Image, subtitle: str = "", width: int = 1080) -> Image.Image:
    """Frame artwork (RGBA) on an ivory card with title, details and palette."""
    header, footer, pad = 176, 190, 48
    art = art.copy()
    max_w, max_h = width - 2 * pad, int(width * 1.25)
    art.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    height = header + art.height + footer + pad
    img = Image.new("RGB", (width, height), IVORY)
    d = ImageDraw.Draw(img)
    d.text((pad, 34), "COLORMUSE", font=font("sans", 22, "Medium"), fill=DUSTY_ROSE)
    title = _fit(d, outfit.name or tr("Untitled look"), font("serif", 58, "SemiBold"), width - 2 * pad)
    d.text((pad, 62), title, font=font("serif", 58, "SemiBold"), fill=BURGUNDY)
    meta = " · ".join(x for x in (subtitle, label("occasion", outfit.occasion), label("style", outfit.style),
                                  tr("Score {score}", score=f"{outfit.score:.0f}") if outfit.score else "") if x)
    d.text((pad, 128), meta, font=font("sans", 22, "Light"), fill=CHARCOAL)
    ax = (width - art.width) // 2
    img.paste(art, (ax, header), art if art.mode == "RGBA" else None)
    y = header + art.height + 20
    d.line((pad, y, width - pad, y), fill=TAUPE, width=2)
    palette_strip(d, outfit, (pad, y + 22, width - pad, y + footer - 10))
    return img
