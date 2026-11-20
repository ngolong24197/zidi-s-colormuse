"""Color conversion, distance, harmony, scoring and recommendation tests."""

from __future__ import annotations

import numpy as np
import pytest
from skimage.color import deltaE_ciede2000, rgb2lab

from src.core import color_convert as cc
from src.core.color_library import COLOR_LIBRARY, color_name, get_color, is_neutral_hex, nearest_color, undertone_of
from src.core.harmony import RULES, all_palettes, classify_relation, harmony_palette, harmony_targets, metallic_for
from src.core.recommender import (
    RECOMMEND_CATEGORIES,
    MatchRequest,
    recommend,
    recommend_for_category,
    target_categories,
    wardrobe_matches,
)
from src.core.scoring import (
    category_fit,
    contrast_balance,
    hue_family_count,
    occasion_fit,
    preference_fit,
    score_pair,
    style_fit,
)
from src.models.domain import UserPreferences, WardrobeItem


# ---------------------------------------------------------------- conversion
@pytest.mark.parametrize("raw,expected", [("#abc", "#AABBCC"), ("b77e79", "#B77E79"), (" #713E4A ", "#713E4A")])
def test_normalize_hex(raw, expected):
    assert cc.normalize_hex(raw) == expected


@pytest.mark.parametrize("bad", ["", "#12", "#GGGGGG", "red", None, 123])
def test_invalid_hex(bad):
    with pytest.raises(cc.ColorError):
        cc.normalize_hex(bad)
    assert not cc.is_valid_hex(bad)


def test_rgb_hsl_hsv_roundtrip():
    for c in COLOR_LIBRARY:
        rgb = cc.hex_to_rgb(c.hex)
        assert cc.hsl_to_rgb(cc.rgb_to_hsl(rgb)) == rgb
        assert cc.hsv_to_rgb(cc.rgb_to_hsv(rgb)) == rgb
        assert cc.rgb_to_hex(rgb) == c.hex


def test_known_hsl_values():
    h, s, l = cc.hex_to_hsl("#FF0000")
    assert (round(h), round(s, 2), round(l, 2)) == (0, 1.0, 0.5)
    h, s, v = cc.rgb_to_hsv((0, 0, 255))
    assert (round(h), s, v) == (240, 1.0, 1.0)


def test_lab_matches_scikit_image():
    for c in COLOR_LIBRARY:
        ours = np.array(cc.hex_to_lab(c.hex))
        ref = rgb2lab(np.array(cc.hex_to_rgb(c.hex), dtype=float).reshape(1, 1, 3) / 255).reshape(3)
        assert np.allclose(ours, ref, atol=0.05), c.name


def test_lab_roundtrip():
    for c in COLOR_LIBRARY:
        back = cc.lab_to_rgb(cc.hex_to_lab(c.hex))
        assert max(abs(a - b) for a, b in zip(back, cc.hex_to_rgb(c.hex))) <= 1


# Reference pairs from Sharma, Wu & Dalal (2005), "The CIEDE2000 color-difference formula"
SHARMA = [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
    ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412),
    ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0000),
    ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
    ((50.0, 2.49, -0.001), (50.0, -2.49, 0.0009), 7.1792),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize("lab1,lab2,expected", SHARMA)
def test_ciede2000_reference(lab1, lab2, expected):
    assert cc.delta_e_2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)


def test_ciede2000_matches_skimage_and_is_symmetric():
    rng = np.random.default_rng(1)
    for _ in range(200):
        a = tuple(rng.uniform([0, -80, -80], [100, 80, 80]))
        b = tuple(rng.uniform([0, -80, -80], [100, 80, 80]))
        ref = float(deltaE_ciede2000(np.array(a), np.array(b)))
        assert cc.delta_e_2000(a, b) == pytest.approx(ref, abs=1e-6)
        assert cc.delta_e_2000(a, b) == pytest.approx(cc.delta_e_2000(b, a), abs=1e-9)
    assert cc.color_distance("#B77E79", "#B77E79") == 0


def test_contrast_ratio_and_luminance():
    assert cc.contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
    assert cc.contrast_ratio("#777777", "#777777") == pytest.approx(1.0)
    assert cc.text_color_for("#141414") == "#F8F4EF" and cc.text_color_for("#F8F4EF") == "#302B2B"


def test_shade_hue_and_helpers():
    assert cc.shade_of("#F8F4EF") == "light" and cc.shade_of("#B77E79") == "medium" and cc.shade_of("#141414") == "dark"
    assert cc.hue_difference(350, 10) == 20 and cc.hue_difference(0, 180) == 180
    assert cc.mix("#000000", "#FFFFFF", 0.5) in ("#7F7F7F", "#808080")
    assert cc.lightness(cc.adjust_lightness("#B77E79", 0.2)) > cc.lightness("#B77E79")


