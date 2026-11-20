"""Outfit model, outfit scoring/generation, nails & hair."""

from __future__ import annotations

import pytest

from src.core.beauty import colors_for_hair, hair_note, recommend_hairstyles, recommend_nails
from src.core.outfit_engine import OutfitContext, finish_beauty, generate_outfits, score_outfit, variant_suitability
from src.core.recommender import MatchRequest, recommend, wardrobe_matches
from src.models.domain import (
    HAIR_STYLES,
    Outfit,
    OutfitItem,
    UserPreferences,
    WardrobeItem,
    variant_for,
)
from src.services.styling import outfit_from_match


def W(name, cat, color, sub=None, **kw):
    return WardrobeItem(name=name, category=cat, primary_color=color, subcategory=sub, **kw)


WARDROBE = [
    W("Ivory blouse", "tops", "#F8F4EF", "Blouse", occasions=["office"]),
    W("Striped tee", "tops", "#FBFBF9", "T-shirt", pattern="striped", secondary_colors=["#1F2A44"]),
    W("Black cami", "tops", "#141414", "Camisole", occasions=["date night"]),
    W("Navy trousers", "bottoms", "#1F2A44", "Trousers", occasions=["office"]),
    W("Jeans", "bottoms", "#8EA7C1", "Jeans"),
    W("Burgundy slip dress", "dresses", "#713E4A", "Slip dress", occasions=["date night"]),
    W("Summer linen dress", "dresses", "#FBFBF9", "Maxi dress", seasons=["summer"]),
    W("Trench", "outerwear", "#C8AD91", "Trench coat", seasons=["autumn", "spring"]),
    W("Nude pumps", "shoes", "#E3BFA3", "Pumps"),
    W("White sneakers", "shoes", "#FBFBF9", "Sneakers"),
    W("Cognac tote", "bags", "#9A5B2E", "Tote"),
    W("Rose clutch", "bags", "#B77E79", "Clutch"),
    W("Gold hoops", "jewelry", "#C9A44C", "Earrings"),
]


# ---------------------------------------------------------------- model
def test_wardrobe_item_validation():
    with pytest.raises(ValueError):
        W("", "tops", "#FFFFFF")
    with pytest.raises(ValueError):
        W("x", "socks", "#FFFFFF")
    it = W("x", "tops", "abc", pattern="weird", shade="glowing", seasons=["summer", "monsoon"],
           secondary_colors=["#111111", "nope", "#111111"])
    assert it.primary_color == "#AABBCC" and it.pattern == "solid" and it.shade is None
    assert it.seasons == ["summer"] and it.secondary_colors == ["#111111"]
    assert it.slot == "top" and it.variant == "tee"
    assert variant_for("bottoms", "Midi skirt") == "skirt_midi"
    assert WardrobeItem.from_dict(it.to_dict()) == it


def test_outfit_dress_replaces_separates_and_back():
    o = Outfit()
    o.set_item(OutfitItem(slot="top", color_hex="#FFFFFF"))
    o.set_item(OutfitItem(slot="bottom", color_hex="#000000"))
    o.set_item(OutfitItem(slot="shoes", color_hex="#000000"))
    assert o.is_complete()
    o.set_item(OutfitItem(slot="dress", color_hex="#713E4A"))
    assert {i.slot for i in o.items} == {"dress", "shoes"} and o.is_complete()
    o.set_item(OutfitItem(slot="top", color_hex="#FFFFFF"))
    assert o.get("dress") is None and not o.is_complete()
    o.remove("shoes")
    assert o.get("shoes") is None


def test_outfit_copy_and_roundtrip():
    o = Outfit(name="A", hair_style="bun")
    o.set_item(OutfitItem(slot="nails", color_hex="#B3112E", variant="french"))
    o.set_item(OutfitItem(slot="top", color_hex="#FFFFFF"))
    clone = o.copy(new_identity=True)
    assert clone.id != o.id and clone.items[0].id != o.items[0].id
    back = Outfit.from_dict(o.to_dict())
    assert back == o
    assert o.colors == ["#FFFFFF"]  # nails are not a garment color
    assert Outfit(hair_style="mohawk").hair_style == "long_waves"
    assert OutfitItem(slot="nails", color_hex="#FFFFFF", variant="tee").variant == "almond"
    with pytest.raises(ValueError):
        OutfitItem(slot="cape", color_hex="#FFFFFF")


