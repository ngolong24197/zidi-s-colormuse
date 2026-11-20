"""Local development backend: SQLite file + image folder.

FOR DEVELOPMENT AND AUTOMATED TESTS ONLY. Streamlit Community Cloud has an
ephemeral filesystem, so production must use the Supabase backend.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Any

from src.core.color_library import COLOR_LIBRARY
from src.database.base import (
    NotFound,
    Repository,
    item_matches,
    sanitize_search,
    sort_items,
)
from src.models.domain import (
    ClothingImage,
    Collection,
    Outfit,
    OutfitItem,
    UserPreferences,
    WardrobeItem,
    new_id,
    utcnow,
)

_TABLES = ("user_preferences", "wardrobe_items", "clothing_images", "outfits", "outfit_items",
           "outfit_collections", "collection_outfits", "recommendation_history")


class LocalRepository(Repository):
    backend_name = "local"

    def __init__(self, root: str | Path, owner_id: str = "local-owner") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "files").mkdir(exist_ok=True)
        self.owner_id = owner_id
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.root / "colormuse.sqlite3", check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys = ON")
        with self._db:
            for t in _TABLES:
                self._db.execute(
                    f"CREATE TABLE IF NOT EXISTS {t} (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
                    "created_at TEXT, updated_at TEXT, ref TEXT, data TEXT NOT NULL)"
                )
                self._db.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_owner ON {t}(owner_id, ref)")

    # ---------------------------------------------------------------- low level
    def _put(self, table: str, row_id: str, data: dict[str, Any], ref: str | None = None) -> dict[str, Any]:
        now = utcnow()
        with self._lock, self._db:
            cur = self._db.execute(f"SELECT created_at FROM {table} WHERE id=? AND owner_id=?", (row_id, self.owner_id))
            existing = cur.fetchone()
            other = self._db.execute(f"SELECT owner_id FROM {table} WHERE id=?", (row_id,)).fetchone()
            if other and other[0] != self.owner_id:
                raise NotFound("Record belongs to another owner")
            created = existing[0] if existing else (data.get("created_at") or now)
            data = {**data, "owner_id": self.owner_id, "created_at": created, "updated_at": now}
            self._db.execute(
                f"INSERT OR REPLACE INTO {table} (id, owner_id, created_at, updated_at, ref, data) VALUES (?,?,?,?,?,?)",
                (row_id, self.owner_id, created, now, ref, json.dumps(data)),
            )
        return data

    def _get(self, table: str, row_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(f"SELECT data FROM {table} WHERE id=? AND owner_id=?", (row_id, self.owner_id)).fetchone()
        return json.loads(row[0]) if row else None

    def _all(self, table: str, ref: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if ref is None:
                rows = self._db.execute(f"SELECT data FROM {table} WHERE owner_id=?", (self.owner_id,)).fetchall()
            else:
                rows = self._db.execute(f"SELECT data FROM {table} WHERE owner_id=? AND ref=?", (self.owner_id, ref)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def _del(self, table: str, row_id: str | None = None, ref: str | None = None) -> None:
        with self._lock, self._db:
            if row_id is not None:
                self._db.execute(f"DELETE FROM {table} WHERE id=? AND owner_id=?", (row_id, self.owner_id))
            elif ref is not None:
                self._db.execute(f"DELETE FROM {table} WHERE ref=? AND owner_id=?", (ref, self.owner_id))

    def _file_path(self, path: str) -> Path:
        p = (self.root / "files" / path).resolve()
        if not str(p).startswith(str((self.root / "files").resolve())) or not path.startswith(self.owner_id + "/"):
            raise NotFound("Invalid file path")
        return p

    # ---------------------------------------------------------------- preferences
    def get_preferences(self) -> UserPreferences:
        return UserPreferences.from_dict(self._get("user_preferences", self.owner_id))

    def save_preferences(self, prefs: UserPreferences) -> UserPreferences:
        data = self._put("user_preferences", self.owner_id, prefs.to_dict())
        return UserPreferences.from_dict(data)

    # ---------------------------------------------------------------- wardrobe
    def list_items(self, *, search=None, category=None, favorite=None, season=None, sort="newest",
                   limit=None, offset=0):
        q = sanitize_search(search)
        items = [WardrobeItem.from_dict(d) for d in self._all("wardrobe_items")]
        items = [i for i in items if item_matches(i, q, category, favorite, season)]
        items = sort_items(items, sort)
        total = len(items)
        if limit is not None:
            items = items[offset: offset + limit]
        return items, total

    def get_item(self, item_id):
        d = self._get("wardrobe_items", item_id)
        return WardrobeItem.from_dict(d) if d else None

    def save_item(self, item):
        item.validate()
        return WardrobeItem.from_dict(self._put("wardrobe_items", item.id, item.to_dict()))

    def delete_item(self, item_id):
        if self._get("wardrobe_items", item_id) is None:
            raise NotFound("Item not found")
        self.delete_item_images(item_id)
        self._del("wardrobe_items", item_id)
        # outfit_items keep their color but lose the link (ON DELETE SET NULL)
        for oi in self._all("outfit_items"):
            if oi.get("wardrobe_item_id") == item_id:
                oi["wardrobe_item_id"] = None
                self._put("outfit_items", oi["id"], oi, ref=oi["outfit_id"])

    # ---------------------------------------------------------------- images
    def upload_item_image(self, item_id, full, thumb, width, height, content_type="image/jpeg"):
        item = self.get_item(item_id)
        if item is None:
            raise NotFound("Item not found")
        self.delete_item_images(item_id)
        image_id = new_id()
        full_path = f"{self.owner_id}/items/{item_id}/{image_id}.jpg"
        thumb_path = f"{self.owner_id}/thumbs/{item_id}/{image_id}.jpg"
        for path, data in ((full_path, full), (thumb_path, thumb)):
            fp = self._file_path(path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(data)
        img = ClothingImage(item_id, full_path, thumb_path, id=image_id, width=width, height=height,
                            size_bytes=len(full), content_type=content_type)
        self._put("clothing_images", image_id, img.to_dict(), ref=item_id)
        item.image_path, item.thumb_path = full_path, thumb_path
        self.save_item(item)
        return ClothingImage.from_dict(self._get("clothing_images", image_id))  # type: ignore[arg-type]

    def list_item_images(self, item_id):
        return [ClothingImage.from_dict(d) for d in self._all("clothing_images", ref=item_id)]

    def delete_item_images(self, item_id):
        for img in self.list_item_images(item_id):
            for path in (img.storage_path, img.thumb_path):
                try:
                    self._file_path(path).unlink(missing_ok=True)
                except NotFound:
                    pass
        self._del("clothing_images", ref=item_id)
        item = self.get_item(item_id)
        if item and (item.image_path or item.thumb_path):
            item.image_path = item.thumb_path = None
            self._put("wardrobe_items", item.id, item.to_dict())

    def get_file(self, path):
        try:
            fp = self._file_path(path)
        except NotFound:
            return None
        return fp.read_bytes() if fp.exists() else None

    # ---------------------------------------------------------------- colors
    def list_colors(self):
        return [{"name": c.name, "hex": c.hex, "family": c.family, "is_neutral": c.is_neutral} for c in COLOR_LIBRARY]

    # ---------------------------------------------------------------- outfits
    def _load_outfit(self, d: dict[str, Any]) -> Outfit:
        items = sorted(self._all("outfit_items", ref=d["id"]), key=lambda x: x.get("position", 0))
        return Outfit.from_dict({**d, "items": items})

    def list_outfits(self, *, search=None, favorite=None, collection_id=None, occasion=None, limit=None, offset=0):
        q = sanitize_search(search).lower()
        rows = self._all("outfits")
        if collection_id:
            ids = {r["outfit_id"] for r in self._all("collection_outfits", ref=collection_id)}
            rows = [r for r in rows if r["id"] in ids]
        if favorite is not None:
            rows = [r for r in rows if bool(r.get("favorite")) == favorite]
        if occasion:
            rows = [r for r in rows if r.get("occasion") == occasion]
        if q:
            rows = [r for r in rows if q in " ".join(filter(None, [r.get("name"), r.get("notes"), r.get("occasion")])).lower()]
        rows.sort(key=lambda r: (r.get("updated_at") or "", r["id"]), reverse=True)
        total = len(rows)
        if limit is not None:
            rows = rows[offset: offset + limit]
        return [self._load_outfit(r) for r in rows], total

    def get_outfit(self, outfit_id):
        d = self._get("outfits", outfit_id)
        return self._load_outfit(d) if d else None

    def save_outfit(self, outfit):
        outfit._reorder()
        self._put("outfits", outfit.id, outfit.record())
        self._del("outfit_items", ref=outfit.id)
        for it in outfit.items:
            it.outfit_id = outfit.id
            self._put("outfit_items", it.id, it.to_dict(), ref=outfit.id)
        return self.get_outfit(outfit.id)  # type: ignore[return-value]

    def delete_outfit(self, outfit_id):
        if self._get("outfits", outfit_id) is None:
            raise NotFound("Outfit not found")
        self._del("outfit_items", ref=outfit_id)
        for r in self._all("collection_outfits"):
            if r["outfit_id"] == outfit_id:
                self._del("collection_outfits", r["id"])
        self._del("outfits", outfit_id)

    # ---------------------------------------------------------------- collections
    def list_collections(self):
        rows = sorted(self._all("outfit_collections"), key=lambda r: (r.get("name") or "").lower())
        return [Collection.from_dict(r) for r in rows]

    def save_collection(self, collection):
        if not collection.name.strip():
            raise ValueError("Collection name is required")
        collection.name = collection.name.strip()[:80]
        return Collection.from_dict(self._put("outfit_collections", collection.id, collection.to_dict()))

    def delete_collection(self, collection_id):
        self._del("collection_outfits", ref=collection_id)
        self._del("outfit_collections", collection_id)

    def add_to_collection(self, collection_id, outfit_id):
        if self._get("outfit_collections", collection_id) is None or self._get("outfits", outfit_id) is None:
            raise NotFound("Collection or outfit not found")
        row_id = f"{collection_id}:{outfit_id}"
        self._put("collection_outfits", row_id, {"collection_id": collection_id, "outfit_id": outfit_id}, ref=collection_id)

    def remove_from_collection(self, collection_id, outfit_id):
        self._del("collection_outfits", f"{collection_id}:{outfit_id}")

    def collections_for_outfit(self, outfit_id):
        return sorted(r["collection_id"] for r in self._all("collection_outfits") if r["outfit_id"] == outfit_id)

    # ---------------------------------------------------------------- history
    def add_history(self, kind, request, results):
        hid = new_id()
        self._put("recommendation_history", hid, {"id": hid, "kind": kind, "request": request, "results": results})
        rows = sorted(self._all("recommendation_history"), key=lambda r: r["created_at"], reverse=True)
        for old in rows[100:]:  # keep history bounded
            self._del("recommendation_history", old["id"])

    def list_history(self, limit=20):
        rows = sorted(self._all("recommendation_history"), key=lambda r: (r["created_at"], r["id"]), reverse=True)
        return rows[:limit]

    # ---------------------------------------------------------------- data management
    def delete_all_data(self):
        with self._lock, self._db:
            for t in _TABLES:
                self._db.execute(f"DELETE FROM {t} WHERE owner_id=?", (self.owner_id,))
        shutil.rmtree(self.root / "files" / self.owner_id, ignore_errors=True)

    def close(self) -> None:
        self._db.close()
