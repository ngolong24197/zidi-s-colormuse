"""Backup (export) and restore (import) of all personal data.

The export is a ZIP containing ``colormuse.json`` (every record) and the
wardrobe photos under ``images/``. It's backend-independent, so it can move
data between Supabase projects or restore after an accident.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from src.database.base import Repository
from src.models.domain import Collection, Outfit, UserPreferences, WardrobeItem, new_id

FORMAT_VERSION = 1
MAX_IMPORT_BYTES = 200 * 1024 * 1024


def export_data(repo: Repository) -> dict[str, Any]:
    items, _ = repo.list_items(sort="oldest")
    outfits, _ = repo.list_outfits()
    collections = repo.list_collections()
    membership = {c.id: [] for c in collections}
    for o in outfits:
        for cid in repo.collections_for_outfit(o.id):
            membership.setdefault(cid, []).append(o.id)
    return {
        "format": "colormuse-backup",
        "version": FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "preferences": repo.get_preferences().to_dict(),
        "wardrobe_items": [i.to_dict() for i in items],
        "outfits": [o.to_dict() for o in outfits],
        "collections": [{**c.to_dict(), "outfit_ids": membership.get(c.id, [])} for c in collections],
        "recommendation_history": repo.list_history(limit=100),
    }


def export_zip(repo: Repository, include_images: bool = True) -> bytes:
    data = export_data(repo)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if include_images:
            for item in data["wardrobe_items"]:
                for key in ("image_path", "thumb_path"):
                    path = item.get(key)
                    if path:
                        blob = repo.get_file(path)
                        if blob:
                            arc = f"images/{item['id']}/{'full' if key == 'image_path' else 'thumb'}.jpg"
                            zf.writestr(arc, blob)
                            item[f"backup_{key}"] = arc
        zf.writestr("colormuse.json", json.dumps(data, indent=2, default=str))
        zf.writestr("README.txt", "ColorMuse backup. Restore it from Settings → Data → Restore from backup.\n")
    return buf.getvalue()


def import_zip(repo: Repository, blob: bytes) -> dict[str, int]:
    """Add the backup's records to the current account (new IDs; nothing is overwritten)."""
    if len(blob) > MAX_IMPORT_BYTES:
        raise ValueError("Backup file is too large.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        data = json.loads(zf.read("colormuse.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("This is not a ColorMuse backup file.") from exc
    if data.get("format") != "colormuse-backup":
        raise ValueError("This is not a ColorMuse backup file.")

    counts = {"items": 0, "photos": 0, "outfits": 0, "collections": 0}
    if data.get("preferences"):
        prefs = UserPreferences.from_dict({k: v for k, v in data["preferences"].items() if k not in ("owner_id", "updated_at")})
        repo.save_preferences(prefs)

    id_map: dict[str, str] = {}
    for raw in data.get("wardrobe_items", []):
        old_id = raw["id"]
        clean = {k: v for k, v in raw.items() if not k.startswith("backup_") and k not in ("owner_id", "image_path", "thumb_path")}
        clean["id"] = new_id()
        item = repo.save_item(WardrobeItem.from_dict(clean))
        id_map[old_id] = item.id
        counts["items"] += 1
        full_arc, thumb_arc = raw.get("backup_image_path"), raw.get("backup_thumb_path")
        if full_arc and full_arc in zf.namelist():
            full = zf.read(full_arc)
            thumb = zf.read(thumb_arc) if thumb_arc and thumb_arc in zf.namelist() else full
            from src.services.image_processing import open_image

            img = open_image(full)
            repo.upload_item_image(item.id, full, thumb, img.width, img.height)
            counts["photos"] += 1

    outfit_map: dict[str, str] = {}
    for raw in data.get("outfits", []):
        o = Outfit.from_dict({k: v for k, v in raw.items() if k not in ("owner_id", "created_at", "updated_at")})
        new = o.copy(new_identity=True)
        for it in new.items:
            it.wardrobe_item_id = id_map.get(it.wardrobe_item_id or "")
        saved = repo.save_outfit(new)
        outfit_map[raw["id"]] = saved.id
        counts["outfits"] += 1

    for raw in data.get("collections", []):
        c = repo.save_collection(Collection(name=raw.get("name") or "Collection", description=raw.get("description")))
        counts["collections"] += 1
        for oid in raw.get("outfit_ids", []):
            if oid in outfit_map:
                repo.add_to_collection(c.id, outfit_map[oid])
    return counts

