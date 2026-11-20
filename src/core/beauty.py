"""Beauty styling: nail polish colors, hairstyles and hair-color harmony.

Deterministic and explainable like the rest of the engine:
* nail colors are scored against every garment color (weighted by how visible
  the piece is) with the same harmony/contrast/occasion/style/taste scoring;
* hairstyles are chosen with transparent rules based on neckline, hats,
  earrings and the occasion;
* "colors that flatter your hair" scores colors worn near the face against the
  owner's hair color.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.color_convert import color_distance, normalize_hex
from src.core.color_library import COLOR_LIBRARY, color_name, get_color
from src.core.scoring import score_pair
from src.models.domain import HAIR_STYLES, Outfit, UserPreferences

NAIL_SLOT_WEIGHT = {
    "top": 1.0, "bottom": 0.7, "dress": 1.4, "outerwear": 0.8, "shoes": 0.8, "bag": 0.9,
    "jewelry": 0.6, "accessory": 0.4, "scarf": 0.6, "belt": 0.3, "hat": 0.4,
}
# Polish shades people actually wear: the whole library except muddy mid-tones
_NAIL_EXCLUDE_FAMILIES = {"gray"}
_NAIL_EXTRA = ("Nude", "Ballet Pink", "Blush", "Cherry Red", "Wine", "Oxblood", "Burgundy", "Coral",
               "Rose Gold", "Gold", "Silver", "Optic White", "Black", "Mauve", "Lavender", "Navy")


def nail_pool() -> tuple:
    names = set(_NAIL_EXTRA)
    return tuple(c for c in COLOR_LIBRARY
                 if c.name in names or (c.family not in _NAIL_EXCLUDE_FAMILIES and c.family != "metallic"))


@dataclass
class NailSuggestion:
    hex: str
    name: str
    score: float
    explanations: list[str] = field(default_factory=list)


def recommend_nails(
    outfit: Outfit | None = None,
    *,
    base_colors: list[tuple[str, str]] | None = None,
    occasion: str | None = None,
    style: str | None = None,
    prefs: UserPreferences | None = None,
    skin_tone: str | None = None,
    limit: int = 5,
    diverse: bool = True,
) -> list[NailSuggestion]:
    """Best polish colors for an outfit (or for (slot, hex) base colors)."""
    if base_colors is None:
        base_colors = [(i.slot, i.color_hex) for i in (outfit.garments if outfit else [])]
        occasion = occasion or (outfit.occasion if outfit else None)
        style = style or (outfit.style if outfit else None)
        skin_tone = skin_tone or (outfit.skin_tone if outfit else None)
    if not base_colors:
        base_colors = [("top", "#F8F4EF")]
    results: list[NailSuggestion] = []
    for cand in nail_pool():
        total_w, acc, best_reason, best_val = 0.0, 0.0, "", -1.0
        for slot, hx in base_colors:
            w = NAIL_SLOT_WEIGHT.get(slot, 0.5)
            bd = score_pair(hx, cand.hex, "nails", occasion=occasion, style=style, prefs=prefs)
            acc += bd.total * w
            total_w += w
            if bd.total * w > best_val:
                best_val, best_reason = bd.total * w, bd.explanations[0] if bd.explanations else ""
        score = acc / total_w
        notes = [best_reason] if best_reason else []
        # Echoing the shoes or bag is a classic, polished finishing touch
        for slot, hx in base_colors:
            if slot in ("shoes", "bag") and color_distance(hx, cand.hex) < 10:
                score += 3
                notes.append(f"Echoes your {slot} — a polished, intentional finish.")
                break
        if skin_tone and cand.family in ("beige", "pink") and color_distance(skin_tone, cand.hex) < 14:
            score += 2
            notes.append("A your-skin-but-better nude that elongates the fingers and goes with everything.")
        results.append(NailSuggestion(cand.hex, cand.name, round(min(score, 100.0), 1), notes))
    results.sort(key=lambda r: (-r.score, r.name))
    if not diverse:
        return results[:limit]
    picked, families = [], set()
    for r in results:
        fam = get_color(r.name).family  # type: ignore[union-attr]
        if fam in families:
            continue
        picked.append(r)
        families.add(fam)
        if len(picked) == limit:
            break
    return picked


# ---------------------------------------------------------------- hairstyles

SHORT_STYLES = ("bob", "pixie")
_OCCASION_HAIR: dict[str, dict[str, float]] = {
    "office": {"ponytail": 0.3, "bun": 0.25, "bob": 0.2, "pixie": 0.15},
    "interview": {"bun": 0.3, "ponytail": 0.3, "bob": 0.2, "pixie": 0.15},
    "formal": {"bun": 0.3, "long_waves": 0.2, "side_braid": 0.15, "bob": 0.15},
    "wedding guest": {"bun": 0.25, "long_waves": 0.25, "side_braid": 0.2, "bob": 0.15},
    "date night": {"long_waves": 0.3, "curly": 0.25, "bob": 0.2},
    "dinner": {"long_waves": 0.25, "bun": 0.15, "bob": 0.2},
    "party": {"curly": 0.3, "long_waves": 0.2, "pixie": 0.2},
    "beach": {"side_braid": 0.3, "bun": 0.2, "long_waves": 0.15, "pixie": 0.1},
    "travel": {"ponytail": 0.25, "side_braid": 0.2, "bun": 0.2},
    "casual": {"ponytail": 0.2, "long_waves": 0.15, "side_braid": 0.15, "bob": 0.1},
    "daily errands": {"ponytail": 0.25, "bun": 0.2, "side_braid": 0.1},
}


@dataclass
class HairSuggestion:
    style: str
    label: str
    score: float
    reasons: list[str] = field(default_factory=list)


def recommend_hairstyles(outfit: Outfit, prefs: UserPreferences | None = None, limit: int = 3) -> list[HairSuggestion]:
    usual = prefs.hair_style if prefs else None
    short_hair = usual in SHORT_STYLES
    allowed = [s for s in HAIR_STYLES if (s in SHORT_STYLES) == short_hair]
    scores = {s: 0.6 for s in allowed}
    reasons: dict[str, list[str]] = {s: [] for s in allowed}

    def bump(style: str, val: float, why: str) -> None:
        if style in scores:
            scores[style] += val
            if why and val > 0:
                reasons[style].append(why)

    occ = outfit.occasion
    for style, val in _OCCASION_HAIR.get(occ or "", {}).items():
        bump(style, val, f"Suits {occ}.")
    top, dress, scarf = outfit.get("top"), outfit.get("dress"), outfit.get("scarf")
    hat, jewelry, outer = outfit.get("hat"), outfit.get("jewelry"), outfit.get("outerwear")
    if scarf or (top and top.variant == "sweater"):
        for s in ("bun", "ponytail", "pixie"):
            bump(s, 0.15, "Keeps a high neckline or scarf uncluttered.")
    if (top and top.variant == "blouse") or dress:
        bump("long_waves", 0.1, "Soft waves frame a V-neckline.")
        bump("bob", 0.08, "A bob frames the neckline.")
    if (top and top.variant == "tank") or dress:
        bump("bun", 0.1, "An up-do shows off bare shoulders.")
    if hat:
        for s in ("long_waves", "side_braid", "bob"):
            bump(s, 0.15, "Sits comfortably under a hat.")
        bump("bun", -0.35, "")
        bump("curly", -0.1, "")
    if jewelry and jewelry.variant in ("earrings", "necklace"):
        for s in ("bun", "ponytail", "pixie"):
            bump(s, 0.15, f"Shows off your {jewelry.variant}.")
    if outer and outer.variant == "coat":
        bump("ponytail", 0.05, "Stays neat over a coat collar.")
    if usual in scores:
        bump(usual, 0.05, "Your everyday style.")
    out = [HairSuggestion(s, HAIR_STYLES[s], round(min(1.0, v) * 100, 1), reasons[s] or ["A versatile choice."])
           for s, v in scores.items()]
    out.sort(key=lambda h: (-h.score, h.style))
    return out[:limit]


# ---------------------------------------------------------------- hair color harmony

@dataclass
class HairColorMatch:
    hex: str
    name: str
    score: float
    explanation: str


def colors_for_hair(hair_hex: str, limit: int = 6, prefs: UserPreferences | None = None) -> list[HairColorMatch]:
    """Colors that flatter the owner's hair color when worn near the face."""
    hair_hex = normalize_hex(hair_hex)
    scored = []
    for c in COLOR_LIBRARY:
        if c.family == "metallic":
            continue
        bd = score_pair(hair_hex, c.hex, "tops", prefs=prefs)
        dist = color_distance(hair_hex, c.hex)
        total = bd.total - (12 if dist < 10 else 0)  # same as hair: face and hair blur together
        expl = bd.explanations[0] if bd.explanations else ""
        scored.append(HairColorMatch(c.hex, c.name, round(total, 1), expl))
    scored.sort(key=lambda m: (-m.score, m.name))
    picked, fams = [], set()
    for m in scored:
        fam = get_color(m.name).family  # type: ignore[union-attr]
        if fam in fams:
            continue
        picked.append(m)
        fams.add(fam)
        if len(picked) == limit:
            break
    return picked


def hair_note(outfit: Outfit) -> str:
    """One-line comment on how the piece nearest the face works with the hair color."""
    near_face = outfit.get("scarf") or outfit.get("top") or outfit.get("dress") or outfit.get("outerwear")
    if not near_face:
        return ""
    d = color_distance(near_face.color_hex, outfit.hair_color)
    hair, piece = color_name(outfit.hair_color), color_name(near_face.color_hex)
    if d < 10:
        return f"{piece} is very close to your {hair.lower()} hair — add earrings or a scarf to separate them."
    bd = score_pair(outfit.hair_color, near_face.color_hex, "tops")
    if bd.components["harmony"] >= 0.8:
        return f"{piece} near the face flatters {hair.lower()} hair ({bd.rule} pairing)."
    return f"{piece} with {hair.lower()} hair is a bolder pairing."
