"""Domain model shared by the engine, database layer and both visualizers.

All records are plain dataclasses with ``to_dict`` / ``from_dict`` so they
map 1:1 onto the Supabase tables (see database/schema.sql).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any

from src.core.color_convert import is_valid_hex, normalize_hex

# ---------------------------------------------------------------- vocabularies

CATEGORIES: tuple[str, ...] = (
    "tops", "bottoms", "dresses", "outerwear", "shoes", "bags",
    "jewelry", "accessories", "scarves", "belts", "hats",
)

CATEGORY_LABELS: dict[str, str] = {
    "tops": "Tops", "bottoms": "Bottoms", "dresses": "Dresses", "outerwear": "Outerwear",
    "shoes": "Shoes", "bags": "Bags", "jewelry": "Jewelry", "accessories": "Accessories",
    "scarves": "Scarves", "belts": "Belts", "hats": "Hats",
}

# subcategory label -> visual variant used by the SVG garment assets
SUBCATEGORIES: dict[str, dict[str, str]] = {
    "tops": {"T-shirt": "tee", "Blouse": "blouse", "Shirt": "blouse", "Sweater": "sweater",
             "Knit top": "sweater", "Tank top": "tank", "Camisole": "tank", "Bodysuit": "tank"},
    "bottoms": {"Trousers": "pants", "Jeans": "pants", "Wide-leg pants": "pants",
                "Shorts": "shorts", "Mini skirt": "skirt_mini", "Midi skirt": "skirt_midi",
                "Maxi skirt": "skirt_maxi"},
    "dresses": {"Mini dress": "dress_mini", "Midi dress": "dress_midi", "Maxi dress": "dress_maxi",
                "Slip dress": "dress_midi", "Shirt dress": "dress_midi", "Gown": "dress_maxi"},
    "outerwear": {"Blazer": "blazer", "Jacket": "blazer", "Leather jacket": "blazer",
                  "Denim jacket": "blazer", "Coat": "coat", "Trench coat": "coat",
                  "Cardigan": "cardigan"},
    "shoes": {"Heels": "heels", "Pumps": "heels", "Sandals": "heels", "Flats": "flats",
              "Loafers": "flats", "Sneakers": "sneakers", "Boots": "boots", "Ankle boots": "boots"},
    "bags": {"Handbag": "handbag", "Tote": "tote", "Clutch": "clutch", "Crossbody": "crossbody",
             "Shoulder bag": "handbag"},
    "jewelry": {"Necklace": "necklace", "Earrings": "earrings", "Bracelet": "bracelet",
                "Watch": "watch"},
    "accessories": {"Sunglasses": "sunglasses", "Watch": "watch", "Hair clip": "earrings",
                    "Gloves": "bracelet"},
    "scarves": {"Scarf": "scarf", "Shawl": "scarf"},
    "belts": {"Belt": "belt"},
    "hats": {"Sun hat": "sunhat", "Fedora": "sunhat", "Beret": "beret", "Beanie": "beanie"},
}

DEFAULT_VARIANT: dict[str, str] = {c: next(iter(v.values())) for c, v in SUBCATEGORIES.items()}

PATTERNS: tuple[str, ...] = (
    "solid", "striped", "polka dot", "plaid", "floral", "animal", "geometric", "textured",
)

SHADES: tuple[str, ...] = ("light", "medium", "dark")

SEASONS: tuple[str, ...] = ("spring", "summer", "autumn", "winter")

STYLES: tuple[str, ...] = (
    "classic", "minimalist", "romantic", "chic", "bohemian", "edgy", "sporty", "glam", "preppy",
)

OCCASIONS: tuple[str, ...] = (
    "casual", "office", "date night", "party", "wedding guest", "travel", "beach",
    "formal", "dinner", "interview", "daily errands",
)

# Outfit slots (canonical order). "nails" is a beauty slot with no wardrobe category.
SLOTS: tuple[str, ...] = (
    "bottom", "top", "dress", "belt", "outerwear", "scarf", "jewelry",
    "accessory", "bag", "shoes", "hat", "nails",
)

HAIR_STYLES: dict[str, str] = {
    "long_waves": "Long waves", "bob": "Bob", "ponytail": "Sleek ponytail", "bun": "Top bun",
    "curly": "Curls", "pixie": "Pixie cut", "side_braid": "Side braid",
}

NAIL_SHAPES: dict[str, str] = {
    "almond": "Almond", "round": "Round", "square": "Square", "french": "French tip",
}

# Natural hair shades offered in the hair color picker (any hex is still allowed)
HAIR_COLORS: dict[str, str] = {
    "Jet black": "#1B1716", "Espresso brown": "#3B2A24", "Chestnut": "#6A3F2A", "Auburn": "#8A3B24",
    "Copper": "#B5562B", "Honey blonde": "#C9975B", "Golden blonde": "#DDB66F", "Platinum": "#E8DFCF",
    "Ash brown": "#7A6656", "Silver gray": "#B9B6B2", "Rose pink": "#D892A0", "Burgundy": "#5C1F2E",
}

CATEGORY_TO_SLOT: dict[str, str] = {
    "tops": "top", "bottoms": "bottom", "dresses": "dress", "outerwear": "outerwear",
    "shoes": "shoes", "bags": "bag", "jewelry": "jewelry", "accessories": "accessory",
    "scarves": "scarf", "belts": "belt", "hats": "hat",
}
SLOT_TO_CATEGORY: dict[str, str] = {v: k for k, v in CATEGORY_TO_SLOT.items()}

SLOT_LABELS: dict[str, str] = {
    "top": "Top", "bottom": "Bottom", "dress": "Dress", "outerwear": "Outerwear",
    "shoes": "Shoes", "bag": "Bag", "jewelry": "Jewelry", "accessory": "Accessory",
    "scarf": "Scarf", "belt": "Belt", "hat": "Hat", "nails": "Nails",
}


_last_ts: list[datetime] = []


def utcnow() -> str:
    """ISO timestamp, strictly increasing within the process (Windows clocks are coarse)."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    if _last_ts and now <= _last_ts[0]:
        now = _last_ts[0] + timedelta(microseconds=1)
    _last_ts[:] = [now]
    return now.isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def variant_for(category: str, subcategory: str | None) -> str:
    options = SUBCATEGORIES.get(category, {})
    if subcategory and subcategory in options:
        return options[subcategory]
    return DEFAULT_VARIANT.get(category, "tee")


