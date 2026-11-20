"""Fill the LOCAL development backend with a small demo wardrobe and a couple of looks.

Run:  python scripts/seed_demo_wardrobe.py [--dir .colormuse_local]
Never run against production: it only uses the local SQLite backend.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.color_library import color_name  # noqa: E402
from src.core.outfit_engine import OutfitContext, generate_outfits  # noqa: E402
from src.database.local_repo import LocalRepository  # noqa: E402
from src.models.domain import Collection, WardrobeItem  # noqa: E402

DEMO = [
    ("Ivory silk blouse", "tops", "Blouse", "#F8F4EF", "solid", ["office", "dinner"], ["classic", "chic"]),
    ("Blush knit sweater", "tops", "Sweater", "#E8C9C5", "solid", ["casual", "daily errands"], ["romantic"]),
    ("Breton striped tee", "tops", "T-shirt", "#FBFBF9", "striped", ["casual", "travel"], ["classic", "preppy"]),
    ("Black camisole", "tops", "Camisole", "#141414", "solid", ["date night", "party"], ["chic", "edgy"]),
    ("Navy tailored trousers", "bottoms", "Trousers", "#1F2A44", "solid", ["office", "interview"], ["classic"]),
    ("Light wash jeans", "bottoms", "Jeans", "#8EA7C1", "solid", ["casual", "daily errands", "travel"], []),
    ("Camel midi skirt", "bottoms", "Midi skirt", "#C19A6B", "solid", ["office", "dinner"], ["chic"]),
    ("Burgundy slip dress", "dresses", "Slip dress", "#713E4A", "solid", ["date night", "dinner", "party"], ["glam"]),
    ("Sage floral midi dress", "dresses", "Midi dress", "#A3B18A", "floral", ["wedding guest", "beach"], ["romantic"]),
    ("Taupe trench coat", "outerwear", "Trench coat", "#C8AD91", "solid", ["office", "travel"], ["classic"]),
    ("Black leather jacket", "outerwear", "Leather jacket", "#141414", "solid", ["casual", "party"], ["edgy"]),
    ("Nude pumps", "shoes", "Pumps", "#E3BFA3", "solid", ["office", "wedding guest", "interview"], ["classic"]),
    ("White sneakers", "shoes", "Sneakers", "#FBFBF9", "solid", ["casual", "travel", "daily errands"], ["sporty"]),
    ("Black ankle boots", "shoes", "Ankle boots", "#141414", "solid", ["casual", "dinner"], ["edgy"]),
    ("Cognac tote", "bags", "Tote", "#9A5B2E", "solid", ["office", "travel"], ["classic"]),
    ("Dusty rose clutch", "bags", "Clutch", "#B77E79", "solid", ["date night", "wedding guest", "party"], ["romantic"]),
    ("Gold hoop earrings", "jewelry", "Earrings", "#C9A44C", "solid", [], ["classic", "glam"]),
    ("Pearl necklace", "jewelry", "Necklace", "#EEE7DC", "solid", ["wedding guest", "formal"], ["classic", "romantic"]),
    ("Silk patterned scarf", "scarves", "Scarf", "#B77E79", "geometric", ["office", "travel"], ["chic"]),
    ("Straw sun hat", "hats", "Sun hat", "#D8C3A5", "solid", ["beach"], ["bohemian"]),
]


def seed(root: Path, owner: str = "local-owner") -> LocalRepository:
    repo = LocalRepository(root, owner)
    existing, _ = repo.list_items()
    if existing:
        print(f"{len(existing)} items already present — skipping wardrobe seed")
        return repo
    for name, cat, sub, hx, pattern, occ, styles in DEMO:
        repo.save_item(WardrobeItem(name=name, category=cat, subcategory=sub, primary_color=hx,
                                    primary_color_name=color_name(hx), pattern=pattern, occasions=occ, styles=styles,
                                    secondary_colors=["#1F2A44"] if pattern == "striped" else
                                    ["#F3E9D2"] if pattern in ("floral", "geometric") else []))
    items, _ = repo.list_items()
    prefs = repo.get_preferences()
    prefs.display_name = "Zidi"
    repo.save_preferences(prefs)
    looks = generate_outfits(items, OutfitContext("office", "classic", None, prefs), limit=2)
    looks += generate_outfits(items, OutfitContext("date night", None, None, prefs), limit=1)
    col = repo.save_collection(Collection(name="Workweek"))
    for n, g in enumerate(looks):
        if n == 0:
            g.outfit.favorite = True
        saved = repo.save_outfit(g.outfit)
        if saved.occasion == "office":
            repo.add_to_collection(col.id, saved.id)
    print(f"seeded {len(items)} items and {len(looks)} looks into {root}")
    return repo


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / ".colormuse_local"))
    seed(Path(ap.parse_args().dir))
