"""Color harmony rules on the HSL color wheel.

Two jobs:
1. ``harmony_palette`` — generate target colors for a rule (complementary,
   analogous, ...) from a base color, snapped to wearable, named library colors.
2. ``classify_relation`` — given two colors, find which harmony relationship
   they form and how cleanly (0..1). This drives the harmony score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from src.core.color_convert import (
    color_distance,
    hex_to_hsl,
    hsl_to_hex,
    hue_difference,
    lightness,
    normalize_hex,
)
from src.core.color_library import NEUTRALS, METALLICS, NamedColor, is_neutral_hex, nearest_colors, COLOR_LIBRARY
from src.i18n import N_

RULES: tuple[str, ...] = (
    "complementary",
    "analogous",
    "triadic",
    "split complementary",
    "monochromatic",
    "neutral",
    "contrast",
)

RULE_DESCRIPTIONS: dict[str, str] = {
    "complementary": N_("Opposite on the color wheel — maximum vibrancy; each color intensifies the other."),
    "analogous": N_("Neighbours on the color wheel — calm, cohesive and effortless."),
    "triadic": N_("Three colors evenly spaced around the wheel — playful and balanced."),
    "split complementary": N_("The two neighbours of the complement — vivid but easier to wear than a straight complement."),
    "monochromatic": N_("One hue in different depths — elongating, polished and refined."),
    "neutral": N_("Grounding neutrals that let the main color lead."),
    "contrast": N_("A deliberate light/dark contrast — crisp, graphic and confident."),
}

# ideal hue angle, tolerance (deg), base quality
_RELATION_PROFILE: dict[str, tuple[float, float, float]] = {
    "monochromatic": (0.0, 10.0, 0.92),
    "analogous": (30.0, 16.0, 0.95),
    "triadic": (120.0, 18.0, 0.86),
    "split complementary": (150.0, 12.0, 0.88),
    "complementary": (180.0, 14.0, 0.90),
}


@dataclass(frozen=True)
class Relation:
    rule: str
    quality: float  # 0..1
    hue_angle: float


@dataclass(frozen=True)
class PaletteColor:
    hex: str  # snapped library hex
    name: str
    target_hex: str  # exact computed target
    rule: str
    note: str


def _wearable(h: float, s: float, l: float) -> tuple[float, float, float]:
    """Pull extreme saturation/lightness into ranges that exist in real fabrics."""
    return h % 360, min(max(s, 0.18), 0.78), min(max(l, 0.18), 0.86)


def rule_hues(base_hue: float, rule: str) -> list[float]:
    if rule == "complementary":
        return [base_hue + 180]
    if rule == "analogous":
        return [base_hue - 30, base_hue + 30]
    if rule == "triadic":
        return [base_hue + 120, base_hue + 240]
    if rule == "split complementary":
        return [base_hue + 150, base_hue + 210]
    return []


def harmony_targets(base_hex: str, rule: str) -> list[str]:
    """Exact target hex colors for ``rule`` (before snapping to the library)."""
    if rule not in RULES:
        raise ValueError(f"Unknown harmony rule: {rule}")
    h, s, l = hex_to_hsl(normalize_hex(base_hex))
    if rule in ("complementary", "analogous", "triadic", "split complementary"):
        # Low-saturation bases have an unstable hue; give them a usable minimum
        s_eff = max(s, 0.35)
        return [hsl_to_hex(_wearable(hh, s_eff, l)) for hh in rule_hues(h, rule)]
    if rule == "monochromatic":
        steps = (-0.30, -0.15, 0.15, 0.30)
        out = []
        for d in steps:
            nl = min(max(l + d, 0.12), 0.92)
            if abs(nl - l) >= 0.08:
                out.append(hsl_to_hex((h, s, nl)))
        return out
    if rule == "contrast":
        # Opposite lightness, same temperature family, muted
        target_l = 0.15 if l > 0.5 else 0.9
        return [hsl_to_hex((h, min(s, 0.25), target_l)), "#141414" if l > 0.5 else "#FBFBF9"]
    # neutral
    return [c.hex for c in _best_neutrals(base_hex, 4)]


def _best_neutrals(base_hex: str, n: int) -> list[NamedColor]:
    """Neutrals that suit the base: matching undertone and some lightness contrast."""
    from src.core.color_library import undertone_of

    base_under = undertone_of(base_hex)
    base_l = lightness(base_hex)
    scored = []
    for c in NEUTRALS:
        if c.family == "blue" and c.name not in ("Navy", "Denim"):
            continue
        under = c.undertone
        tone = 1.0 if under in (base_under, "neutral") or base_under == "neutral" else 0.7
        dl = abs(c.lab[0] - base_l)
        contrast = 1.0 - abs(dl - 40) / 60
        scored.append((tone * 0.6 + max(contrast, 0) * 0.4, c.name, c))
    scored.sort(key=lambda t: (-t[0], t[1]))
    picked: list[NamedColor] = []
    families: set[str] = set()
    for _, _, c in scored:
        if c.family in families and len(picked) < n - 1:
            continue
        picked.append(c)
        families.add(c.family)
        if len(picked) == n:
            break
    return picked


def harmony_palette(base_hex: str, rule: str) -> list[PaletteColor]:
    """Rule targets snapped to the nearest distinct named library colors."""
    base_hex = normalize_hex(base_hex)
    out: list[PaletteColor] = []
    seen = {base_hex}
    pool = tuple(c for c in COLOR_LIBRARY if c.family != "metallic")
    for target in harmony_targets(base_hex, rule):
        for cand, _dist in nearest_colors(target, 4, pool):
            if cand.hex not in seen and color_distance(cand.hex, base_hex) > 4:
                seen.add(cand.hex)
                out.append(PaletteColor(cand.hex, cand.name, target, rule, RULE_DESCRIPTIONS[rule]))
                break
    return out


def all_palettes(base_hex: str) -> dict[str, list[PaletteColor]]:
    return {rule: harmony_palette(base_hex, rule) for rule in RULES}


def classify_relation(hex1: str, hex2: str) -> Relation:
    """Which harmony two colors form, and how cleanly (0..1)."""
    return _classify(normalize_hex(hex1), normalize_hex(hex2))


@lru_cache(maxsize=16384)
def _classify(hex1: str, hex2: str) -> Relation:
    n1, n2 = is_neutral_hex(hex1), is_neutral_hex(hex2)
    h1, s1, l1 = hex_to_hsl(hex1)
    h2, s2, l2 = hex_to_hsl(hex2)
    d = hue_difference(h1, h2)
    if n1 and n2:
        return Relation("neutral", 0.86, d)
    if n1 or n2:
        return Relation("neutral", 0.90, d)

    best_rule, best_q = "analogous", 0.0
    for rule, (angle, tol, base_q) in _RELATION_PROFILE.items():
        q = base_q * math.exp(-(((d - angle) / tol) ** 2))
        if q > best_q:
            best_rule, best_q = rule, q
    # Hue gaps between named harmonies (≈ 55–95°) read as slightly discordant
    best_q = max(best_q, 0.38)
    if best_rule == "monochromatic":
        if color_distance(hex1, hex2) < 5:
            best_q = 0.72  # practically identical: matching rather than toning
        elif abs(l1 - l2) > 0.12:
            best_q = max(best_q, 0.9)
    # Muted colors are forgiving: low saturation softens any hue clash
    softness = 1 - min(s1, s2)
    best_q = best_q + (0.85 - best_q) * max(0.0, softness - 0.55) if best_q < 0.85 else best_q
    return Relation(best_rule, round(min(best_q, 1.0), 4), d)


def contrast_rule_applies(hex1: str, hex2: str) -> bool:
    return abs(lightness(hex1) - lightness(hex2)) >= 45


def metallic_for(base_hex: str) -> NamedColor:
    """Gold for warm colors, silver for cool, rose gold for pinks."""
    from src.core.color_library import get_color, undertone_of

    hh, _, _ = hex_to_hsl(base_hex)
    tone = undertone_of(base_hex)
    if tone == "warm" and (hh < 15 or hh > 330) and lightness(base_hex) > 55:
        return get_color("Rose Gold") or METALLICS[0]
    if tone == "cool":
        return get_color("Silver") or METALLICS[0]
    return get_color("Gold") or METALLICS[0]