def test_preferences_normalisation():
    p = UserPreferences(favorite_colors=["#abc", "nope"], preferred_styles=["romantic", "goth"],
                        scoring_weights={"harmony": "2", "contrast": -1, "unknown": 5}, hair_style="x", nail_shape="y")
    assert p.favorite_colors == ["#AABBCC"] and p.preferred_styles == ["romantic"]
    assert p.scoring_weights["harmony"] == 2.0 and p.scoring_weights["contrast"] == 0.0
    assert "unknown" not in p.scoring_weights
    assert sum(p.normalized_weights().values()) == pytest.approx(1.0)
    assert p.hair_style == "long_waves" and p.nail_shape == "almond"


# ---------------------------------------------------------------- outfit scoring
def _outfit(*pieces):
    o = Outfit()
    for slot, color, variant, pattern in pieces:
        o.set_item(OutfitItem(slot=slot, color_hex=color, variant=variant, pattern=pattern))
    return o


def test_score_outfit_rewards_harmony_and_completeness():
    classic = _outfit(("top", "#F8F4EF", "blouse", "solid"), ("bottom", "#1F2A44", "pants", "solid"),
                      ("shoes", "#E3BFA3", "heels", "solid"))
    clash = _outfit(("top", "#E0457B", "blouse", "floral"), ("bottom", "#2E9E4F", "pants", "plaid"),
                    ("shoes", "#F28C28", "heels", "solid"), ("bag", "#1F4FB4", "handbag", "solid"))
    incomplete = _outfit(("top", "#F8F4EF", "blouse", "solid"))
    s_classic, s_clash = score_outfit(classic).total, score_outfit(clash).total
    assert s_classic > s_clash
    assert score_outfit(incomplete).components["category"] < score_outfit(classic).components["category"]
    notes = " ".join(score_outfit(clash).explanations)
    assert "patterned" in notes
    assert score_outfit(Outfit()).total == 0


def test_occasion_suitability_affects_score():
    office_heels = _outfit(("top", "#F8F4EF", "blouse", "solid"), ("bottom", "#1F2A44", "pants", "solid"),
                           ("shoes", "#E3BFA3", "heels", "solid"))
    office_sneak = _outfit(("top", "#F8F4EF", "blouse", "solid"), ("bottom", "#1F2A44", "pants", "solid"),
                           ("shoes", "#E3BFA3", "sneakers", "solid"))
    ctx = OutfitContext(occasion="interview")
    assert score_outfit(office_heels, ctx).components["occasion"] > score_outfit(office_sneak, ctx).components["occasion"]
    assert variant_suitability("clutch", "date night") > 0 > variant_suitability("tote", "date night")
    assert variant_suitability("tee", None) == 0


# ---------------------------------------------------------------- generator
def test_generator_uses_only_owned_items_and_is_deterministic():
    ctx = OutfitContext(occasion="office")
    a = generate_outfits(WARDROBE, ctx, limit=4)
    b = generate_outfits(list(reversed(WARDROBE)), ctx, limit=4)
    owned = {w.id for w in WARDROBE}
    assert a and len(a) <= 4
    for g in a:
        assert g.outfit.is_complete()
        assert all(i.wardrobe_item_id in owned for i in g.outfit.garments)
        assert g.outfit.get("nails") is not None  # beauty finishing
        assert g.outfit.hair_style in HAIR_STYLES
    assert [[i.wardrobe_item_id for i in g.outfit.garments] for g in a] == \
           [[i.wardrobe_item_id for i in g.outfit.garments] for g in b]


