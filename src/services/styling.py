"""Glue between the color engine and outfits (used by the Color Matcher)."""

from __future__ import annotations

from src.core.outfit_engine import OutfitContext, finish_beauty
from src.core.recommender import MatchRequest, Recommendation
from src.models.domain import (
    CATEGORY_TO_SLOT,
    DEFAULT_VARIANT,
    Outfit,
    OutfitItem,
    UserPreferences,
    WardrobeItem,
)

REC_TO_SLOT = {
    "shirts": ("top", "blouse"), "skirts": ("bottom", "skirt_midi"), "pants": ("bottom", "pants"),
    "dresses": ("dress", "dress_midi"), "shoes": ("shoes", "heels"), "handbags": ("bag", "handbag"),
    "jewelry": ("jewelry", "necklace"), "accessories": ("accessory", "sunglasses"), "outerwear": ("outerwear", "blazer"),
}

# Which recommendation categories complete an outfit, by base slot
_COMPLETE = {
    "top": ("pants", "shoes", "handbags", "jewelry"),
    "bottom": ("shirts", "shoes", "handbags", "jewelry"),
    "dress": ("shoes", "handbags", "jewelry"),
    "outerwear": ("shirts", "pants", "shoes", "handbags"),
    "shoes": ("shirts", "pants", "handbags"),
    "bag": ("shirts", "pants", "shoes"),
}


def outfit_from_match(
    req: MatchRequest,
    results: dict[str, list[Recommendation]],
    owned: dict[str, list[Recommendation]] | None = None,
    base_item: WardrobeItem | None = None,
    prefs: UserPreferences | None = None,
) -> Outfit:
    owned = owned or {}
    o = Outfit(name="Matched look", occasion=req.occasion, style=req.style)
    if prefs:
        o.skin_tone, o.hair_color, o.hair_style = prefs.skin_tone, prefs.hair_color, prefs.hair_style
    if base_item is not None:
        o.set_item(OutfitItem.from_wardrobe(base_item))
        base_slot = base_item.slot
    else:
        base_slot = CATEGORY_TO_SLOT.get(req.base_category, "top")
        o.set_item(OutfitItem(slot=base_slot, color_hex=req.base_hex, pattern=req.pattern,
                              secondary_hex=req.secondary[0] if req.secondary else None,
                              variant=DEFAULT_VARIANT.get(req.base_category), label="Your piece"))
    for cat in _COMPLETE.get(base_slot, ("shoes", "handbags", "jewelry")):
        slot, variant = REC_TO_SLOT[cat]
        if o.get(slot) is not None:
            continue
        mine = owned.get(cat) or []
        if mine and mine[0].wardrobe_item is not None and mine[0].score >= 70:
            o.set_item(OutfitItem.from_wardrobe(mine[0].wardrobe_item))
        elif results.get(cat):
            r = results[cat][0]
            o.set_item(OutfitItem(slot=slot, color_hex=r.hex, variant=variant, label=r.name))
    finish_beauty(o, OutfitContext(req.occasion, req.style, None, prefs))
    return o