# ---------------------------------------------------------------- library
def test_library_unique_and_valid():
    names = [c.name for c in COLOR_LIBRARY]
    assert len(names) == len(set(names)) and len(names) >= 90
    assert all(cc.is_valid_hex(c.hex) for c in COLOR_LIBRARY)


def test_nearest_names_and_neutrals():
    assert color_name("#B77E7A") == "Dusty Rose"
    assert nearest_color("#141415").name == "Black"
    assert is_neutral_hex("#C19A6B") and is_neutral_hex("#808080") and is_neutral_hex("#1F2A44")
    assert not is_neutral_hex("#F2D3D4") and not is_neutral_hex("#C2185B")
    assert undertone_of("#F28C28") == "warm" and undertone_of("#1F4FB4") == "cool" and undertone_of("#808080") == "neutral"
    assert get_color("navy").hex == "#1F2A44"


# ---------------------------------------------------------------- harmony
def test_harmony_target_angles():
    base = "#D0312D"
    h = cc.hex_to_hsl(base)[0]
    (comp,) = harmony_targets(base, "complementary")
    assert cc.hue_difference(cc.hex_to_hsl(comp)[0], h) == pytest.approx(180, abs=2)
    tri = harmony_targets(base, "triadic")
    assert sorted(round(cc.hue_difference(cc.hex_to_hsl(t)[0], h)) for t in tri) == pytest.approx([120, 120], abs=2)
    split = harmony_targets(base, "split complementary")
    assert all(cc.hue_difference(cc.hex_to_hsl(t)[0], h) == pytest.approx(150, abs=2) for t in split)
    ana = harmony_targets(base, "analogous")
    assert all(cc.hue_difference(cc.hex_to_hsl(t)[0], h) == pytest.approx(30, abs=2) for t in ana)
    mono = harmony_targets(base, "monochromatic")
    assert mono and all(cc.hue_difference(cc.hex_to_hsl(t)[0], h) < 3 for t in mono)
    with pytest.raises(ValueError):
        harmony_targets(base, "rainbow")


def test_palettes_are_named_distinct_and_not_the_base():
    pals = all_palettes("#B77E79")
    assert set(pals) == set(RULES)
    for rule, colors in pals.items():
        assert colors, rule
        hexes = [p.hex for p in colors]
        assert len(hexes) == len(set(hexes)) and "#B77E79" not in hexes
        assert all(get_color(p.name) for p in colors)


def test_classify_relation():
    assert classify_relation("#D0312D", "#2DCCD0").rule == "complementary"
    assert classify_relation("#D0312D", "#D0812D").rule == "analogous"
    assert classify_relation("#B77E79", "#141414").rule == "neutral"
    mono = classify_relation("#713E4A", cc.adjust_lightness("#713E4A", 0.35))
    assert mono.rule == "monochromatic" and mono.quality >= 0.85
    near_identical = classify_relation("#B77E79", "#B77E7A")
    assert near_identical.quality < mono.quality
    awkward = classify_relation("#D0312D", "#8DD02D")  # ~75° apart: between named harmonies
    assert awkward.quality < classify_relation("#D0312D", "#2DCCD0").quality


def test_metallic_for():
    assert metallic_for("#1F4FB4").name == "Silver"
    assert metallic_for("#C25B26").name == "Gold"


# ---------------------------------------------------------------- scoring
def test_contrast_balance():
    soft, _ = contrast_balance("#E8C9C5", "#E9CBC6")
    good, _ = contrast_balance("#E8C9C5", "#713E4A")
    assert good > soft
    loud, msg = contrast_balance("#E0457B", "#2E9E4F")
    assert "intense" in msg


def test_category_fit_rules():
    assert category_fit("#C9A44C", "jewelry")[0] == 1.0
    assert category_fit("#141414", "shoes")[0] > category_fit("#E0457B", "shoes")[0]
    assert category_fit("#1F2A44", "outerwear")[0] > category_fit("#F28C28", "outerwear")[0]


def test_occasion_and_style_fit():
    white, msg = occasion_fit("#FBFBF9", "wedding guest")
    sage, _ = occasion_fit("#A3B18A", "wedding guest")
    assert white < sage and "avoided" in msg
    assert occasion_fit("#1F2A44", "interview")[0] > occasion_fit("#E0457B", "interview")[0]
    assert occasion_fit("#B77E79", None)[0] == 0.75
    assert style_fit("#E8C9C5", "romantic")[0] > style_fit("#141414", "romantic")[0]
    assert style_fit("#A0472A", "bohemian")[0] > style_fit("#1F4FB4", "bohemian")[0]


