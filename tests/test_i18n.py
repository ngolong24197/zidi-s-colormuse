"""Vietnamese language support: completeness, placeholders, engine output, fonts, pages."""

from __future__ import annotations

import ast
import re
import string
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from src import i18n
from src.core.color_library import COLOR_LIBRARY
from src.core.harmony import RULES
from src.core.recommender import RECOMMEND_CATEGORIES
from src.core.scoring import _CATEGORY_NOTES, OCCASION_PROFILES, STYLE_PROFILES
from src.database.base import WARDROBE_SORTS
from src.i18n_vi import VI, VI_LABELS
from src.models.domain import (
    CATEGORIES,
    HAIR_COLORS,
    HAIR_STYLES,
    NAIL_SHAPES,
    OCCASIONS,
    PATTERNS,
    SEASONS,
    SHADES,
    SLOTS,
    STYLES,
    SUBCATEGORIES,
)
from src.visualizer.flatlay import LAYOUTS

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "app.py", ROOT / "companion.py", *sorted((ROOT / "pages").glob("*.py")), *sorted((ROOT / "src").rglob("*.py"))]

# Strings translated through a variable (options shown with format_func=_, "none" texts,
# exception messages raised elsewhere and shown via _(str(exc))).
DYNAMIC = [
    "None", "From wardrobe", "Custom color", "Library", "Custom", "Separates (top + bottom)", "Dress",
    "Manual choice", "Photo", "Wardrobe piece", "Any occasion", "Any style", "Any season", "All categories",
    "ColorMuse can't reach its cloud database right now. If the Supabase project was paused for inactivity, "
    "restore it from the Supabase dashboard, then retry.",
    "Your session has expired. Please sign in again.",
    "Backup file is too large.", "This is not a ColorMuse backup file.",
]


@pytest.fixture(autouse=True)
def _english_after():
    yield
    i18n.set_language("en")


def translatable_literals() -> set[str]:
    found: set[str] = set()
    for path in SOURCES:
        if path.name == "i18n_vi.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("_", "N_", "tr") and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.add(node.args[0].value)
    found.discard("...")  # docstring example in i18n.py
    return found


def _fields(s: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(s) if f}


def test_every_ui_string_has_a_vietnamese_translation():
    needed = translatable_literals() | set(DYNAMIC)
    needed |= {p.summary for p in OCCASION_PROFILES.values()} | {p.summary for p in STYLE_PROFILES.values()}
    needed |= {text for notes in _CATEGORY_NOTES.values() for text in notes.values()}
    missing = sorted(s for s in needed if s not in VI)
    assert not missing, f"{len(missing)} strings lack Vietnamese: {missing[:15]}"
    assert len(needed) > 300


def test_placeholders_match():
    bad = [k for k, v in VI.items() if _fields(k) != _fields(v)]
    assert bad == []


def test_no_unused_vietnamese_entries_drift():
    """Every VI key is still used somewhere (keeps the table honest)."""
    used = translatable_literals() | set(DYNAMIC)
    used |= {p.summary for p in OCCASION_PROFILES.values()} | {p.summary for p in STYLE_PROFILES.values()}
    used |= {text for notes in _CATEGORY_NOTES.values() for text in notes.values()}
    stale = sorted(k for k in VI if k not in used)
    assert stale == [], stale


@pytest.mark.parametrize("kind,values", [
    ("category", CATEGORIES), ("slot", SLOTS), ("pattern", PATTERNS), ("shade", SHADES), ("season", SEASONS),
    ("style", STYLES), ("occasion", OCCASIONS), ("hair", list(HAIR_STYLES)), ("nail", list(NAIL_SHAPES)),
    ("hair_color", list(HAIR_COLORS)), ("rule", RULES), ("rec", RECOMMEND_CATEGORIES), ("layout", list(LAYOUTS)),
    ("sort", list(WARDROBE_SORTS)), ("color", [c.name for c in COLOR_LIBRARY]),
    ("component", ["harmony", "contrast", "category", "occasion", "style", "preference"]),
    ("subcategory", [s for subs in SUBCATEGORIES.values() for s in subs]),
    ("variant", sorted({v for subs in SUBCATEGORIES.values() for v in subs.values()})),
    ("skin", ["Porcelain", "Light", "Medium", "Tan", "Deep", "Rich"]),
])
def test_every_vocabulary_value_has_a_vietnamese_label(kind, values):
    missing = [v for v in values if v not in VI_LABELS[kind]]
    assert missing == []


def test_language_switch_and_english_default():
    assert i18n.get_language() == "en"
    assert i18n._("Save piece") == "Save piece"
    assert i18n.label("occasion", "date night") == "Date night"
    assert i18n.cname("#B77E79") == "Dusty Rose"
    i18n.set_language("vi")
    assert i18n._("Save piece") == "Lưu món đồ"
    assert i18n._("Hello, {name}", name="Zidi") == "Xin chào, Zidi"
    assert i18n.label("occasion", "date night") == "Hẹn hò"
    assert i18n.cname("#B77E79") == "Hồng đất"
    assert i18n.set_language("fr") == "en"  # unknown → English


def test_engine_explanations_in_vietnamese():
    from src.core.outfit_engine import OutfitContext, generate_outfits
    from src.core.scoring import score_pair
    from tests.test_outfits_and_beauty import WARDROBE

    i18n.set_language("vi")
    bd = score_pair("#B77E79", "#A3B18A", "skirts", occasion="wedding guest", style="romantic")
    text = " ".join(bd.explanations)
    assert "Hồng đất" in text and "Xanh xô thơm" in text and "dịp dự đám cưới" in text
    assert "color wheel" not in text and "occasion favours" not in text
    looks = generate_outfits(WARDROBE, OutfitContext("date night"), limit=1)
    assert looks[0].outfit.name.startswith("Bộ đồ Hẹn hò")
    assert any("Móng" in n or "Độ hợp" in n for n in looks[0].breakdown.explanations)
    i18n.set_language("en")
    assert "color wheel" in " ".join(score_pair("#D0312D", "#2DCCD0", "skirts").explanations)


def test_vietnamese_png_export_has_real_glyphs():
    """The export font must contain Vietnamese stacked diacritics (not 'tofu' boxes)."""
    from src.models.domain import Outfit, OutfitItem
    from src.visualizer import mannequin
    from src.visualizer.export import font

    i18n.set_language("vi")
    f = font("sans", 40)

    def render(text: str) -> bytes:
        img = Image.new("L", (200, 80), 0)
        ImageDraw.Draw(img).text((10, 10), text, font=f, fill=255)
        return img.tobytes()

    tofu = render("")  # private-use code point → .notdef glyph
    for ch in "ạềốữỹđươ":
        assert render(ch) != tofu, ch
    o = Outfit(name="Bộ đồ Hẹn hò 1")
    o.set_item(OutfitItem(slot="dress", color_hex="#713E4A"))
    assert mannequin.render_png(o, height=300)[:8] == b"\x89PNG\r\n\x1a\n"


def test_streamlit_font_supports_vietnamese():
    cfg = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "Be+Vietnam+Pro" in cfg
    assert re.search(r"headingFont = .*Cormorant", cfg)
