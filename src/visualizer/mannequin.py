"""Illustrated mannequin: layered, recolorable SVG figure (browser) and PNG (export).

Both renderers consume the same ``layer_plan`` built from an ``Outfit``, so the
SVG preview and the exported PNG always show exactly the same look.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageDraw

from src.core.color_convert import hex_to_rgb
from src.models.domain import Outfit
from src.visualizer.patterns import pattern_tile, svg_pattern_def
from src.visualizer.svg_assets import (
    Asset,
    Transform,
    body_colors,
    draw_asset,
    load_mannequin_layer,
    load_template,
    role_colors,
    svg_paths,
)

VIEW_X, VIEW_Y, VIEW_W, VIEW_H = 52.0, 4.0, 296.0, 976.0
BASE_LAYER_HEX = "#EDE4DA"  # modest neutral base when no top/bottom/dress is chosen
BACKDROP_HEX = "#F1E4DF"

# Draw order (back to front). Earrings sit above the hair; sunglasses and hats on top.
DRAW_ORDER = ("bottom", "top", "dress", "belt", "outerwear", "scarf", "bag", "shoes", "jewelry",
              "hair_front", "accessory", "jewelry_front", "hat")


@dataclass
class Layer:
    key: str
    asset: Asset
    colors: dict[str, str]
    pattern: str = "solid"
    main_hex: str = "#000000"
    secondary_hex: str | None = None
    outline_key: str = "outline"


def layer_plan(outfit: Outfit) -> list[Layer]:
    bc = body_colors(outfit.skin_tone, outfit.hair_color)
    body_c = {"skin": bc["skin"], "hair": bc["hair"], "outline": bc["skin_outline"]}
    hair_c = {"hair": bc["hair"], "outline": bc["hair_outline"]}
    style = outfit.hair_style or "long_waves"
    layers = [
        Layer("hair_back", load_mannequin_layer(f"hair_{style}_back"), hair_c),
        Layer("body", load_mannequin_layer("body"), body_c),
    ]
    by_slot = {it.slot: it for it in outfit.items}
    nails = by_slot.get("nails")
    if nails:
        layers.append(Layer("nails", load_mannequin_layer(f"nails_{nails.variant}"),
                            role_colors(nails.color_hex), main_hex=nails.color_hex))
    if "dress" not in by_slot:
        if "bottom" not in by_slot:
            layers.append(Layer("base_bottom", load_template("shorts"), role_colors(BASE_LAYER_HEX)))
        if "top" not in by_slot:
            layers.append(Layer("base_top", load_template("tank"), role_colors(BASE_LAYER_HEX)))

    for key in DRAW_ORDER:
        if key == "hair_front":
            layers.append(Layer("hair_front", load_mannequin_layer(f"hair_{style}_front"), hair_c))
            continue
        slot = "jewelry" if key == "jewelry_front" else key
        item = by_slot.get(slot)
        if item is None:
            continue
        is_earring = item.variant == "earrings"
        if slot == "jewelry" and (key == "jewelry") == is_earring:
            continue
        try:
            asset = load_template(item.variant or "")
        except FileNotFoundError:
            continue
        layers.append(Layer(slot, asset, role_colors(item.color_hex, item.secondary_hex),
                            item.pattern, item.color_hex, item.secondary_hex))
    return layers


def _uid(outfit: Outfit) -> str:
    sig = outfit.id + "|" + "|".join(f"{i.slot}{i.color_hex}{i.pattern}{i.variant}" for i in outfit.items)
    return "m" + hashlib.sha1(sig.encode()).hexdigest()[:8]


def render_svg(outfit: Outfit, height: int = 560, background: bool = True) -> str:
    """Inline SVG markup (no scripts, only paths) for the browser preview."""
    uid = _uid(outfit)
    defs, body = [], []
    if background:
        body.append(f'<ellipse cx="200" cy="470" rx="128" ry="420" fill="{BACKDROP_HEX}"/>')
        body.append('<ellipse cx="200" cy="968" rx="62" ry="8" fill="#302B2B" fill-opacity="0.12"/>')
    for n, layer in enumerate(layer_plan(outfit)):
        pid = None
        if layer.pattern != "solid":
            pid = f"{uid}-{n}"
            defs.append(svg_pattern_def(layer.pattern, pid, layer.main_hex, layer.secondary_hex))
        body.append(f'<g data-layer="{layer.key}">' + svg_paths(layer.asset, layer.colors, pid, layer.outline_key) + "</g>")
    width = int(round(height * VIEW_W / VIEW_H))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEW_X} {VIEW_Y} {VIEW_W} {VIEW_H}" '
        f'width="{width}" height="{height}" role="img" aria-label="Illustrated outfit: {_esc(outfit.name)}">'
        f"<defs>{''.join(defs)}</defs>{''.join(body)}</svg>"
    )


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_image(outfit: Outfit, height: int = 900, supersample: int = 2, background: bool = True) -> Image.Image:
    """RGBA Pillow image of the mannequin."""
    scale = height / VIEW_H * supersample
    w, h = int(round(VIEW_W * scale)), int(round(VIEW_H * scale))
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tf = Transform(scale, -VIEW_X * scale, -VIEW_Y * scale)
    if background:
        d = ImageDraw.Draw(canvas)
        cx, cy = (200 - VIEW_X) * scale, (470 - VIEW_Y) * scale
        d.ellipse((cx - 128 * scale, cy - 420 * scale, cx + 128 * scale, cy + 420 * scale), fill=hex_to_rgb(BACKDROP_HEX) + (255,))
        sy = (968 - VIEW_Y) * scale
        d.ellipse((cx - 62 * scale, sy - 8 * scale, cx + 62 * scale, sy + 8 * scale), fill=(48, 43, 43, 30))
    for layer in layer_plan(outfit):
        tile = pattern_tile(layer.pattern, layer.main_hex, layer.secondary_hex, round(scale, 3)) if layer.pattern != "solid" else None
        draw_asset(canvas, layer.asset, tf, layer.colors, tile, layer.outline_key)
    if supersample > 1:
        canvas = canvas.resize((w // supersample, h // supersample), Image.Resampling.LANCZOS)
    return canvas


def render_png(outfit: Outfit, height: int = 900) -> bytes:
    from src.visualizer.export import poster

    from src.i18n import _

    img = poster(outfit, render_image(outfit, height), subtitle=_("Mannequin view"))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
