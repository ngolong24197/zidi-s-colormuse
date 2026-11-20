"""Fabric patterns defined once as primitives, rendered to SVG <pattern> and Pillow tiles."""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw

from src.core.color_convert import hex_to_rgb, lightness, mix, normalize_hex

# primitive: ("rect", x, y, w, h, role, opacity) | ("circle", cx, cy, r, role, opacity)
#            | ("poly", [(x, y), ...], role, opacity)
# role: "sec" (secondary color) or "line" (darker main color)
PATTERNS: dict[str, tuple[int, list[tuple]]] = {
    "striped": (16, [("rect", 0, 0, 16, 6, "sec", 1.0)]),
    "polka dot": (18, [("circle", 4.5, 4.5, 2.6, "sec", 1.0), ("circle", 13.5, 13.5, 2.6, "sec", 1.0)]),
    "plaid": (24, [("rect", 0, 9, 24, 6, "sec", 0.55), ("rect", 9, 0, 6, 24, "sec", 0.55),
                   ("rect", 0, 20, 24, 1.5, "line", 0.8), ("rect", 20, 0, 1.5, 24, "line", 0.8)]),
    "floral": (28, [("circle", 8, 5, 2.6, "sec", 1.0), ("circle", 11, 8, 2.6, "sec", 1.0),
                    ("circle", 8, 11, 2.6, "sec", 1.0), ("circle", 5, 8, 2.6, "sec", 1.0),
                    ("circle", 8, 8, 1.6, "line", 1.0), ("circle", 21, 19, 2.0, "sec", 1.0),
                    ("circle", 23.5, 21.5, 2.0, "sec", 1.0), ("circle", 21, 24, 2.0, "sec", 1.0),
                    ("circle", 18.5, 21.5, 2.0, "sec", 1.0), ("circle", 21, 21.5, 1.2, "line", 1.0)]),
    "animal": (30, [("circle", 6, 7, 4.0, "sec", 0.9), ("circle", 20, 5, 3.0, "sec", 0.9),
                    ("circle", 14, 18, 4.5, "sec", 0.9), ("circle", 26, 24, 3.0, "sec", 0.9),
                    ("circle", 5, 25, 3.0, "sec", 0.9), ("circle", 14, 18, 2.0, "line", 0.6),
                    ("circle", 6, 7, 1.6, "line", 0.6)]),
    "geometric": (20, [("poly", [(10, 3), (17, 10), (10, 17), (3, 10)], "sec", 0.85)]),
    "textured": (8, [("poly", [(0, 8), (8, 0), (8, 1.2), (1.2, 8)], "line", 0.35)]),
}


def pattern_colors(main_hex: str, secondary_hex: str | None) -> dict[str, str]:
    main = normalize_hex(main_hex)
    if secondary_hex:
        sec = normalize_hex(secondary_hex)
    else:
        sec = mix(main, "#302B2B", 0.55) if lightness(main) > 55 else mix(main, "#F8F4EF", 0.6)
    line = mix(main, "#1A1414", 0.45) if lightness(main) > 30 else mix(main, "#FFFFFF", 0.35)
    return {"sec": sec, "line": line, "main": main}


def svg_pattern_def(pattern: str, pattern_id: str, main_hex: str, secondary_hex: str | None, scale: float = 1.0) -> str:
    """An SVG <pattern> element, or '' for solid colors."""
    if pattern not in PATTERNS:
        return ""
    size, prims = PATTERNS[pattern]
    cols = pattern_colors(main_hex, secondary_hex)
    s = size * scale
    parts = [f'<rect width="{s:.2f}" height="{s:.2f}" fill="{cols["main"]}"/>']
    for prim in prims:
        kind = prim[0]
        if kind == "rect":
            _, x, y, w, h, role, op = prim
            parts.append(f'<rect x="{x*scale:.2f}" y="{y*scale:.2f}" width="{w*scale:.2f}" height="{h*scale:.2f}" fill="{cols[role]}" fill-opacity="{op}"/>')
        elif kind == "circle":
            _, cx, cy, r, role, op = prim
            parts.append(f'<circle cx="{cx*scale:.2f}" cy="{cy*scale:.2f}" r="{r*scale:.2f}" fill="{cols[role]}" fill-opacity="{op}"/>')
        else:
            _, pts, role, op = prim
            pts_s = " ".join(f"{x*scale:.2f},{y*scale:.2f}" for x, y in pts)
            parts.append(f'<polygon points="{pts_s}" fill="{cols[role]}" fill-opacity="{op}"/>')
    return (f'<pattern id="{pattern_id}" width="{s:.2f}" height="{s:.2f}" patternUnits="userSpaceOnUse">'
            + "".join(parts) + "</pattern>")


@lru_cache(maxsize=128)
def pattern_tile(pattern: str, main_hex: str, secondary_hex: str | None, scale: float) -> Image.Image | None:
    """Pillow RGB tile for a pattern at ``scale`` pixels per asset unit."""
    if pattern not in PATTERNS:
        return None
    size, prims = PATTERNS[pattern]
    cols = pattern_colors(main_hex, secondary_hex)
    px = max(4, int(round(size * scale)))
    k = px / size
    tile = Image.new("RGBA", (px, px), hex_to_rgb(cols["main"]) + (255,))
    for prim in prims:
        layer = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        kind = prim[0]
        if kind == "rect":
            _, x, y, w, h, role, op = prim
            d.rectangle((x * k, y * k, (x + w) * k - 1, (y + h) * k - 1), fill=hex_to_rgb(cols[role]) + (int(255 * op),))
        elif kind == "circle":
            _, cx, cy, r, role, op = prim
            d.ellipse(((cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k), fill=hex_to_rgb(cols[role]) + (int(255 * op),))
        else:
            _, pts, role, op = prim
            d.polygon([(x * k, y * k) for x, y in pts], fill=hex_to_rgb(cols[role]) + (int(255 * op),))
        tile.alpha_composite(layer)
    return tile.convert("RGB")
