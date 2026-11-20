"""Flat-lay composer: arranges an outfit's pieces with predefined layout templates.

Each piece is drawn from its wardrobe photograph when available (and
``use_photos`` is on); otherwise from the recolored SVG garment template,
cropped to its own bounding box. Output is a Pillow image / PNG.
"""

from __future__ import annotations

import io
from collections.abc import Callable

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from src.models.domain import Outfit, OutfitItem
from src.visualizer.export import poster
from src.visualizer.patterns import pattern_tile
from src.visualizer.svg_assets import Transform, draw_asset, load_template, role_colors

Box = tuple[float, float, float, float]  # x, y, w, h as fractions of the board

LAYOUTS: dict[str, str] = {
    "editorial": "Editorial — hero pieces centre, accessories in side columns",
    "grid": "Grid — every piece in an even grid",
    "minimal": "Minimal — main pieces with a row of accessories beneath",
}

MAIN_ORDER = ("dress", "top", "bottom")
LEFT_ORDER = ("outerwear", "hat", "scarf", "belt")
RIGHT_ORDER = ("bag", "jewelry", "accessory", "nails", "shoes")
WEIGHT = {"outerwear": 2.2, "bag": 1.5, "shoes": 1.3, "hat": 1.0, "scarf": 1.2, "belt": 0.8,
          "jewelry": 0.9, "accessory": 0.9, "nails": 0.8}


def _stack(slots: list[str], x: float, w: float, y0: float = 0.03, y1: float = 0.97, gap: float = 0.025) -> dict[str, Box]:
    if not slots:
        return {}
    total = sum(WEIGHT.get(s, 1.0) for s in slots)
    avail = (y1 - y0) - gap * (len(slots) - 1)
    out, y = {}, y0
    for s in slots:
        h = avail * WEIGHT.get(s, 1.0) / total
        out[s] = (x, y, w, h)
        y += h + gap
    return out


