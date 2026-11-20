"""Image processing (validation, optimisation, extraction) and both visualizers."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from src.core.color_convert import color_distance
from src.models.domain import HAIR_STYLES, NAIL_SHAPES, SUBCATEGORIES, Outfit, OutfitItem
from src.services import image_processing as ip
from src.visualizer import flatlay, mannequin
from src.visualizer.patterns import PATTERNS, pattern_tile, svg_pattern_def
from src.visualizer.svg_assets import available_variants, load_template, parse_path
from tests.conftest import jpeg_bytes


# ---------------------------------------------------------------- validation
def test_validation_rejects_bad_files():
    with pytest.raises(ip.ImageValidationError, match="empty"):
        ip.validate_image(b"", "a.jpg")
    with pytest.raises(ip.ImageValidationError, match="not a readable image"):
        ip.validate_image(b"definitely not an image", "a.jpg")
    with pytest.raises(ip.ImageValidationError, match="JPG, PNG or WEBP"):
        ip.validate_image(jpeg_bytes(), "a.gif")
    with pytest.raises(ip.ImageValidationError, match="limit"):
        ip.validate_image(b"\xff" * (ip.MAX_UPLOAD_BYTES + 1), "a.jpg")
    with pytest.raises(ip.ImageValidationError, match="too small"):
        ip.validate_image(jpeg_bytes(size=(40, 40)), "a.jpg")
    buf = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buf, format="GIF")
    with pytest.raises(ip.ImageValidationError, match="Unsupported"):
        ip.validate_image(buf.getvalue(), None)
    truncated = jpeg_bytes()[:400]
    with pytest.raises(ip.ImageValidationError):
        ip.validate_image(truncated, "a.jpg")


def test_accepts_png_with_alpha_and_webp():
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out = ip.process_upload(buf.getvalue(), "x.png")
    assert Image.open(io.BytesIO(out.full)).getpixel((5, 5)) == pytest.approx((248, 244, 239), abs=3)
    ip.validate_image(jpeg_bytes(fmt="WEBP"), "x.webp")


def test_optimize_resizes_compresses_and_strips_exif():
    big = jpeg_bytes(size=(3000, 4000))
    p = ip.process_upload(big, "big.jpg")
    full = Image.open(io.BytesIO(p.full))
    thumb = Image.open(io.BytesIO(p.thumb))
    assert max(full.size) == ip.FULL_MAX_SIDE and max(thumb.size) == ip.THUMB_MAX_SIDE
    assert full.format == "JPEG" and len(p.thumb) < len(p.full) < len(big)
    assert not full.getexif()


def test_exif_orientation_applied():
    img = Image.new("RGB", (400, 200), (200, 0, 0))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° CW
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    p = ip.process_upload(buf.getvalue(), "r.jpg")
    assert (p.width, p.height) == (200, 400)


def test_crop_fraction():
    img = Image.new("RGB", (1000, 500))
    assert ip.crop_fraction(img, (0.1, 0.2, 0.6, 0.8)).size == (500, 300)
    with pytest.raises(ValueError):
        ip.crop_fraction(img, (0.5, 0.5, 0.4, 0.9))
    with pytest.raises(ValueError):
        ip.crop_fraction(img, (0.5, 0.5, 0.501, 0.501))
    prev = ip.preview_with_box(img, (0.1, 0.1, 0.9, 0.9))
    assert prev.size[0] <= 640


def test_extract_dominant_and_secondary_colors_ignoring_background():
    img = ip.open_image(jpeg_bytes(garment=(113, 62, 74), stripes=(232, 201, 197)))
    res = ip.extract_colors(img)
    assert res.primary.name in ("Burgundy", "Wine", "Plum")
    assert color_distance(res.primary.hex, "#713E4A") < 8
    assert any(color_distance(c.hex, "#E8C9C5") < 10 for c in res.secondary)
    # background (light gray) should not dominate
    assert all(color_distance(c.hex, "#F0F0EE") > 5 for c in res.colors[:2])
    assert 0.1 < res.mask_coverage < 0.6
    assert abs(sum(c.share for c in res.colors) - 1) < 1e-6
    again = ip.extract_colors(img)
    assert [c.hex for c in again.colors] == [c.hex for c in res.colors]  # deterministic


def test_extract_with_crop_and_without_background_reduction():
    img = ip.open_image(jpeg_bytes(garment=(31, 42, 68)))
    cropped = ip.extract_colors(img, crop=(0.3, 0.3, 0.7, 0.7), reduce_background=False)
    assert cropped.method == "full region"
    assert cropped.primary.name in ("Navy", "Midnight")


def test_uniform_image_falls_back_gracefully():
    img = Image.new("RGB", (200, 200), (200, 50, 50))
    res = ip.extract_colors(img)
    assert res.primary is not None and len(res.colors) >= 1


# ---------------------------------------------------------------- svg assets
def test_path_parser_commands():
    (sp,) = parse_path("M0,0 L10,0 H20 V10 Q20,20 10,20 C5,20 0,15 0,10 Z")
    assert sp.closed and sp.points[0] == (0, 0) and (20.0, 10.0) in sp.points
    (rel,) = parse_path("m10,10 l5,0 l0,5 z")
    assert rel.points[-1] == (15.0, 15.0)
    with pytest.raises(ValueError):
        parse_path("A 1 1 0 0 1 5 5")


def test_every_subcategory_variant_has_a_template():
    variants = {v for subs in SUBCATEGORIES.values() for v in subs.values()}
    assert variants <= set(available_variants())
    for v in variants:
        asset = load_template(v)
        x0, y0, x1, y1 = asset.bbox
        assert 0 <= x0 < x1 <= 400 and 0 <= y0 < y1 <= 1000
    for shape in NAIL_SHAPES:
        assert load_template(f"nails_{shape}").paths


def _outfit_full(pattern="striped") -> Outfit:
    o = Outfit(name="Test <look> & co", hair_style="ponytail", hair_color="#C9975B")
    for slot, color, variant in [("top", "#E8C9C5", "blouse"), ("bottom", "#1F2A44", "pants"),
                                 ("outerwear", "#C8AD91", "blazer"), ("shoes", "#141414", "heels"),
                                 ("bag", "#713E4A", "clutch"), ("jewelry", "#C9A44C", "earrings"),
                                 ("accessory", "#302B2B", "sunglasses"), ("scarf", "#B77E79", "scarf"),
                                 ("belt", "#9A5B2E", "belt"), ("hat", "#D8C3A5", "beret"),
                                 ("nails", "#B3112E", "french")]:
        o.set_item(OutfitItem(slot=slot, color_hex=color, variant=variant,
                              pattern=pattern if slot == "top" else "solid", secondary_hex="#F8F4EF"))
    return o


def test_mannequin_svg_is_valid_and_layered():
    o = _outfit_full()
    svg = mannequin.render_svg(o, height=500)
    root = ET.fromstring(svg)  # well-formed XML
    layers = [g.get("data-layer") for g in root.iter("{http://www.w3.org/2000/svg}g")]
    for expected in ("hair_back", "body", "nails", "top", "bottom", "outerwear", "shoes", "bag", "hair_front", "hat"):
        assert expected in layers
    assert layers.index("bottom") < layers.index("top") < layers.index("outerwear") < layers.index("hat")
    assert "<pattern" in svg and "#E8C9C5" in svg
    assert "<script" not in svg.lower()
    assert "&lt;look&gt;" in svg  # name escaped in aria-label


def test_mannequin_updates_with_outfit_changes():
    o = _outfit_full("solid")
    before = mannequin.render_svg(o)
    o.set_item(OutfitItem(slot="top", color_hex="#A3B18A", variant="tee"))
    after = mannequin.render_svg(o)
    assert before != after and "#A3B18A" in after


def test_mannequin_base_layers_when_empty_and_all_hairstyles():
    svg = mannequin.render_svg(Outfit())
    assert 'data-layer="base_top"' in svg and 'data-layer="base_bottom"' in svg
    for style in HAIR_STYLES:
        img = mannequin.render_image(Outfit(hair_style=style), height=300)
        assert img.mode == "RGBA" and img.height == 300


def test_mannequin_png_export():
    data = mannequin.render_png(_outfit_full(), height=600)
    img = Image.open(io.BytesIO(data))
    assert img.format == "PNG" and img.width == 1080 and img.height > 900


def test_patterns_render_in_both_formats():
    for name in PATTERNS:
        assert "<pattern" in svg_pattern_def(name, "p1", "#1F2A44", None)
        tile = pattern_tile(name, "#1F2A44", "#F8F4EF", 2.0)
        assert tile.size[0] >= 4
    assert svg_pattern_def("solid", "p", "#FFFFFF", None) == ""
    assert pattern_tile("solid", "#FFFFFF", None, 1.0) is None


@pytest.mark.parametrize("layout", list(flatlay.LAYOUTS))
def test_flatlay_layouts_fit_and_dont_overlap(layout):
    slots = [i.slot for i in _outfit_full().items]
    boxes = flatlay.layout_boxes(layout, slots)
    assert set(boxes) == set(slots)
    rects = list(boxes.values())
    for x, y, w, h in rects:
        assert 0 <= x and 0 <= y and x + w <= 1.0001 and y + h <= 1.0001 and w > 0 and h > 0
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            overlap = not (a[0] + a[2] <= b[0] + 1e-6 or b[0] + b[2] <= a[0] + 1e-6 or
                           a[1] + a[3] <= b[1] + 1e-6 or b[1] + b[3] <= a[1] + 1e-6)
            assert not overlap, (a, b)


def test_flatlay_uses_photos_and_falls_back_to_templates():
    o = _outfit_full("solid")
    o.get("top").wardrobe_item_id = "with-photo"
    o.get("bag").wardrobe_item_id = "broken"
    calls = []

    def loader(item_id):
        calls.append(item_id)
        if item_id == "with-photo":
            return jpeg_bytes(size=(300, 400), garment=(10, 200, 10))
        return b"corrupt"

    board = flatlay.render_board(o, "editorial", size=(800, 880), photo_loader=loader)
    assert board.size == (800, 880) and set(calls) == {"with-photo", "broken"}
    # the photo's green garment appears in the top's box
    x, y, w, h = flatlay.layout_boxes("editorial", [i.slot for i in o.items])["top"]
    region = board.crop((int(x * 800), int(y * 880), int((x + w) * 800), int((y + h) * 880))).convert("RGB")
    greens = sum(1 for px in region.getdata() if px[1] > 150 and px[0] < 80)
    assert greens > 500
    no_photos = flatlay.render_board(o, "grid", photo_loader=loader, use_photos=False)
    assert no_photos.size == (1000, 1100)


def test_flatlay_png_export():
    data = flatlay.render_png(_outfit_full(), "minimal")
    img = Image.open(io.BytesIO(data))
    assert img.format == "PNG" and img.width == 1080