def test_preference_fit():
    prefs = UserPreferences(favorite_colors=["#A3B18A"], disliked_colors=["#F28C28"])
    fav, fmsg = preference_fit("#A3B18A", prefs)
    dis, dmsg = preference_fit("#F28C28", prefs)
    assert fav > 0.9 and dis < 0.2 and "favourite" in fmsg and "avoid" in dmsg
    assert preference_fit("#A3B18A", None)[0] == 0.7


def test_score_pair_weights_and_explanations():
    bd = score_pair("#B77E79", "#A3B18A", "skirts", occasion="wedding guest", style="romantic")
    assert 0 <= bd.total <= 100
    assert set(bd.components) == {"harmony", "contrast", "category", "occasion", "style", "preference"}
    assert sum(bd.weights.values()) == pytest.approx(1.0)
    assert bd.weights["harmony"] == pytest.approx(0.35)
    assert len(bd.explanations) >= 4
    # configurable weights
    prefs = UserPreferences(scoring_weights={"harmony": 1, "contrast": 0, "category": 0, "occasion": 0, "style": 0, "preference": 0})
    only_h = score_pair("#B77E79", "#A3B18A", "skirts", prefs=prefs)
    assert only_h.total == pytest.approx(only_h.components["harmony"] * 100, abs=0.1)


def test_pattern_clash_penalised():
    solid = score_pair("#1F2A44", "#E8C9C5", "skirts", base_pattern="striped")
    clash = score_pair("#1F2A44", "#E8C9C5", "skirts", base_pattern="striped", candidate_pattern="floral")
    assert clash.total < solid.total


def test_secondary_color_echo_bonus():
    plain = score_pair("#1F2A44", "#C19A6B", "shoes")
    echo = score_pair("#1F2A44", "#C19A6B", "shoes", base_secondary=["#C19A6B"])
    assert echo.components["harmony"] > plain.components["harmony"]
    assert any("picks up" in e for e in echo.explanations)


def test_hue_family_count():
    assert hue_family_count(["#FBFBF9", "#141414"]) == 0
    assert hue_family_count(["#D0312D", "#D2392F", "#1F4FB4"]) == 2


# ---------------------------------------------------------------- recommender
def test_target_category_exclusions():
    assert "dresses" not in target_categories("dresses") and "shirts" not in target_categories("dresses")
    assert "pants" not in target_categories("bottoms")
    assert set(target_categories("hats")) == set(RECOMMEND_CATEGORIES)


def test_recommendations_are_ranked_diverse_and_deterministic():
    req = MatchRequest("#B77E79", "tops", occasion="office")
    a = recommend(req)
    b = recommend(MatchRequest("#B77E79", "tops", occasion="office"))
    assert [(c, [r.hex for r in v]) for c, v in a.items()] == [(c, [r.hex for r in v]) for c, v in b.items()]
    for cat, recs in a.items():
        assert len(recs) == 4
        assert [r.score for r in recs] == sorted([r.score for r in recs], reverse=True)
        assert len({get_color(r.name).family for r in recs}) == 4
        assert all(r.explanations and 0 <= r.score <= 100 for r in recs)
        assert "#B77E79" not in [r.hex for r in recs]


def test_jewelry_recommends_metals_first():
    recs = recommend_for_category(MatchRequest("#1F2A44", "dresses"), "jewelry")
    assert get_color(recs[0].name).family == "metallic"


def test_shade_filter():
    recs = recommend_for_category(MatchRequest("#1F2A44", "pants", shade_filter="light"), "shirts")
    assert all(cc.shade_of(r.hex) == "light" for r in recs)


def test_preferences_change_recommendations():
    base = recommend_for_category(MatchRequest("#1F2A44", "pants"), "shirts", limit=10)
    top = base[0]
    prefs = UserPreferences(disliked_colors=[top.hex])
    after = recommend_for_category(MatchRequest("#1F2A44", "pants", prefs=prefs), "shirts", limit=10)
    assert after[0].hex != top.hex


def test_wardrobe_matches_respect_category_and_subcategory():
    items = [
        WardrobeItem(name="Midi skirt", category="bottoms", subcategory="Midi skirt", primary_color="#C19A6B"),
        WardrobeItem(name="Jeans", category="bottoms", subcategory="Jeans", primary_color="#8EA7C1"),
        WardrobeItem(name="Tee", category="tops", primary_color="#FBFBF9"),
    ]
    req = MatchRequest("#E8C9C5", "tops")
    skirts = wardrobe_matches(req, items, "skirts")
    pants = wardrobe_matches(req, items, "pants")
    assert [r.wardrobe_item.name for r in skirts] == ["Midi skirt"]
    assert [r.wardrobe_item.name for r in pants] == ["Jeans"]
    assert wardrobe_matches(req, items, "shirts", exclude_id=items[2].id) == []