def _filter_kwargs(cls, data: dict[str, Any]) -> dict[str, Any]:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def _clean_hex_list(values: Any) -> list[str]:
    out: list[str] = []
    for v in values or []:
        if is_valid_hex(v):
            hx = normalize_hex(v)
            if hx not in out:
                out.append(hx)
    return out


# ---------------------------------------------------------------- records

@dataclass
class WardrobeItem:
    name: str
    category: str
    primary_color: str
    id: str = field(default_factory=new_id)
    subcategory: str | None = None
    primary_color_name: str | None = None
    secondary_colors: list[str] = field(default_factory=list)
    shade: str | None = None
    pattern: str = "solid"
    brand: str | None = None
    seasons: list[str] = field(default_factory=list)
    styles: list[str] = field(default_factory=list)
    occasions: list[str] = field(default_factory=list)
    notes: str | None = None
    favorite: bool = False
    image_path: str | None = None
    thumb_path: str | None = None
    owner_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Item name is required")
        self.name = self.name.strip()[:120]
        if self.category not in CATEGORIES:
            raise ValueError(f"Unknown category: {self.category}")
        self.primary_color = normalize_hex(self.primary_color)
        self.secondary_colors = _clean_hex_list(self.secondary_colors)[:4]
        if self.pattern not in PATTERNS:
            self.pattern = "solid"
        if self.shade is not None and self.shade not in SHADES:
            self.shade = None
        self.seasons = [s for s in self.seasons if s in SEASONS]
        self.styles = [s for s in self.styles if s in STYLES]
        self.occasions = [o for o in self.occasions if o in OCCASIONS]

    @property
    def slot(self) -> str:
        return CATEGORY_TO_SLOT[self.category]

    @property
    def variant(self) -> str:
        return variant_for(self.category, self.subcategory)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WardrobeItem":
        d = _filter_kwargs(cls, data)
        for key in ("secondary_colors", "seasons", "styles", "occasions"):
            if d.get(key) is None:
                d[key] = []
        d["favorite"] = bool(d.get("favorite", False))
        return cls(**d)


