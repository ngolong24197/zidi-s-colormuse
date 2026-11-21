"""Deterministic, explainable scoring.

Every component returns a value in 0..1 plus a short human explanation.
Components (default weights, configurable in Settings):

    harmony 35% · contrast & balance 20% · category 15%
    occasion 10% · style 10% · personal preference 10%
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache

from src.core.color_convert import chroma, color_distance, hex_to_hsl, hue_difference, lightness, normalize_hex
from src.core.color_library import color_name, is_neutral_hex, nearest_color, undertone_of
from src.core.harmony import RULE_DESCRIPTIONS, classify_relation
from src.i18n import _, cname, label
from src.models.domain import DEFAULT_WEIGHTS, UserPreferences


def _bell(x: float, ideal: float, tolerance: float) -> float:
    """1 at ``ideal``, smoothly decaying with distance (gaussian)."""
    return math.exp(-(((x - ideal) / tolerance) ** 2))


# ---------------------------------------------------------------- profiles

@dataclass(frozen=True)
class ColorProfile:
    """Preferred perceptual lightness/chroma plus families that suit or clash."""

    ideal_l: float | None
    tol_l: float
    ideal_c: float
    tol_c: float
    bonus_families: tuple[str, ...] = ()
    bonus_names: tuple[str, ...] = ()
    avoid_names: tuple[str, ...] = ()
    neutral_bonus: float = 0.0
    metallic_bonus: float = 0.0
    warm_bonus: float = 0.0
    summary: str = ""


OCCASION_PROFILES: dict[str, ColorProfile] = {
    "casual": ColorProfile(60, 35, 30, 35, ("blue", "white", "beige"), ("Denim", "Light Denim"), summary="relaxed, easy colors"),
    "office": ColorProfile(None, 0, 12, 22, ("gray", "beige", "blue", "white", "brown"), ("Navy", "Camel", "Charcoal"), neutral_bonus=0.15, summary="polished, muted tones"),
    "date night": ColorProfile(35, 22, 45, 25, ("red", "black", "pink"), ("Burgundy", "Wine", "Black", "Cherry Red"), summary="rich, romantic depth"),
    "party": ColorProfile(None, 0, 60, 30, ("metallic", "pink", "red", "purple"), ("Fuchsia", "Emerald", "Cobalt", "Gold"), metallic_bonus=0.15, summary="bold, celebratory colors"),
    "wedding guest": ColorProfile(62, 25, 35, 22, ("green", "blue", "purple", "pink"), ("Sage", "Dusty Rose", "Lavender", "Powder Blue", "Emerald"), avoid_names=("Optic White", "Ivory", "Cream", "Ecru", "Pearl"), summary="soft pastels and jewel tones (never bridal white)"),
    "travel": ColorProfile(45, 25, 18, 20, ("blue", "gray", "beige", "brown", "black"), ("Navy", "Olive", "Camel"), neutral_bonus=0.12, summary="practical, forgiving neutrals"),
    "beach": ColorProfile(78, 18, 35, 30, ("white", "blue", "orange", "yellow"), ("Optic White", "Turquoise", "Coral", "Aqua", "Sand"), summary="light, sunny colors"),
    "formal": ColorProfile(28, 20, 30, 25, ("black", "blue", "red", "metallic"), ("Black", "Navy", "Midnight", "Burgundy", "Emerald", "Sapphire"), metallic_bonus=0.12, summary="deep, elegant shades"),
    "dinner": ColorProfile(45, 25, 30, 25, ("red", "brown", "blue", "green"), ("Wine", "Camel", "Navy", "Forest Green"), summary="warm, refined tones"),
    "interview": ColorProfile(None, 0, 8, 16, ("gray", "blue", "white", "black"), ("Navy", "Charcoal", "Optic White", "Slate"), neutral_bonus=0.2, summary="trustworthy neutrals and navy"),
    "daily errands": ColorProfile(55, 30, 22, 28, ("blue", "gray", "beige", "white"), ("Denim", "Heather Gray"), summary="comfortable everyday colors"),
}

STYLE_PROFILES: dict[str, ColorProfile] = {
    "classic": ColorProfile(None, 0, 18, 22, ("blue", "white", "black", "beige"), ("Navy", "Camel", "Cherry Red", "Optic White"), neutral_bonus=0.1, summary="timeless navy, camel, red and white"),
    "minimalist": ColorProfile(None, 0, 4, 12, ("white", "gray", "black", "beige"), ("Black", "Optic White", "Oatmeal"), neutral_bonus=0.2, summary="quiet neutrals"),
    "romantic": ColorProfile(76, 18, 28, 20, ("pink", "purple", "white"), ("Blush", "Dusty Rose", "Lavender", "Ballet Pink"), summary="soft pastels and blush"),
    "chic": ColorProfile(None, 0, 14, 22, ("black", "white", "brown", "beige"), ("Black", "Camel", "Ivory", "Burgundy"), neutral_bonus=0.12, summary="neutrals with one refined accent"),
    "bohemian": ColorProfile(52, 22, 35, 20, ("orange", "brown", "yellow", "green"), ("Rust", "Terracotta", "Mustard", "Olive", "Sage"), warm_bonus=0.12, summary="warm, earthy tones"),
    "edgy": ColorProfile(25, 18, 20, 30, ("black", "gray", "red"), ("Black", "Charcoal", "Oxblood"), summary="dark, high-contrast colors"),
    "sporty": ColorProfile(None, 0, 55, 28, ("white", "blue", "gray"), ("Optic White", "Cobalt", "Heather Gray", "Kelly Green"), summary="fresh brights and white"),
    "glam": ColorProfile(35, 22, 55, 22, ("metallic", "purple", "red", "green"), ("Emerald", "Sapphire", "Fuchsia", "Gold", "Black"), metallic_bonus=0.18, summary="jewel tones and metallics"),
    "preppy": ColorProfile(None, 0, 40, 25, ("blue", "white", "green", "red"), ("Navy", "Kelly Green", "Optic White", "Cherry Red", "Baby Blue"), summary="crisp navy, white and bright accents"),
}


def profile_fit(hex_value: str, profile: ColorProfile) -> float:
    return _profile_fit(normalize_hex(hex_value), profile)


@lru_cache(maxsize=16384)
def _profile_fit(hx: str, profile: ColorProfile) -> float:
    L, C = lightness(hx), chroma(hx)
    lc = _bell(L, profile.ideal_l, profile.tol_l) if profile.ideal_l is not None else 1.0
    cc = _bell(C, profile.ideal_c, profile.tol_c)
    score = 0.35 + 0.35 * lc * cc + 0.15 * cc + 0.15 * lc
    near = nearest_color(hx)
    if near.name in profile.bonus_names:
        score += 0.15
    elif near.family in profile.bonus_families:
        score += 0.08
    if near.name in profile.avoid_names:
        score -= 0.6
    if near.family == "metallic":
        score += profile.metallic_bonus
    elif is_neutral_hex(hx):
        score += profile.neutral_bonus
    if profile.warm_bonus and undertone_of(hx) == "warm":
        score += profile.warm_bonus
    return max(0.0, min(1.0, score))


def occasion_fit(hex_value: str, occasion: str | None) -> tuple[float, str]:
    if not occasion or occasion not in OCCASION_PROFILES:
        return 0.75, ""
    p = OCCASION_PROFILES[occasion]
    s = profile_fit(hex_value, p)
    name, occ, summary = cname(hex_value), label("occasion", occasion).lower(), _(p.summary)
    if nearest_color(hex_value).name in p.avoid_names:
        return s, _("{name} is best avoided for {occasion} ({summary}).", name=name, occasion=occ, summary=summary)
    verdict = _("ideal") if s >= 0.8 else _("a good fit") if s >= 0.6 else _("a bolder choice")
    return s, _("For {occasion}, {name} is {verdict} — the occasion favours {summary}.",
                occasion=occ, name=name, verdict=verdict, summary=summary)


def style_fit(hex_value: str, style: str | None) -> tuple[float, str]:
    if not style or style not in STYLE_PROFILES:
        return 0.75, ""
    p = STYLE_PROFILES[style]
    s = profile_fit(hex_value, p)
    verdict = _("signature") if s >= 0.8 else _("compatible") if s >= 0.6 else _("an unexpected twist")
    return s, _("In a {style} look ({summary}), {name} is {verdict}.", style=label("style", style).lower(),
                summary=_(p.summary), name=cname(hex_value), verdict=verdict)


def preference_fit(hex_value: str, prefs: UserPreferences | None) -> tuple[float, str]:
    if prefs is None or (not prefs.favorite_colors and not prefs.disliked_colors):
        return 0.7, ""

    def closeness(colors: list[str]) -> tuple[float, str | None]:
        best, best_hex = 0.0, None
        for c in colors:
            d = color_distance(hex_value, c)
            v = 1.0 if d <= 8 else max(0.0, 1 - (d - 8) / 22)
            if v > best:
                best, best_hex = v, c
        return best, best_hex

    fav, fav_hex = closeness(prefs.favorite_colors)
    dis, dis_hex = closeness(prefs.disliked_colors)
    score = max(0.0, min(1.0, 0.6 + 0.4 * fav - 0.6 * dis))
    if dis >= 0.5 and dis_hex:
        return score, _("Close to {name}, which you prefer to avoid.", name=cname(dis_hex))
    if fav >= 0.5 and fav_hex:
        return score, _("Echoes one of your favourite colors ({name}).", name=cname(fav_hex))
    return score, ""


def contrast_balance(hex1: str, hex2: str) -> tuple[float, str]:
    """Lightness contrast plus saturation balance between two colors."""
    l1, l2 = lightness(hex1), lightness(hex2)
    c1, c2 = chroma(hex1), chroma(hex2)
    dl = abs(l1 - l2)
    if dl < 8:
        lc = 0.55 + 0.35 * (dl / 8)
        msg = _("Very similar depth — a soft, tonal effect.")
    elif dl <= 55:
        lc = 0.9 + 0.1 * _bell(dl, 32, 20)
        msg = _("Comfortable light-to-dark contrast keeps the look balanced.")
    else:
        lc = 0.82
        msg = _("Strong light/dark contrast — crisp and graphic.")
    both_loud = c1 > 55 and c2 > 55
    if both_loud:
        rel = classify_relation(hex1, hex2)
        if rel.rule not in ("monochromatic", "analogous"):
            lc *= 0.75
            msg += " " + _("Both colors are intense, so let one lead and keep the rest quiet.")
    return max(0.0, min(1.0, lc)), msg


# category -> how forgiving the slot is with different color types
_CATEGORY_RULES: dict[str, dict[str, float]] = {
    # neutral, metallic, muted, bright
    "tops": {"neutral": 0.9, "metallic": 0.55, "muted": 0.9, "bright": 0.85},
    "shirts": {"neutral": 0.92, "metallic": 0.5, "muted": 0.9, "bright": 0.85},
    "bottoms": {"neutral": 0.97, "metallic": 0.45, "muted": 0.85, "bright": 0.68},
    "pants": {"neutral": 0.97, "metallic": 0.4, "muted": 0.85, "bright": 0.66},
    "skirts": {"neutral": 0.93, "metallic": 0.6, "muted": 0.88, "bright": 0.75},
    "dresses": {"neutral": 0.85, "metallic": 0.6, "muted": 0.9, "bright": 0.85},
    "outerwear": {"neutral": 1.0, "metallic": 0.35, "muted": 0.85, "bright": 0.6},
    "shoes": {"neutral": 1.0, "metallic": 0.8, "muted": 0.8, "bright": 0.7},
    "bags": {"neutral": 1.0, "metallic": 0.75, "muted": 0.82, "bright": 0.72},
    "handbags": {"neutral": 1.0, "metallic": 0.75, "muted": 0.82, "bright": 0.72},
    "jewelry": {"neutral": 0.55, "metallic": 1.0, "muted": 0.6, "bright": 0.65},
    "accessories": {"neutral": 0.85, "metallic": 0.9, "muted": 0.85, "bright": 0.9},
    "scarves": {"neutral": 0.82, "metallic": 0.5, "muted": 0.9, "bright": 0.92},
    "belts": {"neutral": 1.0, "metallic": 0.85, "muted": 0.75, "bright": 0.6},
    "hats": {"neutral": 0.95, "metallic": 0.4, "muted": 0.85, "bright": 0.7},
    "nails": {"neutral": 0.95, "metallic": 0.82, "muted": 0.9, "bright": 0.86},
}

_CATEGORY_NOTES: dict[str, dict[str, str]] = {
    "neutral": {"default": "Neutrals are the easiest choice here and stretch across many outfits.",
                "nails": "A neutral polish is effortlessly chic and never clashes."},
    "metallic": {"jewelry": "Metallic finishes are the natural choice for jewelry.",
                 "nails": "A metallic or shimmer polish adds a festive glint.",
                 "default": "A metallic finish adds polish as an accent."},
    "muted": {"default": "A muted tone keeps this piece versatile."},
    "bright": {"outerwear": "A bright coat becomes the statement of every outfit.",
               "default": "A bright shade here works as a statement accent."},
}


def color_kind(hex_value: str) -> str:
    near = nearest_color(normalize_hex(hex_value))
    if near.family == "metallic" and color_distance(hex_value, near.hex) < 10:
        return "metallic"
    if is_neutral_hex(hex_value):
        return "neutral"
    return "bright" if chroma(hex_value) > 50 else "muted"


def category_fit(hex_value: str, category: str) -> tuple[float, str]:
    rules = _CATEGORY_RULES.get(category, _CATEGORY_RULES["tops"])
    kind = color_kind(hex_value)
    notes = _CATEGORY_NOTES[kind]
    return rules[kind], _(notes.get(category, notes["default"]))


# ---------------------------------------------------------------- results

@dataclass
class ScoreBreakdown:
    components: dict[str, float]
    weights: dict[str, float]
    explanations: list[str] = field(default_factory=list)
    rule: str | None = None

    @property
    def total(self) -> float:
        """0..100"""
        return round(100 * sum(self.components[k] * self.weights.get(k, 0) for k in self.components), 1)

    def as_percentages(self) -> dict[str, int]:
        return {k: int(round(v * 100)) for k, v in self.components.items()}


def weights_from(prefs: UserPreferences | None) -> dict[str, float]:
    if prefs is None:
        total = sum(DEFAULT_WEIGHTS.values())
        return {k: v / total for k, v in DEFAULT_WEIGHTS.items()}
    return prefs.normalized_weights()


def score_pair(
    base_hex: str,
    candidate_hex: str,
    candidate_category: str,
    *,
    occasion: str | None = None,
    style: str | None = None,
    prefs: UserPreferences | None = None,
    base_secondary: list[str] | None = None,
    base_pattern: str = "solid",
    candidate_pattern: str = "solid",
) -> ScoreBreakdown:
    """Score wearing ``candidate`` (in ``candidate_category``) with ``base``."""
    base_hex, candidate_hex = normalize_hex(base_hex), normalize_hex(candidate_hex)
    rel = classify_relation(base_hex, candidate_hex)
    harmony = rel.quality
    cand_name, base_name = cname(candidate_hex), cname(base_hex)
    if rel.rule == "neutral":
        desc = _(RULE_DESCRIPTIONS["neutral"])
        harmony_msg = _("{a} and {b}: a neutral pairing — {desc}", a=cand_name, b=base_name,
                        desc=desc[:1].lower() + desc[1:])
    else:
        harmony_msg = _("{rule}: {a} and {b} sit {angle}° apart on the color wheel. {desc}",
                        rule=label("rule", rel.rule), a=cand_name, b=base_name,
                        angle=f"{rel.hue_angle:.0f}", desc=_(RULE_DESCRIPTIONS[rel.rule]))
    # Echoing a secondary color of a printed base ties the outfit together
    for sec in base_secondary or []:
        if color_distance(sec, candidate_hex) < 12:
            harmony = min(1.0, harmony + 0.08)
            harmony_msg += " " + _("It also picks up the {name} in your piece.", name=cname(sec))
            break

    contrast, contrast_msg = contrast_balance(base_hex, candidate_hex)
    category, category_msg = category_fit(candidate_hex, candidate_category)
    if base_pattern != "solid" and candidate_pattern != "solid":
        category *= 0.7
        category_msg += " " + _("Two patterns compete — keep this piece solid.")
    occ, occ_msg = occasion_fit(candidate_hex, occasion)
    sty, sty_msg = style_fit(candidate_hex, style)
    pref, pref_msg = preference_fit(candidate_hex, prefs)

    explanations = [m for m in (harmony_msg, contrast_msg, category_msg, occ_msg, sty_msg, pref_msg) if m]
    return ScoreBreakdown(
        components={
            "harmony": harmony,
            "contrast": contrast,
            "category": category,
            "occasion": occ,
            "style": sty,
            "preference": pref,
        },
        weights=weights_from(prefs),
        explanations=explanations,
        rule=rel.rule,
    )


COMPONENT_LABELS: dict[str, str] = {
    "harmony": "Color harmony",
    "contrast": "Contrast & balance",
    "category": "Category fit",
    "occasion": "Occasion",
    "style": "Style",
    "preference": "Your taste",
}


def hue_family_count(colors: list[str]) -> int:
    """Number of distinct non-neutral hue groups (30° buckets merged by proximity)."""
    hues = sorted(hex_to_hsl(c)[0] for c in colors if not is_neutral_hex(c))
    groups: list[float] = []
    for h in hues:
        if not groups or min(hue_difference(h, g) for g in groups) > 25:
            groups.append(h)
    return len(groups)
