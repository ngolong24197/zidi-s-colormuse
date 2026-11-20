"""The same behavioural contract, run against the local and the Supabase repository."""

from __future__ import annotations

import pytest

from src.database.base import NotFound
from src.models.domain import Collection, Outfit, OutfitItem, UserPreferences, WardrobeItem
from src.services.image_processing import process_upload


def item(name="Silk blouse", category="tops", color="#E8C9C5", **kw) -> WardrobeItem:
    return WardrobeItem(name=name, category=category, primary_color=color, **kw)


def test_preferences_roundtrip(repo):
    assert repo.get_preferences().display_name == ""
    p = UserPreferences(display_name="Zidi", favorite_colors=["#b77e79"], preferred_styles=["romantic"],
                        hair_style="bob", nail_shape="french", scoring_weights={"harmony": 0.5})
    repo.save_preferences(p)
    got = repo.get_preferences()
    assert got.display_name == "Zidi"
    assert got.favorite_colors == ["#B77E79"]
    assert got.hair_style == "bob" and got.nail_shape == "french"
    assert got.scoring_weights["harmony"] == 0.5


def test_item_crud(repo):
    saved = repo.save_item(item(brand="Muse", seasons=["spring"], styles=["chic"], occasions=["office"]))
    got = repo.get_item(saved.id)
    assert got.name == "Silk blouse" and got.brand == "Muse" and got.seasons == ["spring"]
    got.name = "Silk blouse (blush)"
    got.primary_color = "#F2D3D4"
    repo.save_item(got)
    again = repo.get_item(saved.id)
    assert again.name == "Silk blouse (blush)" and again.primary_color == "#F2D3D4"
    assert again.created_at == got.created_at
    repo.set_item_favorite(saved.id, True)
    assert repo.get_item(saved.id).favorite is True
    repo.delete_item(saved.id)
    assert repo.get_item(saved.id) is None
    with pytest.raises(NotFound):
        repo.delete_item(saved.id)


def test_item_search_filter_sort_paginate(repo):
    names = ["Navy trousers", "Ivory blouse", "Blush sweater", "Black boots", "Camel coat"]
    cats = ["bottoms", "tops", "tops", "shoes", "outerwear"]
    colors = ["#1F2A44", "#F8F4EF", "#E8C9C5", "#141414", "#C19A6B"]
    for n, c, col in zip(names, cats, colors):
        repo.save_item(item(n, c, col, seasons=["winter"] if "coat" in n else [], favorite="boots" in n))
    items, total = repo.list_items()
    assert total == 5
    assert [i.name for i in repo.list_items(category="tops", sort="name")[0]] == ["Blush sweater", "Ivory blouse"]
    assert [i.name for i in repo.list_items(search="blouse")[0]] == ["Ivory blouse"]
    assert [i.name for i in repo.list_items(favorite=True)[0]] == ["Black boots"]
    # season: untagged items count as all-season
    summer = {i.name for i in repo.list_items(season="summer")[0]}
    assert "Camel coat" not in summer and "Navy trousers" in summer
    by_color = [i.name for i in repo.list_items(sort="color")[0]]
    assert by_color[0] == "Ivory blouse" and by_color[-1] == "Black boots"
    page1, total = repo.list_items(sort="name", limit=2, offset=0)
    page3, _ = repo.list_items(sort="name", limit=2, offset=4)
    assert total == 5 and len(page1) == 2 and len(page3) == 1
    assert page1[0].name == "Black boots" and page3[0].name == "Navy trousers"
    # search text with PostgREST control characters must not break the query
    assert repo.list_items(search="a,b)(*%")[1] == 0


def test_images_upload_replace_delete(repo, photo):
    saved = repo.save_item(item())
    p = process_upload(photo, "shirt.jpg")
    img = repo.upload_item_image(saved.id, p.full, p.thumb, p.width, p.height)
    assert img.storage_path.startswith(repo.owner_id + "/")
    it = repo.get_item(saved.id)
    assert it.image_path == img.storage_path and it.thumb_path == img.thumb_path
    assert repo.get_file(it.thumb_path) == p.thumb
    # replacing removes the old files
    img2 = repo.upload_item_image(saved.id, p.full, p.thumb, p.width, p.height)
    assert repo.get_file(img.storage_path) is None
    assert len(repo.list_item_images(saved.id)) == 1
    repo.delete_item_images(saved.id)
    assert repo.get_file(img2.storage_path) is None
    assert repo.get_item(saved.id).image_path is None