def test_generator_picks_practical_pieces_for_the_occasion():
    date = generate_outfits(WARDROBE, OutfitContext(occasion="date night"), limit=1)[0].outfit
    assert date.get("bag").label == "Rose clutch"
    assert date.get("shoes").label == "Nude pumps"
    office = generate_outfits(WARDROBE, OutfitContext(occasion="office"), limit=1)[0].outfit
    assert office.get("bag").label == "Cognac tote"


def test_generator_respects_season():
    winter = generate_outfits(WARDROBE, OutfitContext(occasion="casual", season="winter"), limit=6)
    used = {i.label for g in winter for i in g.outfit.items}
    assert "Summer linen dress" not in used and "Trench" not in used


def test_generator_diversifies_main_pieces():
    looks = generate_outfits(WARDROBE, OutfitContext(occasion="casual"), limit=3)
    first_mains = [tuple(sorted(i.wardrobe_item_id for i in g.outfit.items if i.slot in ("top", "bottom", "dress")))
                   for g in looks]
    assert len(set(first_mains)) == len(first_mains)


def test_generator_needs_a_base():
    assert generate_outfits([W("Shoes", "shoes", "#000000")], OutfitContext()) == []


# ---------------------------------------------------------------- beauty
def test_nail_recommendations():
    o = _outfit(("dress", "#713E4A", "dress_midi", "solid"), ("shoes", "#141414", "heels", "solid"))
    recs = recommend_nails(o, limit=5)
    assert len(recs) == 5 and [r.score for r in recs] == sorted([r.score for r in recs], reverse=True)
    assert all(r.explanations for r in recs)
    families = [r.name for r in recs]
    assert len(set(families)) == 5
    # matching the bag gets a bonus note
    o2 = _outfit(("top", "#F8F4EF", "blouse", "solid"), ("bag", "#B3112E", "clutch", "solid"))
    red = next((r for r in recommend_nails(o2, limit=200, diverse=False) if r.name == "Cherry Red"), None)
    assert red is not None and any("Echoes your bag" in e for e in red.explanations)
    assert recommend_nails(None, limit=3)  # works with nothing chosen yet


def test_hairstyle_rules():
    hat = _outfit(("dress", "#A3B18A", "dress_maxi", "solid"), ("hat", "#D8C3A5", "sunhat", "solid"))
    hat.occasion = "beach"
    styles = [h.style for h in recommend_hairstyles(hat, limit=7)]
    assert styles.index("bun") > styles.index("side_braid")
    office = _outfit(("top", "#F8F4EF", "sweater", "solid"), ("jewelry", "#C9A44C", "earrings", "solid"))
    office.occasion = "interview"
    best = recommend_hairstyles(office)[0]
    assert best.style in ("bun", "ponytail") and best.reasons
    short = recommend_hairstyles(office, UserPreferences(hair_style="pixie"), limit=7)
    assert {h.style for h in short} <= {"bob", "pixie"}


def test_hair_color_harmony():
    blonde = colors_for_hair("#DDB66F", limit=6)
    assert len(blonde) == 6 and all(m.hex != "#DDB66F" for m in blonde)
    o = _outfit(("top", "#3B2A24", "tee", "solid"))
    o.hair_color = "#3B2A24"
    assert "very close" in hair_note(o)
    assert hair_note(Outfit()) == ""


def test_finish_beauty_uses_preferences():
    o = _outfit(("dress", "#713E4A", "dress_midi", "solid"), ("shoes", "#141414", "heels", "solid"))
    finish_beauty(o, OutfitContext("date night", None, None, UserPreferences(nail_shape="square")))
    assert o.get("nails").variant == "square"
    existing = o.get("nails").color_hex
    finish_beauty(o, OutfitContext("date night"))
    assert o.get("nails").color_hex == existing  # never overrides a chosen polish


def test_outfit_from_match_builds_complete_look():
    req = MatchRequest("#B77E79", "tops", occasion="office")
    results = recommend(req)
    owned = {c: wardrobe_matches(req, WARDROBE, c) for c in results}
    o = outfit_from_match(req, results, owned)
    assert o.get("top").color_hex == "#B77E79"
    assert o.get("bottom") and o.get("shoes") and o.get("bag") and o.get("nails")
    assert o.is_complete()
