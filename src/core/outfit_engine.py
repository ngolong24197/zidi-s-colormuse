"""Whole-outfit scoring and the occasion planner's outfit generator.

Generation is a deterministic beam search over the owner's wardrobe:
bases (top+bottom or dress) → best shoes → optional outerwear/bag/jewelry/
accessories, each only kept if it improves the outfit score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from src.core.color_convert import lightness
from src.core.color_library import color_name, is_neutral_hex
from src.core.harmony import classify_relation
from src.core.scoring import (
    COMPONENT_LABELS,
    ScoreBreakdown,
    category_fit,
    contrast_balance,
    hue_family_count,
    occasion_fit,
    preference_fit,
    style_fit,
    weights_from,
)
from src.i18n import _, cname, label
from src.models.domain import Outfit, OutfitItem, UserPreferences, WardrobeItem

# Visual weight of each slot in the overall palette
SLOT_WEIGHT: dict[str, float] = {
    "top": 1.0, "bottom": 1.0, "dress": 1.6, "outerwear": 1.1, "shoes": 0.6, "bag": 0.6,
    "jewelry": 0.3, "accessory": 0.3, "scarf": 0.5, "belt": 0.3, "hat": 0.4, "nails": 0.25,
}
SLOT_CATEGORY_KEY: dict[str, str] = {
    "top": "tops", "bottom": "bottoms", "dress": "dresses", "outerwear": "outerwear", "shoes": "shoes",
    "bag": "bags", "jewelry": "jewelry", "accessory": "accessories", "scarf": "scarves",
    "belt": "belts", "hat": "hats", "nails": "nails",
}
MAIN_SLOTS = ("top", "bottom", "dress", "outerwear")

# Garment type x occasion suitability (added to the occasion fit of that piece).
# Heuristic: e.g. a clutch reads evening, a tote reads daytime/work.
VARIANT_OCCASION: dict[str, dict[str, float]] = {
    "sneakers": {"office": -0.35, "interview": -0.5, "formal": -0.6, "wedding guest": -0.5, "date night": -0.2,
                 "dinner": -0.2, "party": -0.2, "casual": 0.2, "travel": 0.25, "daily errands": 0.25},
    "heels": {"formal": 0.2, "wedding guest": 0.2, "date night": 0.2, "party": 0.2, "office": 0.1, "interview": 0.1,
              "dinner": 0.15, "beach": -0.4, "daily errands": -0.2, "travel": -0.3},
    "flats": {"office": 0.1, "travel": 0.15, "daily errands": 0.1, "beach": 0.1, "casual": 0.05},
    "boots": {"casual": 0.1, "dinner": 0.05, "beach": -0.5, "formal": -0.3, "wedding guest": -0.3, "date night": -0.05},
    "tote": {"office": 0.2, "travel": 0.2, "daily errands": 0.15, "date night": -0.3, "party": -0.4, "formal": -0.5,
             "wedding guest": -0.4, "dinner": -0.2},
    "clutch": {"date night": 0.25, "party": 0.25, "formal": 0.25, "wedding guest": 0.25, "dinner": 0.15,
               "office": -0.3, "travel": -0.4, "daily errands": -0.3, "beach": -0.2},
    "crossbody": {"casual": 0.15, "travel": 0.2, "daily errands": 0.2, "formal": -0.3, "wedding guest": -0.2},
    "handbag": {"office": 0.15, "dinner": 0.1, "interview": 0.1},
    "tee": {"office": -0.15, "interview": -0.3, "formal": -0.5, "wedding guest": -0.4, "casual": 0.15,
            "daily errands": 0.1, "travel": 0.1, "beach": 0.1},
    "tank": {"office": -0.2, "interview": -0.4, "formal": -0.3, "beach": 0.2, "party": 0.05, "date night": 0.05},
    "blouse": {"office": 0.2, "interview": 0.2, "dinner": 0.1, "date night": 0.05},
    "sweater": {"casual": 0.1, "travel": 0.1, "daily errands": 0.1, "beach": -0.4, "party": -0.1, "formal": -0.3},
    "shorts": {"office": -0.5, "interview": -0.6, "formal": -0.6, "wedding guest": -0.5, "beach": 0.3, "casual": 0.1,
               "dinner": -0.2},
    "pants": {"office": 0.15, "interview": 0.2, "travel": 0.1},
    "skirt_mini": {"office": -0.2, "interview": -0.3, "party": 0.15, "date night": 0.1},
    "skirt_midi": {"office": 0.1, "dinner": 0.05, "wedding guest": 0.05},
    "dress_mini": {"party": 0.2, "date night": 0.1, "office": -0.2, "interview": -0.3},
    "dress_midi": {"wedding guest": 0.15, "dinner": 0.1, "date night": 0.1, "office": 0.05},
    "dress_maxi": {"formal": 0.2, "beach": 0.15, "wedding guest": 0.15, "office": -0.1},
    "blazer": {"office": 0.25, "interview": 0.3, "beach": -0.4},
    "coat": {"travel": 0.1, "beach": -0.5, "party": -0.1},
    "cardigan": {"casual": 0.1, "travel": 0.1, "office": 0.05, "formal": -0.3},
    "sunhat": {"beach": 0.3, "office": -0.4, "interview": -0.5, "formal": -0.4, "dinner": -0.2, "party": -0.3,
               "wedding guest": -0.1},
    "beanie": {"formal": -0.5, "office": -0.3, "wedding guest": -0.5, "interview": -0.5, "date night": -0.2},
    "beret": {"interview": -0.2, "formal": -0.2},
    "sunglasses": {"beach": 0.2, "travel": 0.1, "interview": -0.3, "formal": -0.3, "dinner": -0.2},
}


def variant_suitability(variant: str | None, occasion: str | None) -> float:
    if not variant or not occasion:
        return 0.0
    return VARIANT_OCCASION.get(variant, {}).get(occasion, 0.0)


WARM_SEASON_OCCASIONS = {"beach"}
LAYERING_OCCASIONS = {"office", "formal", "interview", "travel"}


@dataclass
class OutfitContext:
    occasion: str | None = None
    style: str | None = None
    season: str | None = None
    prefs: UserPreferences | None = None


def _wmean(pairs: list[tuple[float, float]]) -> float:
    tw = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / tw if tw else 0.0


def score_outfit(outfit: Outfit, ctx: OutfitContext | None = None, items_by_id: dict[str, WardrobeItem] | None = None) -> ScoreBreakdown:
    ctx = ctx or OutfitContext()
    items_by_id = items_by_id or {}
    pieces = outfit.items
    weights = weights_from(ctx.prefs)
    if not pieces:
        return ScoreBreakdown({k: 0.0 for k in COMPONENT_LABELS}, weights, [_("Add pieces to see a score.")])

    notes: list[str] = []
    # ---- harmony: weighted pairwise relation quality
    pair_scores: list[tuple[float, float]] = []
    rules: dict[str, int] = {}
    for a, b in combinations(pieces, 2):
        rel = classify_relation(a.color_hex, b.color_hex)
        w = SLOT_WEIGHT[a.slot] * SLOT_WEIGHT[b.slot]
        pair_scores.append((rel.quality, w))
        if rel.rule != "neutral":
            rules[rel.rule] = rules.get(rel.rule, 0) + 1
    harmony = _wmean(pair_scores) if pair_scores else 0.85
    accent_count = hue_family_count(outfit.colors)
    if accent_count > 3:
        harmony *= 0.8
        notes.append(_("{n} different accent hues — consider swapping one for a neutral.", n=accent_count))
    if rules:
        main_rule = max(rules.items(), key=lambda kv: (kv[1], kv[0]))[0]
        notes.append(_("The palette reads as {rule}.", rule=label("rule", main_rule).lower()))
    else:
        notes.append(_("An all-neutral palette — timeless and easy to accessorise."))

    # ---- contrast & balance between the main pieces (and shoes vs. bottom/dress)
    mains = [p for p in pieces if p.slot in MAIN_SLOTS]
    contrast_pairs: list[tuple[float, float]] = []
    for a, b in combinations(mains, 2):
        c, _msg = contrast_balance(a.color_hex, b.color_hex)
        contrast_pairs.append((c, 1.0))
    shoes = outfit.get("shoes")
    anchor = outfit.get("dress") or outfit.get("bottom")
    if shoes and anchor:
        c, _msg = contrast_balance(shoes.color_hex, anchor.color_hex)
        contrast_pairs.append((c, 0.5))
    contrast = _wmean(contrast_pairs) if contrast_pairs else 0.8
    ls = [lightness(p.color_hex) for p in mains] or [50]
    if max(ls) - min(ls) < 8 and len(mains) > 1:
        notes.append(_("Tonal dressing: the main pieces share a similar depth."))
    elif max(ls) - min(ls) > 55:
        notes.append(_("Crisp light-and-dark contrast gives the look definition."))

    # ---- category fit + pattern discipline + completeness
    cat_scores = [(category_fit(p.color_hex, SLOT_CATEGORY_KEY[p.slot])[0], SLOT_WEIGHT[p.slot]) for p in pieces]
    category = _wmean(cat_scores)
    patterned = [p for p in pieces if p.pattern != "solid" and p.slot in MAIN_SLOTS + ("scarf",)]
    if len(patterned) > 1:
        category *= 0.75
        notes.append(_("More than one patterned piece — let a single print lead."))
    elif len(patterned) == 1:
        notes.append(_("The {pattern} piece is the focal point; everything else stays solid.",
                       pattern=label("pattern", patterned[0].pattern).lower()))
    if not outfit.is_complete():
        category *= 0.85
        notes.append(_("Add a full base (top + bottom or a dress) and shoes to complete the look."))

    # ---- occasion / style / preference (color fit + item tags)
    def tag_bonus(piece: OutfitItem, attr: str, value: str | None) -> float:
        item = items_by_id.get(piece.wardrobe_item_id or "")
        if not item or not value:
            return 0.0
        tags = getattr(item, attr)
        if not tags:
            return 0.0
        return 0.12 if value in tags else -0.08

    occ = _wmean([(max(0.0, min(1.0, occasion_fit(p.color_hex, ctx.occasion)[0] + tag_bonus(p, "occasions", ctx.occasion)
                                + variant_suitability(p.variant, ctx.occasion))), SLOT_WEIGHT[p.slot]) for p in pieces])
    unsuited = [p for p in pieces if variant_suitability(p.variant, ctx.occasion) <= -0.3]
    if unsuited:
        names = ", ".join((p.label or p.variant or p.slot) for p in unsuited[:2])
        notes.append(_("For {occasion}, consider swapping: {names}.",
                       occasion=label("occasion", ctx.occasion).lower(), names=names))
    sty = _wmean([(min(1.0, style_fit(p.color_hex, ctx.style)[0] + tag_bonus(p, "styles", ctx.style)), SLOT_WEIGHT[p.slot]) for p in pieces])
    pref = _wmean([(preference_fit(p.color_hex, ctx.prefs)[0], SLOT_WEIGHT[p.slot]) for p in pieces])
    if ctx.prefs:
        favs = [items_by_id[p.wardrobe_item_id] for p in pieces if p.wardrobe_item_id in items_by_id and items_by_id[p.wardrobe_item_id].favorite]
        if favs:
            pref = min(1.0, pref + 0.05 * len(favs))
            notes.append(_("Includes {n} of your favourite pieces.", n=len(favs)) if len(favs) > 1
                         else _("Includes one of your favourite pieces."))
    if ctx.occasion:
        notes.append(_("Occasion fit for {occasion}: {pct}%.",
                       occasion=label("occasion", ctx.occasion).lower(), pct=int(occ * 100)))
    from src.core.beauty import hair_note

    hn = hair_note(outfit)
    if hn:
        notes.append(hn)
    nails = outfit.get("nails")
    if nails:
        notes.append(_("Nails: {color} polish.", color=cname(nails.color_hex)))

    comps = {
        "harmony": max(0.0, min(1.0, harmony)),
        "contrast": max(0.0, min(1.0, contrast)),
        "category": max(0.0, min(1.0, category)),
        "occasion": max(0.0, min(1.0, occ)),
        "style": max(0.0, min(1.0, sty)),
        "preference": max(0.0, min(1.0, pref)),
    }
    return ScoreBreakdown(comps, weights, notes)


# ---------------------------------------------------------------- generator

def _in_season(item: WardrobeItem, season: str | None) -> bool:
    return not season or not item.seasons or season in item.seasons


def _item_fit(item: WardrobeItem, ctx: OutfitContext) -> float:
    occ = occasion_fit(item.primary_color, ctx.occasion)[0] + variant_suitability(item.variant, ctx.occasion)
    if ctx.occasion and item.occasions:
        occ += 0.25 if ctx.occasion in item.occasions else -0.1
    sty = style_fit(item.primary_color, ctx.style)[0]
    if ctx.style and item.styles:
        sty += 0.1 if ctx.style in item.styles else -0.05
    return occ + 0.6 * sty + (0.05 if item.favorite else 0)


@dataclass
class GeneratedOutfit:
    outfit: Outfit
    breakdown: ScoreBreakdown
    items: list[WardrobeItem] = field(default_factory=list)
    objective: float = 0.0

    @property
    def score(self) -> float:
        return self.breakdown.total


def _make_outfit(pieces: list[WardrobeItem], ctx: OutfitContext) -> Outfit:
    o = Outfit(name="", occasion=ctx.occasion, style=ctx.style, season=ctx.season)
    if ctx.prefs:
        o.skin_tone, o.hair_color, o.hair_style = ctx.prefs.skin_tone, ctx.prefs.hair_color, ctx.prefs.hair_style
    for p in pieces:
        o.set_item(OutfitItem.from_wardrobe(p))
    return o


def generate_outfits(
    wardrobe: list[WardrobeItem], ctx: OutfitContext, limit: int = 6, per_slot: int = 8
) -> list[GeneratedOutfit]:
    """Best outfits from owned pieces for the context. Deterministic."""
    by_id = {w.id: w for w in wardrobe}
    pool: dict[str, list[WardrobeItem]] = {}
    for w in wardrobe:
        if _in_season(w, ctx.season):
            pool.setdefault(w.slot, []).append(w)
    for slot, items in pool.items():
        items.sort(key=lambda w: (-_item_fit(w, ctx), w.name, w.id))
        pool[slot] = items[:per_slot]

    def sc(pieces: list[WardrobeItem]) -> tuple[float, Outfit, ScoreBreakdown]:
        """Search objective: displayed score + practical suitability of each garment type
        and the owner's own occasion tags (so a clutch wins for date night, a tote for work)."""
        o = _make_outfit(pieces, ctx)
        bd = score_outfit(o, ctx, by_id)
        practical = 0.0
        for p in pieces:
            practical += 10 * variant_suitability(p.variant, ctx.occasion)
            if ctx.occasion and p.occasions:
                practical += 3 if ctx.occasion in p.occasions else -1.5
        return bd.total + practical, o, bd

    bases: list[list[WardrobeItem]] = []
    for top in pool.get("top", []):
        for bottom in pool.get("bottom", []):
            bases.append([top, bottom])
    for dress in pool.get("dress", []):
        bases.append([dress])
    if not bases:
        return []

    # Keep the best bases (beam)
    scored_bases = sorted(bases, key=lambda b: (-sc(b)[0], [i.id for i in b]))[: max(limit * 4, 12)]

    optional_order = ["outerwear", "bag", "jewelry", "belt", "scarf", "accessory", "hat"]
    results: list[GeneratedOutfit] = []
    for base in scored_bases:
        current = list(base)
        if pool.get("shoes"):
            best = max(pool["shoes"], key=lambda s: (sc(current + [s])[0], s.name, s.id))
            current.append(best)
        best_score = sc(current)[0]
        for slot in optional_order:
            if slot not in pool:
                continue
            candidates = sorted(pool[slot], key=lambda c: (-sc(current + [c])[0], c.name, c.id))
            if not candidates:
                continue
            cand = candidates[0]
            new_score = sc(current + [cand])[0]
            wants_layer = slot == "outerwear" and (
                ctx.season in ("autumn", "winter") or ctx.occasion in LAYERING_OCCASIONS
            )
            skip_layer = slot == "outerwear" and (ctx.season == "summer" or ctx.occasion in WARM_SEASON_OCCASIONS)
            if skip_layer:
                continue
            # a bag is expected with almost every outfit; small accents get some slack too
            slack = {"bag": 4.0, "jewelry": 2.0}.get(slot, 1.5 if wants_layer else 0.0)
            if new_score >= best_score - slack:
                current.append(cand)
                best_score = max(best_score, new_score)
        total, outfit, bd = sc(current)
        results.append(GeneratedOutfit(outfit, bd, current, total))

    results.sort(key=lambda g: (-g.objective, [i.id for i in g.items]))

    # Diversity: avoid repeating the same main piece across suggestions where possible
    chosen: list[GeneratedOutfit] = []
    used: dict[str, int] = {}
    for allowed in (1, 2, 99):
        for g in results:
            if g in chosen:
                continue
            mains = [i.id for i in g.items if i.slot in MAIN_SLOTS]
            if all(used.get(m, 0) < allowed for m in mains):
                chosen.append(g)
                for m in mains:
                    used[m] = used.get(m, 0) + 1
            if len(chosen) == limit:
                break
        if len(chosen) == limit:
            break
    chosen.sort(key=lambda g: (-g.objective, [i.id for i in g.items]))
    for n, g in enumerate(chosen, 1):
        anchor = g.outfit.get("dress") or g.outfit.get("top")
        title = label("occasion", ctx.occasion) if ctx.occasion else _("Everyday")
        g.outfit.name = _("{occasion} look {n}", occasion=title, n=n) + (f" — {cname(anchor.color_hex)}" if anchor else "")
        finish_beauty(g.outfit, ctx)
        g.breakdown = score_outfit(g.outfit, ctx, by_id)
        g.outfit.score = g.score
    return chosen


def finish_beauty(outfit: Outfit, ctx: OutfitContext) -> None:
    """Add the best nail polish and hairstyle for the outfit (in place)."""
    from src.core.beauty import recommend_hairstyles, recommend_nails

    if outfit.get("nails") is None:
        nails = recommend_nails(outfit, occasion=ctx.occasion, style=ctx.style, prefs=ctx.prefs, limit=1)
        if nails:
            shape = ctx.prefs.nail_shape if ctx.prefs else "almond"
            outfit.set_item(OutfitItem(slot="nails", color_hex=nails[0].hex, variant=shape, label=_("{color} polish", color=label("color", nails[0].name))))
    hair = recommend_hairstyles(outfit, ctx.prefs, limit=1)
    if hair:
        outfit.hair_style = hair[0].style


def palette_summary(outfit: Outfit) -> str:
    names = []
    for p in outfit.items:
        n = color_name(p.color_hex)
        if n not in names:
            names.append(n)
    neutral = sum(1 for p in outfit.items if is_neutral_hex(p.color_hex))
    return f"{', '.join(names)} · {neutral}/{len(outfit.items)} neutral"