@dataclass
class ClothingImage:
    wardrobe_item_id: str
    storage_path: str
    thumb_path: str
    id: str = field(default_factory=new_id)
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None
    content_type: str = "image/jpeg"
    is_primary: bool = True
    owner_id: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClothingImage":
        return cls(**_filter_kwargs(cls, data))


@dataclass
class OutfitItem:
    """One slot of an outfit. Either linked to a wardrobe item or a free color."""

    slot: str
    color_hex: str
    id: str = field(default_factory=new_id)
    wardrobe_item_id: str | None = None
    secondary_hex: str | None = None
    pattern: str = "solid"
    variant: str | None = None
    label: str | None = None
    position: int = 0
    outfit_id: str | None = None
    owner_id: str | None = None

    def __post_init__(self) -> None:
        if self.slot not in SLOTS:
            raise ValueError(f"Unknown slot: {self.slot}")
        self.color_hex = normalize_hex(self.color_hex)
        if self.secondary_hex:
            self.secondary_hex = normalize_hex(self.secondary_hex)
        if self.pattern not in PATTERNS:
            self.pattern = "solid"
        if self.slot == "nails":
            if self.variant not in NAIL_SHAPES:
                self.variant = "almond"
            self.pattern = "solid"
        elif not self.variant:
            self.variant = DEFAULT_VARIANT[SLOT_TO_CATEGORY[self.slot]]

    @classmethod
    def from_wardrobe(cls, item: WardrobeItem) -> "OutfitItem":
        return cls(
            slot=item.slot,
            color_hex=item.primary_color,
            wardrobe_item_id=item.id,
            secondary_hex=item.secondary_colors[0] if item.secondary_colors else None,
            pattern=item.pattern,
            variant=item.variant,
            label=item.name,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OutfitItem":
        return cls(**_filter_kwargs(cls, data))


@dataclass
class Outfit:
    """The single outfit model rendered by both the flat-lay and the mannequin."""

    name: str = "Untitled look"
    id: str = field(default_factory=new_id)
    occasion: str | None = None
    style: str | None = None
    season: str | None = None
    notes: str | None = None
    favorite: bool = False
    layout: str = "editorial"
    skin_tone: str = "#E8C4A8"
    hair_color: str = "#3B2A24"
    hair_style: str = "long_waves"
    score: float | None = None
    items: list[OutfitItem] = field(default_factory=list)
    owner_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    # ---- slot helpers (a dress replaces top + bottom)
    def __post_init__(self) -> None:
        if self.hair_style not in HAIR_STYLES:
            self.hair_style = "long_waves"
        self.skin_tone = normalize_hex(self.skin_tone) if is_valid_hex(self.skin_tone) else "#E8C4A8"
        self.hair_color = normalize_hex(self.hair_color) if is_valid_hex(self.hair_color) else "#3B2A24"

    def get(self, slot: str) -> OutfitItem | None:
        return next((i for i in self.items if i.slot == slot), None)

    def set_item(self, item: OutfitItem) -> None:
        self.items = [i for i in self.items if i.slot != item.slot]
        if item.slot == "dress":
            self.items = [i for i in self.items if i.slot not in ("top", "bottom")]
        elif item.slot in ("top", "bottom"):
            self.items = [i for i in self.items if i.slot != "dress"]
        self.items.append(item)
        self._reorder()

    def remove(self, slot: str) -> None:
        self.items = [i for i in self.items if i.slot != slot]
        self._reorder()

    def _reorder(self) -> None:
        self.items.sort(key=lambda i: SLOTS.index(i.slot))
        for pos, it in enumerate(self.items):
            it.position = pos

    @property
    def colors(self) -> list[str]:
        """Clothing/accessory colors (nails excluded; they're scored separately)."""
        return [i.color_hex for i in self.items if i.slot != "nails"]

    @property
    def garments(self) -> list[OutfitItem]:
        return [i for i in self.items if i.slot != "nails"]

    @property
    def wardrobe_item_ids(self) -> list[str]:
        return [i.wardrobe_item_id for i in self.items if i.wardrobe_item_id]

    def is_complete(self) -> bool:
        has_body = self.get("dress") is not None or (
            self.get("top") is not None and self.get("bottom") is not None
        )
        return has_body and self.get("shoes") is not None

    def copy(self, *, new_identity: bool = False) -> "Outfit":
        clone = Outfit.from_dict(self.to_dict())
        if new_identity:
            clone.id = new_id()
            clone.created_at = clone.updated_at = None
            for it in clone.items:
                it.id = new_id()
                it.outfit_id = clone.id
        return clone

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def record(self) -> dict[str, Any]:
        """Row for the ``outfits`` table (items are stored in ``outfit_items``)."""
        d = asdict(self)
        d.pop("items")
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Outfit":
        d = _filter_kwargs(cls, data)
        d["items"] = [OutfitItem.from_dict(i) if isinstance(i, dict) else i for i in d.get("items") or []]
        d["favorite"] = bool(d.get("favorite", False))
        outfit = cls(**d)
        outfit._reorder()
        return outfit


@dataclass
class Collection:
    name: str
    id: str = field(default_factory=new_id)
    description: str | None = None
    owner_id: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Collection":
        return cls(**_filter_kwargs(cls, data))


DEFAULT_WEIGHTS: dict[str, float] = {
    "harmony": 0.35,
    "contrast": 0.20,
    "category": 0.15,
    "occasion": 0.10,
    "style": 0.10,
    "preference": 0.10,
}


@dataclass
class UserPreferences:
    display_name: str = ""
    favorite_colors: list[str] = field(default_factory=list)
    disliked_colors: list[str] = field(default_factory=list)
    preferred_styles: list[str] = field(default_factory=list)
    occasion_preferences: list[str] = field(default_factory=list)
    seasons: list[str] = field(default_factory=list)
    scoring_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    skin_tone: str = "#E8C4A8"
    hair_color: str = "#3B2A24"
    hair_style: str = "long_waves"
    nail_shape: str = "almond"
    owner_id: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        self.favorite_colors = _clean_hex_list(self.favorite_colors)
        self.disliked_colors = _clean_hex_list(self.disliked_colors)
        self.preferred_styles = [s for s in self.preferred_styles if s in STYLES]
        self.occasion_preferences = [o for o in self.occasion_preferences if o in OCCASIONS]
        self.seasons = [s for s in self.seasons if s in SEASONS]
        merged = dict(DEFAULT_WEIGHTS)
        for k, v in (self.scoring_weights or {}).items():
            if k in merged:
                try:
                    merged[k] = max(0.0, float(v))
                except (TypeError, ValueError):
                    pass
        self.scoring_weights = merged
        self.skin_tone = normalize_hex(self.skin_tone) if is_valid_hex(self.skin_tone) else "#E8C4A8"
        self.hair_color = normalize_hex(self.hair_color) if is_valid_hex(self.hair_color) else "#3B2A24"
        if self.hair_style not in HAIR_STYLES:
            self.hair_style = "long_waves"
        if self.nail_shape not in NAIL_SHAPES:
            self.nail_shape = "almond"

    def normalized_weights(self) -> dict[str, float]:
        total = sum(self.scoring_weights.values()) or 1.0
        return {k: v / total for k, v in self.scoring_weights.items()}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "UserPreferences":
        if not data:
            return cls()
        d = _filter_kwargs(cls, data)
        for key in ("favorite_colors", "disliked_colors", "preferred_styles", "occasion_preferences", "seasons"):
            if d.get(key) is None:
                d[key] = []
        if not d.get("scoring_weights"):
            d["scoring_weights"] = dict(DEFAULT_WEIGHTS)
        return cls(**d)
