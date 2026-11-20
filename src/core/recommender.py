"""Color Matcher: ranked, explained color recommendations per clothing category."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.color_convert import normalize_hex, shade_of
from src.core.color_library import COLOR_LIBRARY, NamedColor, get_color
from src.core.scoring import ScoreBreakdown, score_pair
from src.models.domain import UserPreferences, WardrobeItem

RECOMMEND_CATEGORIES: tuple[str, ...] = (
    "shirts", "skirts", "pants", "dresses", "shoes", "handbags", "jewelry", "accessories", "outerwear",
)

RECOMMEND_LABELS: dict[str, str] = {
    "shirts": "Shirts & tops", "skirts": "Skirts", "pants": "Pants", "dresses": "Dresses",
    "shoes": "Shoes", "handbags": "Handbags", "jewelry": "Jewelry", "accessories": "Accessories",
    "outerwear": "Outerwear",
}

# Which wardrobe categories satisfy each recommendation category
RECOMMEND_TO_WARDROBE: dict[str, tuple[str, tuple[str, ...] | None]] = {
    "shirts": ("tops", None),
    "skirts": ("bottoms", ("Mini skirt", "Midi skirt", "Maxi skirt")),
    "pants": ("bottoms", ("Trousers", "Jeans", "Wide-leg pants", "Shorts")),
    "dresses": ("dresses", None),
    "shoes": ("shoes", None),
    "handbags": ("bags", None),
    "jewelry": ("jewelry", None),
    "accessories": ("accessories", None),
    "outerwear": ("outerwear", None),
}

# Base category -> recommendation categories that don't make sense with it
_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "tops": ("shirts", "dresses"),
    "shirts": ("shirts", "dresses"),
    "bottoms": ("skirts", "pants", "dresses"),
    "skirts": ("skirts", "pants", "dresses"),
    "pants": ("skirts", "pants", "dresses"),
    "dresses": ("shirts", "skirts", "pants", "dresses"),
    "outerwear": ("outerwear",),
    "shoes": ("shoes",),
    "bags": ("handbags",),
    "handbags": ("handbags",),
    "jewelry": ("jewelry",),
}

_GEM_TONES = ("Emerald", "Sapphire", "Crimson", "Amethyst", "Turquoise", "Pearl")


@dataclass
class MatchRequest:
    base_hex: str
    base_category: str = "tops"
    secondary: list[str] = field(default_factory=list)
    pattern: str = "solid"
    shade: str | None = None
    occasion: str | None = None
    style: str | None = None
    shade_filter: str | None = None  # restrict suggestions to light/medium/dark
    prefs: UserPreferences | None = None

    def __post_init__(self) -> None:
        self.base_hex = normalize_hex(self.base_hex)
        self.secondary = [normalize_hex(s) for s in self.secondary]
        if self.shade is None:
            self.shade = shade_of(self.base_hex)


@dataclass
class Recommendation:
    category: str
    hex: str
    name: str
    score: float
    rule: str | None
    breakdown: ScoreBreakdown
    wardrobe_item: WardrobeItem | None = None

    @property
    def explanations(self) -> list[str]:
        return self.breakdown.explanations


def target_categories(base_category: str) -> list[str]:
    excluded = _EXCLUSIONS.get(base_category, ())
    return [c for c in RECOMMEND_CATEGORIES if c not in excluded]


def candidate_pool(category: str) -> tuple[NamedColor, ...]:
    if category == "jewelry":
        gems = tuple(c for name in _GEM_TONES if (c := get_color(name)))
        return tuple(c for c in COLOR_LIBRARY if c.family == "metallic") + gems
    if category in ("shoes", "handbags", "accessories", "belts"):
        return COLOR_LIBRARY
    return tuple(c for c in COLOR_LIBRARY if c.family != "metallic")


def _score(req: MatchRequest, hex_value: str, category: str, pattern: str = "solid") -> ScoreBreakdown:
    return score_pair(
        req.base_hex, hex_value, category,
        occasion=req.occasion, style=req.style, prefs=req.prefs,
        base_secondary=req.secondary, base_pattern=req.pattern, candidate_pattern=pattern,
    )


def recommend_for_category(req: MatchRequest, category: str, limit: int = 4) -> list[Recommendation]:
    """Top ``limit`` library colors for ``category``, diversified across rules and families."""
    scored: list[Recommendation] = []
    for color in candidate_pool(category):
        if color.hex == req.base_hex:
            continue
        if req.shade_filter and color.family != "metallic" and shade_of(color.hex) != req.shade_filter:
            continue
        bd = _score(req, color.hex, category)
        scored.append(Recommendation(category, color.hex, color.name, bd.total, bd.rule, bd))
    # Deterministic: score desc, then name
    scored.sort(key=lambda r: (-r.score, r.name))

    picked: list[Recommendation] = []
    rule_count: dict[str, int] = {}
    families: set[str] = set()
    # Pass 1: distinct families and at most two per harmony rule; pass 2: distinct
    # families only; pass 3: anything. Keeps suggestions varied but deterministic.
    for pass_no in (1, 2, 3):
        for rec in scored:
            if len(picked) == limit:
                break
            if rec in picked:
                continue
            fam = get_color(rec.name).family  # type: ignore[union-attr]
            if pass_no < 3 and fam in families:
                continue
            if pass_no == 1 and rule_count.get(rec.rule or "", 0) >= 2:
                continue
            picked.append(rec)
            rule_count[rec.rule or ""] = rule_count.get(rec.rule or "", 0) + 1
            families.add(fam)
    picked.sort(key=lambda r: (-r.score, r.name))
    return picked


def recommend(req: MatchRequest, categories: list[str] | None = None, limit: int = 4) -> dict[str, list[Recommendation]]:
    cats = categories or target_categories(req.base_category)
    return {c: recommend_for_category(req, c, limit) for c in cats}


def wardrobe_matches(
    req: MatchRequest, items: list[WardrobeItem], category: str, limit: int = 3, exclude_id: str | None = None
) -> list[Recommendation]:
    """Owned pieces that pair best with the base color."""
    wcat, subcats = RECOMMEND_TO_WARDROBE[category]
    out: list[Recommendation] = []
    for item in items:
        if item.id == exclude_id or item.category != wcat:
            continue
        if subcats and item.subcategory and item.subcategory not in subcats:
            continue
        bd = _score(req, item.primary_color, category, item.pattern)
        out.append(Recommendation(category, item.primary_color, item.name, bd.total, bd.rule, bd, item))
    out.sort(key=lambda r: (-r.score, r.name, r.wardrobe_item.id if r.wardrobe_item else ""))
    return out[:limit]
