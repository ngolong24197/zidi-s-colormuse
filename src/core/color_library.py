"""The internal fashion color library.

This list is the single source of truth: ``scripts/generate_color_seed.py``
renders it into ``database/seed_colors.sql`` for the Supabase ``colors`` table.

Each entry: (name, hex, family, is_neutral)
``family`` groups related shades (used for explanations and filtering).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from src.core.color_convert import (
    delta_e_2000,
    hex_to_hsl,
    hex_to_lab,
    lab_to_lch,
    normalize_hex,
)


@dataclass(frozen=True)
class NamedColor:
    name: str
    hex: str
    family: str
    is_neutral: bool

    @property
    def lab(self) -> tuple[float, float, float]:
        return _lab(self.hex)

    @property
    def hsl(self) -> tuple[float, float, float]:
        return hex_to_hsl(self.hex)

    @property
    def undertone(self) -> str:
        return undertone_of(self.hex)

    @property
    def slug(self) -> str:
        return self.name.lower().replace(" ", "-")


_RAW: list[tuple[str, str, str, bool]] = [
    # --- Neutrals: whites & creams
    ("Optic White", "#FBFBF9", "white", True),
    ("Ivory", "#F8F4EF", "white", True),
    ("Cream", "#F3E9D2", "white", True),
    ("Ecru", "#E9DFC9", "white", True),
    ("Oatmeal", "#DDD1BC", "beige", True),
    # --- Neutrals: beiges, browns
    ("Sand", "#D8C3A5", "beige", True),
    ("Beige", "#D9C4A8", "beige", True),
    ("Nude", "#E3BFA3", "beige", True),
    ("Taupe", "#C8AD91", "beige", True),
    ("Greige", "#B8AD9E", "beige", True),
    ("Khaki", "#BFAF85", "beige", True),
    ("Camel", "#C19A6B", "brown", True),
    ("Cognac", "#9A5B2E", "brown", True),
    ("Tan", "#C69C72", "brown", True),
    ("Mocha", "#7B5B4C", "brown", True),
    ("Chocolate", "#4E3226", "brown", True),
    ("Espresso", "#3B2A24", "brown", True),
    # --- Neutrals: grays & black
    ("Dove Gray", "#D3D0CB", "gray", True),
    ("Silver Gray", "#B7B8B6", "gray", True),
    ("Heather Gray", "#9C9A98", "gray", True),
    ("Slate", "#6C737A", "gray", True),
    ("Charcoal", "#302B2B", "gray", True),
    ("Graphite", "#45474B", "gray", True),
    ("Black", "#141414", "black", True),
    # --- Neutral-like blues
    ("Navy", "#1F2A44", "blue", True),
    ("Midnight", "#191D33", "blue", True),
    ("Denim", "#4A6584", "blue", True),
    ("Light Denim", "#8EA7C1", "blue", True),
    ("Olive", "#6B6B3A", "green", True),
    # --- Reds
    ("Cherry Red", "#B3112E", "red", False),
    ("Scarlet", "#D0312D", "red", False),
    ("Tomato", "#E2533C", "red", False),
    ("Brick", "#9C3B2E", "red", False),
    ("Wine", "#6A1E2D", "red", False),
    ("Burgundy", "#713E4A", "red", False),
    ("Oxblood", "#5C1F22", "red", False),
    ("Crimson", "#A4123F", "red", False),
    # --- Pinks
    ("Blush", "#E8C9C5", "pink", False),
    ("Ballet Pink", "#F2D3D4", "pink", False),
    ("Dusty Rose", "#B77E79", "pink", False),
    ("Rose", "#D98695", "pink", False),
    ("Mauve", "#A98095", "pink", False),
    ("Bubblegum", "#F4A6C1", "pink", False),
    ("Hot Pink", "#E0457B", "pink", False),
    ("Fuchsia", "#C2185B", "pink", False),
    ("Raspberry", "#B0305C", "pink", False),
    ("Peony", "#E3829B", "pink", False),
    # --- Oranges & corals
    ("Coral", "#F27F6B", "orange", False),
    ("Peach", "#F6C1A6", "orange", False),
    ("Apricot", "#F1A97A", "orange", False),
    ("Tangerine", "#F28C28", "orange", False),
    ("Burnt Orange", "#C25B26", "orange", False),
    ("Rust", "#A0472A", "orange", False),
    ("Terracotta", "#C46A4F", "orange", False),
    ("Salmon", "#EE9A86", "orange", False),
    # --- Yellows
    ("Butter", "#F6E3A1", "yellow", False),
    ("Lemon", "#F4E04D", "yellow", False),
    ("Sunflower", "#F2B630", "yellow", False),
    ("Mustard", "#CC9A2B", "yellow", False),
    ("Ochre", "#B5832F", "yellow", False),
    ("Champagne", "#EBD9B4", "yellow", False),
    # --- Greens
    ("Mint", "#BFE3CF", "green", False),
    ("Pistachio", "#B8CF96", "green", False),
    ("Sage", "#A3B18A", "green", False),
    ("Eucalyptus", "#7FA393", "green", False),
    ("Moss", "#77814A", "green", False),
    ("Kelly Green", "#2E9E4F", "green", False),
    ("Emerald", "#11795A", "green", False),
    ("Forest Green", "#2D4F3A", "green", False),
    ("Hunter Green", "#355E3B", "green", False),
    ("Lime", "#BFD641", "green", False),
    ("Teal", "#1F7A7A", "green", False),
    # --- Blues
    ("Powder Blue", "#BCD3E6", "blue", False),
    ("Baby Blue", "#A9CBEA", "blue", False),
    ("Sky Blue", "#7DB5E3", "blue", False),
    ("Cornflower", "#6F8FD8", "blue", False),
    ("Cerulean", "#2A7AB8", "blue", False),
    ("Cobalt", "#1F4FB4", "blue", False),
    ("Royal Blue", "#2A3FA0", "blue", False),
    ("Sapphire", "#1D3B78", "blue", False),
    ("Turquoise", "#3CC2C0", "blue", False),
    ("Aqua", "#86D9D2", "blue", False),
    ("Steel Blue", "#5B7C99", "blue", False),
    ("Petrol", "#1F4E5F", "blue", False),
    # --- Purples
    ("Lavender", "#C9B8DD", "purple", False),
    ("Lilac", "#B9A2CC", "purple", False),
    ("Wisteria", "#9C87C1", "purple", False),
    ("Orchid", "#B06AB3", "purple", False),
    ("Violet", "#7A4FA3", "purple", False),
    ("Plum", "#5E2F52", "purple", False),
    ("Eggplant", "#3F2541", "purple", False),
    ("Amethyst", "#8E5CA8", "purple", False),
    # --- Metallics (jewelry & accents)
    ("Gold", "#C9A44C", "metallic", True),
    ("Rose Gold", "#C99584", "metallic", True),
    ("Silver", "#BFC1C2", "metallic", True),
    ("Bronze", "#A0703E", "metallic", True),
    ("Pearl", "#EEE7DC", "metallic", True),
]

COLOR_LIBRARY: tuple[NamedColor, ...] = tuple(
    NamedColor(name, normalize_hex(hx), family, neutral) for name, hx, family, neutral in _RAW
)

_BY_NAME = {c.name.lower(): c for c in COLOR_LIBRARY}

FAMILIES: tuple[str, ...] = tuple(dict.fromkeys(c.family for c in COLOR_LIBRARY))
METALLICS: tuple[NamedColor, ...] = tuple(c for c in COLOR_LIBRARY if c.family == "metallic")
NEUTRALS: tuple[NamedColor, ...] = tuple(
    c for c in COLOR_LIBRARY if c.is_neutral and c.family != "metallic"
)


@lru_cache(maxsize=4096)
def _lab(hex_value: str) -> tuple[float, float, float]:
    return hex_to_lab(hex_value)


def get_color(name: str) -> NamedColor | None:
    return _BY_NAME.get(name.strip().lower())


def nearest_colors(hex_value: str, n: int = 1, pool: tuple[NamedColor, ...] | None = None) -> list[tuple[NamedColor, float]]:
    """Library colors closest to ``hex_value`` by CIEDE2000, with distances."""
    lab = _lab(normalize_hex(hex_value))
    candidates = pool if pool is not None else COLOR_LIBRARY
    scored = sorted(((c, delta_e_2000(lab, c.lab)) for c in candidates), key=lambda t: t[1])
    return scored[:n]


@lru_cache(maxsize=4096)
def nearest_color(hex_value: str) -> NamedColor:
    return nearest_colors(hex_value, 1)[0][0]


def color_name(hex_value: str) -> str:
    """Human-friendly name for any hex (nearest library color)."""
    return nearest_color(normalize_hex(hex_value)).name


@lru_cache(maxsize=4096)
def is_neutral_hex(hex_value: str) -> bool:
    """A color is neutral if it is low-chroma, or very close to a library neutral."""
    hx = normalize_hex(hex_value)
    near, dist = nearest_colors(hx, 1)[0]
    if dist < 4:
        return near.is_neutral
    L, C, _ = lab_to_lch(_lab(hx))
    if C < 9:
        return True
    return near.is_neutral and dist < 6


@lru_cache(maxsize=4096)
def undertone_of(hex_value: str) -> str:
    """'warm', 'cool' or 'neutral' based on hue/chroma."""
    L, C, h = lab_to_lch(_lab(normalize_hex(hex_value)))
    if C < 6:
        return "neutral"
    # Lab hue: ~0-100 reds/oranges/yellows (warm), ~180-320 greens-blues-purples (cool)
    if h < 100 or h >= 345:
        return "warm"
    if 100 <= h < 140:
        return "warm" if C > 25 else "neutral"
    return "cool"
