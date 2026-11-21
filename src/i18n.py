"""Internationalisation: English (source) and Vietnamese.

Usage
-----
    from src.i18n import _, label, cname
    _("Save piece")                                   # UI sentence
    _("Hello, {name}", name="Zidi")                  # with placeholders
    label("occasion", "date night")                  # vocabulary value → display label
    cname("#B77E79")                                  # localized color name

English strings in the code are the translation keys (gettext style); the
Vietnamese table lives in ``src/i18n_vi.py``. A test checks that every
``_("...")`` literal in the code has a Vietnamese entry.

The active language is a ``ContextVar`` so it is per Streamlit session/run
and the engine stays pure: same inputs + same language → same output.
"""

from __future__ import annotations

from contextvars import ContextVar

LANGUAGES: dict[str, str] = {"en": "English", "vi": "Tiếng Việt"}
DEFAULT_LANGUAGE = "en"

_LANG: ContextVar[str] = ContextVar("colormuse_language", default=DEFAULT_LANGUAGE)


def set_language(code: str | None) -> str:
    code = code if code in LANGUAGES else DEFAULT_LANGUAGE
    _LANG.set(code)
    return code


def get_language() -> str:
    return _LANG.get()


def _table() -> dict[str, str]:
    if _LANG.get() == "vi":
        from src.i18n_vi import VI

        return VI
    return {}


def _(text: str, **kwargs) -> str:
    """Translate ``text`` (English source) and fill ``{placeholders}``."""
    s = _table().get(text, text)
    return s.format(**kwargs) if kwargs else s


tr = _


def N_(text: str) -> str:
    """Mark a string for translation without translating it yet (translated later via ``_(var)``)."""
    return text


# ---------------------------------------------------------------- vocabulary labels
_EN_LABELS: dict[str, dict[str, str]] = {
    "category": {
        "tops": "Tops", "bottoms": "Bottoms", "dresses": "Dresses", "outerwear": "Outerwear",
        "shoes": "Shoes", "bags": "Bags", "jewelry": "Jewelry", "accessories": "Accessories",
        "scarves": "Scarves", "belts": "Belts", "hats": "Hats",
    },
    "slot": {
        "top": "Top", "bottom": "Bottom", "dress": "Dress", "outerwear": "Outerwear", "shoes": "Shoes",
        "bag": "Bag", "jewelry": "Jewelry", "accessory": "Accessory", "scarf": "Scarf", "belt": "Belt",
        "hat": "Hat", "nails": "Nails",
    },
    "hair": {
        "long_waves": "Long waves", "bob": "Bob", "ponytail": "Sleek ponytail", "bun": "Top bun",
        "curly": "Curls", "pixie": "Pixie cut", "side_braid": "Side braid",
    },
    "nail": {"almond": "Almond", "round": "Round", "square": "Square", "french": "French tip"},
    "component": {
        "harmony": "Color harmony", "contrast": "Contrast & balance", "category": "Category fit",
        "occasion": "Occasion", "style": "Style", "preference": "Your taste",
    },
    "rec": {
        "shirts": "Shirts & tops", "skirts": "Skirts", "pants": "Pants", "dresses": "Dresses",
        "shoes": "Shoes", "handbags": "Handbags", "jewelry": "Jewelry", "accessories": "Accessories",
        "outerwear": "Outerwear",
    },
    "layout": {
        "editorial": "Editorial — hero pieces centre, accessories in side columns",
        "grid": "Grid — every piece in an even grid",
        "minimal": "Minimal — main pieces with a row of accessories beneath",
    },
    "sort": {
        "newest": "Newest first", "oldest": "Oldest first", "name": "Name A–Z", "category": "Category",
        "color": "Color (light → dark)", "favorites": "Favorites first",
    },
}


def label(kind: str, value: str | None) -> str:
    """Display label for a vocabulary value (category, occasion, color name, ...)."""
    if value is None:
        return ""
    lang = _LANG.get()
    if lang == "vi":
        from src.i18n_vi import VI_LABELS

        hit = VI_LABELS.get(kind, {}).get(value)
        if hit:
            return hit
    en = _EN_LABELS.get(kind, {}).get(value)
    if en:
        return en
    if kind in ("variant",):
        return value.replace("_", " ").title()
    if kind in ("occasion", "style", "season", "pattern", "shade", "rule"):
        return value[:1].upper() + value[1:]
    return value


def cname(hex_or_name: str) -> str:
    """Localized name of a color (hex → nearest library color)."""
    from src.core.color_convert import is_valid_hex
    from src.core.color_library import color_name

    name = color_name(hex_or_name) if is_valid_hex(hex_or_name) else hex_or_name
    return label("color", name)


def format_func(kind: str, none_text: str | None = None):
    """Helper for Streamlit selectboxes: ``format_func=format_func("occasion", "Any occasion")``."""
    def fmt(value):
        if value is None:
            return _(none_text) if none_text else "—"
        return label(kind, value)
    return fmt
