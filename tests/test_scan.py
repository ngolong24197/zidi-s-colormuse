"""Camera scan service: snapshot → colors → recommendations → save to wardrobe."""

from __future__ import annotations

import pytest

from src import i18n
from src.core.color_convert import color_distance
from src.models.domain import UserPreferences, WardrobeItem
from src.services import scan
from src.services.image_processing import ImageValidationError
from tests.conftest import jpeg_bytes

SAGE = (163, 177, 138)


def _snapshot(color=SAGE, bg=(236, 233, 228)) -> bytes:
    # a phone-like frame: the piece fills the middle, background around it
    return jpeg_bytes(size=(720, 960), bg=bg, garment=color)


def test_analyze_reads_the_centre_and_recommends():
    r = scan.analyze(_snapshot(), "tops")
    assert color_distance(r.main_hex, "#A3B18A") < 10
    assert r.extraction.mask_coverage > 0.2
    # quick categories only, and none that conflict with a top
    assert set(r.recommendations) <= set(scan.QUICK_CATEGORIES)
    assert "shirts" not in r.recommendations and "pants" in r.recommendations
    assert all(len(v) <= 2 and v for v in r.recommendations.values())
    assert r.nails and all(n.explanations is not None for n in r.nails)


def test_manual_color_correction_overrides_detection():
    r = scan.analyze(_snapshot(), "tops", main_hex="#713E4A")
    assert r.main_hex == "#713E4A"
    assert r.request.shade == "dark"


def test_finds_owned_matches_and_similar_pieces():
    wardrobe = [
        WardrobeItem(name="Sage tee", category="tops", primary_color="#A5B28C"),
        WardrobeItem(name="Navy trousers", category="bottoms", subcategory="Trousers", primary_color="#1F2A44"),
        WardrobeItem(name="Nude pumps", category="shoes", primary_color="#E3BFA3"),
        WardrobeItem(name="Red top", category="tops", primary_color="#D0312D"),
    ]
    r = scan.analyze(_snapshot(), "tops", wardrobe=wardrobe, prefs=UserPreferences())
    assert [w.name for w in r.similar_owned] == ["Sage tee"]
    assert r.owned_matches["pants"][0].wardrobe_item.name == "Navy trousers"
    assert r.owned_matches["shoes"][0].wardrobe_item.name == "Nude pumps"


def test_dress_scan_skips_conflicting_categories():
    r = scan.analyze(_snapshot((113, 62, 74)), "dresses")
    assert not {"shirts", "pants", "skirts"} & set(r.recommendations)
    assert "shoes" in r.recommendations


def test_suggested_name_in_both_languages():
    r = scan.analyze(_snapshot(), "tops")
    assert r.suggested_name("Blouse").endswith("blouse")
    i18n.set_language("vi")
    try:
        name = r.suggested_name("Blouse")
        assert name.startswith("Áo blouse") and "xanh" in name
    finally:
        i18n.set_language("en")


def test_rejects_unusable_snapshots():
    with pytest.raises(ImageValidationError):
        scan.analyze(b"not an image", "tops")


def test_save_to_wardrobe_creates_piece_with_photo(repo):
    r = scan.analyze(_snapshot(), "tops")
    item = scan.save_to_wardrobe(repo, r, name="Sage linen shirt", subcategory="Shirt", pattern="solid", favorite=True)
    got = repo.get_item(item.id)
    assert got.name == "Sage linen shirt" and got.category == "tops" and got.subcategory == "Shirt"
    assert got.primary_color == r.main_hex and got.favorite and got.primary_color_name
    assert got.thumb_path and repo.get_file(got.thumb_path)
    assert len(repo.list_item_images(item.id)) == 1
    # it now shows up as "already owned" on the next scan of the same piece
    again = scan.analyze(_snapshot(), "tops", wardrobe=repo.list_items()[0])
    assert [w.id for w in again.similar_owned] == [item.id]