def test_deleting_item_removes_photos_and_unlinks_outfits(repo, photo):
    saved = repo.save_item(item())
    p = process_upload(photo, "shirt.jpg")
    img = repo.upload_item_image(saved.id, p.full, p.thumb, p.width, p.height)
    o = Outfit(name="Look")
    o.set_item(OutfitItem.from_wardrobe(saved))
    repo.save_outfit(o)
    repo.delete_item(saved.id)
    assert repo.get_file(img.storage_path) is None
    look = repo.get_outfit(o.id)
    assert look.get("top").wardrobe_item_id is None
    assert look.get("top").color_hex == "#E8C9C5"  # the look keeps its color


def test_cannot_read_other_owners_files(repo):
    assert repo.get_file("someone-else/items/x.jpg") is None


def test_outfit_crud_and_items(repo):
    o = Outfit(name="Brunch", occasion="casual", hair_style="bun")
    o.set_item(OutfitItem(slot="top", color_hex="#E8C9C5", variant="blouse"))
    o.set_item(OutfitItem(slot="bottom", color_hex="#1F2A44", variant="pants"))
    o.set_item(OutfitItem(slot="nails", color_hex="#B3112E", variant="french"))
    repo.save_outfit(o)
    got = repo.get_outfit(o.id)
    assert got.name == "Brunch" and got.hair_style == "bun"
    assert [i.slot for i in got.items] == ["bottom", "top", "nails"]
    assert got.get("nails").variant == "french"
    # edit: switch to a dress (removes top & bottom)
    got.set_item(OutfitItem(slot="dress", color_hex="#713E4A"))
    repo.save_outfit(got)
    again = repo.get_outfit(o.id)
    assert {i.slot for i in again.items} == {"dress", "nails"}
    dup = repo.duplicate_outfit(o.id)
    assert dup.id != o.id and dup.name.endswith("(copy)") and len(dup.items) == 2
    repo.set_outfit_favorite(o.id, True)
    assert [x.id for x in repo.list_outfits(favorite=True)[0]] == [o.id]
    assert repo.list_outfits(search="brunch")[1] == 2
    assert repo.list_outfits(occasion="casual")[1] == 2
    repo.delete_outfit(o.id)
    assert repo.get_outfit(o.id) is None
    assert repo.get_outfit(dup.id) is not None


def test_outfit_pagination_most_recent_first(repo):
    ids = []
    for n in range(5):
        o = Outfit(name=f"Look {n}")
        o.set_item(OutfitItem(slot="top", color_hex="#FFFFFF"))
        ids.append(repo.save_outfit(o).id)
    page, total = repo.list_outfits(limit=2)
    assert total == 5 and len(page) == 2
    assert page[0].name == "Look 4"


def test_collections(repo):
    o = Outfit(name="Office")
    o.set_item(OutfitItem(slot="top", color_hex="#FFFFFF"))
    repo.save_outfit(o)
    c = repo.save_collection(Collection(name=" Workweek "))
    assert c.name == "Workweek"
    repo.add_to_collection(c.id, o.id)
    repo.add_to_collection(c.id, o.id)  # idempotent
    assert repo.collections_for_outfit(o.id) == [c.id]
    assert [x.id for x in repo.list_outfits(collection_id=c.id)[0]] == [o.id]
    c.name = "Work"
    repo.save_collection(c)
    assert [x.name for x in repo.list_collections()] == ["Work"]
    repo.remove_from_collection(c.id, o.id)
    assert repo.list_outfits(collection_id=c.id)[1] == 0
    repo.add_to_collection(c.id, o.id)
    repo.delete_collection(c.id)
    assert repo.get_outfit(o.id) is not None  # deleting a collection keeps the looks
    with pytest.raises(ValueError):
        repo.save_collection(Collection(name="   "))


def test_history(repo):
    repo.add_history("color_match", {"base_hex": "#B77E79"}, [{"hex": "#A3B18A", "score": 88}])
    repo.add_history("color_match", {"base_hex": "#1F2A44"}, [])
    hist = repo.list_history()
    assert len(hist) == 2 and hist[0]["request"]["base_hex"] in ("#1F2A44", "#B77E79")


def test_colors_library_readable(repo):
    colors = repo.list_colors()
    assert len(colors) > 80 and {"name", "hex", "family", "is_neutral"} <= set(colors[0])


def test_delete_all_data(repo, photo):
    saved = repo.save_item(item())
    p = process_upload(photo, "a.jpg")
    img = repo.upload_item_image(saved.id, p.full, p.thumb, p.width, p.height)
    o = Outfit(name="x")
    o.set_item(OutfitItem.from_wardrobe(saved))
    repo.save_outfit(o)
    repo.save_collection(Collection(name="c"))
    repo.save_preferences(UserPreferences(display_name="Z"))
    repo.add_history("k", {}, [])
    repo.delete_all_data()
    assert repo.list_items()[1] == 0 and repo.list_outfits()[1] == 0
    assert repo.list_collections() == [] and repo.list_history() == []
    assert repo.get_preferences().display_name == ""
    assert repo.get_file(img.storage_path) is None
    assert repo.health_check()