def layout_boxes(layout: str, slots: list[str]) -> dict[str, Box]:
    present = set(slots)
    mains = [s for s in MAIN_ORDER if s in present]
    others = [s for s in slots if s not in MAIN_ORDER]
    if layout == "grid":
        ordered = mains + others
        n = len(ordered)
        cols = 1 if n == 1 else 2 if n <= 4 else 3
        rows = -(-n // cols)
        cw, rh = 0.94 / cols, 0.94 / rows
        return {s: (0.03 + (i % cols) * cw + 0.01, 0.03 + (i // cols) * rh + 0.01, cw - 0.02, rh - 0.02)
                for i, s in enumerate(ordered)}
    if layout == "minimal":
        out: dict[str, Box] = {}
        row_h = 0.24 if others else 0.0
        main_h = 0.94 - row_h - (0.03 if others else 0)
        if mains:
            if "dress" in mains:
                out["dress"] = (0.22, 0.03, 0.56, main_h)
            else:
                half = (0.94 - 0.04) / 2
                if "top" in present:
                    out["top"] = (0.04, 0.03, half, main_h)
                if "bottom" in present:
                    out["bottom"] = (0.04 + half + 0.02, 0.03, half, main_h)
        if others:
            cw = 0.94 / len(others)
            for i, s in enumerate(others):
                out[s] = (0.03 + i * cw + 0.008, 0.97 - row_h, cw - 0.016, row_h)
        return out
    # editorial
    left = [s for s in LEFT_ORDER if s in present]
    right = [s for s in RIGHT_ORDER if s in present]
    side_w = 0.27
    cx0 = 0.03 + (side_w + 0.02 if left else 0.0)
    cx1 = 0.97 - (side_w + 0.02 if right else 0.0)
    out = {}
    if "dress" in mains:
        out["dress"] = (cx0, 0.03, cx1 - cx0, 0.94)
    else:
        if "top" in present and "bottom" in present:
            out["top"] = (cx0, 0.03, cx1 - cx0, 0.40)
            out["bottom"] = (cx0, 0.45, cx1 - cx0, 0.52)
        elif "top" in present:
            out["top"] = (cx0, 0.03, cx1 - cx0, 0.94)
        elif "bottom" in present:
            out["bottom"] = (cx0, 0.03, cx1 - cx0, 0.94)
    if left:
        out.update(_stack(left, 0.03, side_w))
    if right:
        out.update(_stack(right, 0.97 - side_w, side_w))
    return out


def _render_template(item: OutfitItem, max_w: int, max_h: int, max_scale: float = 3.0) -> Image.Image:
    """The item's garment template, cropped and scaled to fit, on transparency."""
    variant = f"nails_{item.variant}" if item.slot == "nails" else (item.variant or "tee")
    asset = load_template(variant)
    x0, y0, x1, y1 = asset.bbox
    pad = 4
    bw, bh = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad
    ss = 2
    scale = min(max_w / bw, max_h / bh, max_scale) * ss
    w, h = max(1, int(bw * scale)), max(1, int(bh * scale))
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tf = Transform(scale, -(x0 - pad) * scale, -(y0 - pad) * scale)
    tile = pattern_tile(item.pattern, item.color_hex, item.secondary_hex, round(scale, 3)) if item.pattern != "solid" else None
    # thin garments (jewelry) need relatively thicker strokes when blown up
    stroke_scale = 1.0 if bw > 80 else 0.7
    draw_asset(canvas, asset, tf, role_colors(item.color_hex, item.secondary_hex), tile, stroke_scale=stroke_scale)
    return canvas.resize((max(1, w // ss), max(1, h // ss)), Image.Resampling.LANCZOS)


def _render_photo(data: bytes, max_w: int, max_h: int) -> Image.Image:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGBA")
    img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=max(6, img.width // 18), fill=255)
    img.putalpha(mask)
    return img


def _shadow(piece: Image.Image, blur: int = 10) -> Image.Image:
    alpha = piece.split()[-1].point(lambda a: int(a * 0.22))
    sh = Image.new("RGBA", piece.size, (48, 43, 43, 0))
    sh.putalpha(alpha)
    padded = Image.new("RGBA", (piece.width + blur * 4, piece.height + blur * 4), (0, 0, 0, 0))
    padded.paste(sh, (blur * 2, blur * 2), sh)
    return padded.filter(ImageFilter.GaussianBlur(blur))


def render_board(
    outfit: Outfit,
    layout: str = "editorial",
    size: tuple[int, int] = (1000, 1100),
    photo_loader: Callable[[str], bytes | None] | None = None,
    use_photos: bool = True,
) -> Image.Image:
    """The flat-lay board (RGBA). ``photo_loader(wardrobe_item_id)`` returns image bytes or None."""
    W, H = size
    board = Image.new("RGBA", size, (252, 249, 245, 255))
    d = ImageDraw.Draw(board)
    # subtle paper border
    d.rounded_rectangle((6, 6, W - 7, H - 7), radius=22, outline=(232, 218, 210), width=3)
    slots = [it.slot for it in outfit.items]
    boxes = layout_boxes(layout if layout in LAYOUTS else "editorial", slots)
    for it in outfit.items:
        box = boxes.get(it.slot)
        if box is None:
            continue
        bx, by, bw, bh = int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)
        inner_w, inner_h = int(bw * 0.9), int(bh * 0.9)
        piece = None
        if use_photos and photo_loader and it.wardrobe_item_id:
            try:
                data = photo_loader(it.wardrobe_item_id)
                if data:
                    piece = _render_photo(data, inner_w, inner_h)
            except Exception:  # noqa: BLE001 - a broken photo falls back to the template
                piece = None
        if piece is None:
            piece = _render_template(it, inner_w, inner_h, max_scale=2.4 * W / 1000)
        px = bx + (bw - piece.width) // 2
        py = by + (bh - piece.height) // 2
        sh = _shadow(piece)
        off = (sh.width - piece.width) // 2
        board.alpha_composite(sh, (max(0, px - off + 6), max(0, py - off + 10)))
        board.alpha_composite(piece, (px, py))
    return board


def render_png(outfit: Outfit, layout: str = "editorial", photo_loader=None, use_photos: bool = True) -> bytes:
    board = render_board(outfit, layout, photo_loader=photo_loader, use_photos=use_photos)
    img = poster(outfit, board, subtitle="Flat-lay")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_preview(outfit: Outfit, layout: str = "editorial", photo_loader=None, use_photos: bool = True,
                   width: int = 720) -> Image.Image:
    board = render_board(outfit, layout, size=(width, int(width * 1.1)), photo_loader=photo_loader, use_photos=use_photos)
    return board.convert("RGB")
