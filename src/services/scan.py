"""Camera scan: one snapshot → colors → recommendations → (optional) save to the wardrobe.

Pure service layer (no Streamlit) used by the Scan page and the companion app.
The centre of the frame is analysed (the piece the camera is pointed at), with
background reduction, so the owner doesn't need to crop anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.beauty import NailSuggestion, recommend_nails
from src.core.color_convert import color_distance, shade_of
from src.core.recommender import MatchRequest, Recommendation, recommend, target_categories, wardrobe_matches
from src.database.base import Repository
from src.i18n import cname, label
from src.models.domain import SUBCATEGORIES, UserPreferences, WardrobeItem, new_id
from src.services import image_processing as ip

# Analyse the middle of the frame, where the piece is when the camera is pointed at it.
SCAN_CROP = (0.18, 0.12, 0.82, 0.88)
# Categories shown in the compact scan results (the full matcher shows all of them)
QUICK_CATEGORIES = ("shirts", "pants", "skirts", "shoes", "handbags", "jewelry", "outerwear")
SIMILAR_DELTA_E = 9.0


@dataclass
class ScanResult:
    image: bytes
    category: str
    extraction: ip.ExtractionResult
    request: MatchRequest
    recommendations: dict[str, list[Recommendation]] = field(default_factory=dict)
    owned_matches: dict[str, list[Recommendation]] = field(default_factory=dict)
    similar_owned: list[WardrobeItem] = field(default_factory=list)
    nails: list[NailSuggestion] = field(default_factory=list)

    @property
    def main_hex(self) -> str:
        return self.request.base_hex

    @property
    def secondary(self) -> list[str]:
        return self.request.secondary

    def suggested_name(self, subcategory: str | None = None) -> str:
        """e.g. 'Dusty Rose blouse' / 'Áo blouse Hồng đất' — editable before saving."""
        from src.i18n import get_language

        kind = label("subcategory", subcategory) if subcategory else label("category", self.category)
        color = cname(self.main_hex)
        if get_language() == "vi":
            return f"{kind} {color.lower()}"
        return f"{color} {kind.lower()}"


def analyze(
    image_bytes: bytes,
    category: str,
    *,
    prefs: UserPreferences | None = None,
    wardrobe: list[WardrobeItem] | None = None,
    main_hex: str | None = None,
    occasion: str | None = None,
    per_category: int = 2,
) -> ScanResult:
    """Validate the snapshot, extract colors from the centre, and build recommendations.

    ``main_hex`` overrides the detected main color (manual correction).
    Raises ``image_processing.ImageValidationError`` for unusable images.
    """
    img = ip.validate_image(image_bytes, None)
    extraction = ip.extract_colors(img, SCAN_CROP, reduce_background=True)
    detected = extraction.primary.hex if extraction.primary else "#808080"
    base = main_hex or detected
    secondary = [c.hex for c in extraction.secondary if color_distance(c.hex, base) > 6][:3]
    req = MatchRequest(base_hex=base, base_category=category, secondary=secondary,
                       shade=shade_of(base), occasion=occasion, prefs=prefs)
    cats = [c for c in QUICK_CATEGORIES if c in target_categories(category)]
    recs = recommend(req, cats, limit=per_category)
    wardrobe = wardrobe or []
    owned = {c: wardrobe_matches(req, wardrobe, c, limit=2) for c in cats}
    owned = {c: v for c, v in owned.items() if v}
    similar = sorted(
        (w for w in wardrobe if w.category == category and color_distance(w.primary_color, base) < SIMILAR_DELTA_E),
        key=lambda w: (color_distance(w.primary_color, base), w.name),
    )
    nails = recommend_nails(base_colors=[(category, base)], occasion=occasion, prefs=prefs,
                            skin_tone=prefs.skin_tone if prefs else None, limit=4)
    return ScanResult(image_bytes, category, extraction, req, recs, owned, similar[:3], nails)


def subcategories_for(category: str) -> list[str]:
    return list(SUBCATEGORIES.get(category, {}))


def save_to_wardrobe(
    repo: Repository,
    result: ScanResult,
    *,
    name: str,
    subcategory: str | None = None,
    pattern: str = "solid",
    favorite: bool = False,
) -> WardrobeItem:
    """Create the wardrobe piece and upload the optimized photo (cropped to the scanned centre)."""
    item = WardrobeItem(
        id=new_id(), name=name, category=result.category, subcategory=subcategory,
        primary_color=result.main_hex, primary_color_name=None, secondary_colors=result.secondary,
        shade=shade_of(result.main_hex), pattern=pattern, favorite=favorite,
        notes=None,
    )
    from src.core.color_library import color_name

    item.primary_color_name = color_name(item.primary_color)
    saved = repo.save_item(item)
    processed = ip.process_upload(result.image, None, SCAN_CROP)
    repo.upload_item_image(saved.id, processed.full, processed.thumb, processed.width, processed.height)
    return repo.get_item(saved.id) or saved
