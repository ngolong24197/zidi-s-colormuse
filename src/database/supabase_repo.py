"""Supabase backend: PostgreSQL via PostgREST + private Storage bucket.

Security model
--------------
* The client is created with the **anon/publishable key** and the owner's
  user session (JWT). Every query therefore runs as the ``authenticated``
  role and Row Level Security restricts it to rows where
  ``owner_id = auth.uid()`` (see database/schema.sql).
* We *also* filter by ``owner_id`` explicitly (defence in depth).
* Storage objects live under ``<user-id>/...`` and storage policies only
  allow access to the user's own folder.
* The service-role key is never used by the app.

Resilience
----------
Transient failures (network errors, timeouts, 5xx, a paused free project)
are retried with backoff and surfaced as ``BackendUnavailable``. An expired
JWT triggers one session refresh before failing with ``NotAuthorized``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

from src.database.base import (
    BackendError,
    BackendUnavailable,
    NotAuthorized,
    NotFound,
    Repository,
    sanitize_search,
    sort_items,
)
from src.models.domain import (
    ClothingImage,
    Collection,
    Outfit,
    UserPreferences,
    WardrobeItem,
    new_id,
    utcnow,
)

T = TypeVar("T")

RETRY_DELAYS = (0.4, 1.2)
SIGNED_URL_TTL = 3600

_ITEM_COLS = (
    "id,owner_id,name,category,subcategory,primary_color,primary_color_name,secondary_colors,shade,"
    "pattern,brand,seasons,styles,occasions,notes,favorite,image_path,thumb_path,created_at,updated_at"
)


def _is_transient(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in {"ConnectError", "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout",
                "RemoteProtocolError", "ReadError", "TimeoutException", "NetworkError"}:
        return True
    status = _status_of(exc)
    return status is not None and (status >= 500 or status in (408, 429))


def _status_of(exc: Exception) -> int | None:
    for attr in ("status", "status_code", "code"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    resp = getattr(exc, "response", None)
    if resp is not None and isinstance(getattr(resp, "status_code", None), int):
        return resp.status_code
    return None


def _is_auth_error(exc: Exception) -> bool:
    code = str(getattr(exc, "code", "") or "")
    msg = str(exc).lower()
    return code in {"PGRST301", "PGRST302", "401", "403"} or "jwt expired" in msg or "invalid jwt" in msg or _status_of(exc) in (401, 403)


class SupabaseRepository(Repository):
    backend_name = "supabase"

    def __init__(self, client: Any, owner_id: str, bucket: str = "wardrobe",
                 on_reconnect: Callable[[], Any] | None = None, sleep: Callable[[float], None] = time.sleep) -> None:
        self.client = client
        self.owner_id = owner_id
        self.bucket = bucket
        self._on_reconnect = on_reconnect
        self._sleep = sleep

    # ---------------------------------------------------------------- plumbing
    def _call(self, fn: Callable[[], T]) -> T:
        refreshed = False
        attempt = 0
        while True:
            try:
                return fn()
            except BackendError:
                raise
            except Exception as exc:  # noqa: BLE001 - classify and re-raise as domain errors
                if _is_auth_error(exc):
                    if not refreshed:
                        refreshed = True
                        try:
                            self.client.auth.refresh_session()
                            continue
                        except Exception:  # noqa: BLE001
                            pass
                    raise NotAuthorized("Your session has expired. Please sign in again.") from exc
                if _is_transient(exc) and attempt < len(RETRY_DELAYS):
                    self._sleep(RETRY_DELAYS[attempt])
                    attempt += 1
                    if self._on_reconnect is not None:
                        new_client = self._on_reconnect()
                        if new_client is not None:
                            self.client = new_client
                    continue
                if _is_transient(exc):
                    raise BackendUnavailable(
                        "ColorMuse can't reach its cloud database right now. If the Supabase project was "
                        "paused for inactivity, restore it from the Supabase dashboard, then retry."
                    ) from exc
                raise BackendError(f"Database error: {exc}") from exc

    def _t(self, name: str):
        return self.client.table(name)

    def _store(self):
        return self.client.storage.from_(self.bucket)

    @staticmethod
    def _data(resp: Any) -> list[dict[str, Any]]:
        return list(getattr(resp, "data", None) or [])

    # ---------------------------------------------------------------- preferences
    def get_preferences(self) -> UserPreferences:
        rows = self._call(lambda: self._data(
            self._t("user_preferences").select("*").eq("owner_id", self.owner_id).limit(1).execute()))
        return UserPreferences.from_dict(rows[0] if rows else None)

    def save_preferences(self, prefs: UserPreferences) -> UserPreferences:
        row = {**prefs.to_dict(), "owner_id": self.owner_id, "updated_at": utcnow()}
        rows = self._call(lambda: self._data(
            self._t("user_preferences").upsert(row, on_conflict="owner_id").execute()))
        return UserPreferences.from_dict(rows[0] if rows else row)

    # ---------------------------------------------------------------- wardrobe
    def list_items(self, *, search=None, category=None, favorite=None, season=None, sort="newest",
                   limit=None, offset=0):
        def run():
            q = self._t("wardrobe_items").select(_ITEM_COLS, count="exact").eq("owner_id", self.owner_id)
            if category:
                q = q.eq("category", category)
            if favorite is not None:
                q = q.eq("favorite", favorite)
            if season:
                # items with no seasons are treated as all-season
                q = q.or_(f"seasons.cs.{{{season}}},seasons.eq.{{}}")
            s = sanitize_search(search)
            if s:
                q = q.or_(f"name.ilike.*{s}*,brand.ilike.*{s}*,notes.ilike.*{s}*,subcategory.ilike.*{s}*,primary_color_name.ilike.*{s}*")
            server_sort = sort != "color"
            if server_sort:
                if sort == "oldest":
                    q = q.order("created_at", desc=False)
                elif sort == "name":
                    q = q.order("name", desc=False)
                elif sort == "category":
                    q = q.order("category", desc=False).order("name", desc=False)
                elif sort == "favorites":
                    q = q.order("favorite", desc=True).order("created_at", desc=True)
                else:
                    q = q.order("created_at", desc=True)
                q = q.order("id", desc=False)
                if limit is not None:
                    q = q.range(offset, offset + limit - 1)
            return q.execute()

        resp = self._call(run)
        items = [WardrobeItem.from_dict(r) for r in self._data(resp)]
        total = getattr(resp, "count", None)
        if sort == "color":  # needs perceptual lightness: sort client-side (wardrobes are small)
            items = sort_items(items, "color")
            total = len(items)
            if limit is not None:
                items = items[offset: offset + limit]
        return items, int(total if total is not None else len(items))

    def get_item(self, item_id):
        rows = self._call(lambda: self._data(
            self._t("wardrobe_items").select(_ITEM_COLS).eq("owner_id", self.owner_id).eq("id", item_id).limit(1).execute()))
        return WardrobeItem.from_dict(rows[0]) if rows else None

    def save_item(self, item):
        item.validate()
        row = item.to_dict()
        row.update(owner_id=self.owner_id, updated_at=utcnow())
        if not row.get("created_at"):
            row.pop("created_at")
        rows = self._call(lambda: self._data(self._t("wardrobe_items").upsert(row, on_conflict="id").execute()))
        return WardrobeItem.from_dict(rows[0] if rows else row)

    def delete_item(self, item_id):
        if self.get_item(item_id) is None:
            raise NotFound("Item not found")
        self.delete_item_images(item_id)
        # outfit_items.wardrobe_item_id is ON DELETE SET NULL in the schema
        self._call(lambda: self._t("wardrobe_items").delete().eq("owner_id", self.owner_id).eq("id", item_id).execute())

    # ---------------------------------------------------------------- images
    def upload_item_image(self, item_id, full, thumb, width, height, content_type="image/jpeg"):
        item = self.get_item(item_id)
        if item is None:
            raise NotFound("Item not found")
        image_id = new_id()
        full_path = f"{self.owner_id}/items/{item_id}/{image_id}.jpg"
        thumb_path = f"{self.owner_id}/thumbs/{item_id}/{image_id}.jpg"
        opts = {"content-type": content_type, "cache-control": "3600", "upsert": "false"}
        self._call(lambda: self._store().upload(full_path, full, opts))
        try:
            self._call(lambda: self._store().upload(thumb_path, thumb, opts))
            old = self.list_item_images(item_id)
            img = ClothingImage(item_id, full_path, thumb_path, id=image_id, width=width, height=height,
                                size_bytes=len(full), content_type=content_type, owner_id=self.owner_id)
            row = img.to_dict()
            row.pop("created_at")
            self._call(lambda: self._t("clothing_images").insert(row).execute())
            item.image_path, item.thumb_path = full_path, thumb_path
            self.save_item(item)
        except Exception:
            # don't leave orphaned files behind if the metadata write failed
            try:
                self._store().remove([full_path, thumb_path])
            except Exception:  # noqa: BLE001
                pass
            raise
        # replace previous photos only after the new one is safely stored
        for o in old:
            self._remove_image(o)
        return img

    def _remove_image(self, img: ClothingImage) -> None:
        self._call(lambda: self._store().remove([img.storage_path, img.thumb_path]))
        self._call(lambda: self._t("clothing_images").delete().eq("owner_id", self.owner_id).eq("id", img.id).execute())

    def list_item_images(self, item_id):
        rows = self._call(lambda: self._data(
            self._t("clothing_images").select("*").eq("owner_id", self.owner_id).eq("wardrobe_item_id", item_id).execute()))
        return [ClothingImage.from_dict(r) for r in rows]

    def delete_item_images(self, item_id):
        for img in self.list_item_images(item_id):
            self._remove_image(img)
        item = self.get_item(item_id)
        if item and (item.image_path or item.thumb_path):
            item.image_path = item.thumb_path = None
            self.save_item(item)

    def get_file(self, path):
        if not path or not path.startswith(self.owner_id + "/"):
            return None
        try:
            return self._call(lambda: self._store().download(path))
        except BackendUnavailable:
            raise
        except BackendError:
            return None

    def signed_urls(self, paths):
        paths = [p for p in paths if p and p.startswith(self.owner_id + "/")]
        if not paths:
            return {}
        res = self._call(lambda: self._store().create_signed_urls(paths, SIGNED_URL_TTL))
        out = {}
        for entry in res or []:
            url = entry.get("signedURL") or entry.get("signedUrl")
            if url and entry.get("path"):
                out[entry["path"]] = url
        return out

    # ---------------------------------------------------------------- colors
    def list_colors(self):
        return self._call(lambda: self._data(self._t("colors").select("name,hex,family,is_neutral").order("name").execute()))

    # ---------------------------------------------------------------- outfits
    def _attach_items(self, rows: list[dict[str, Any]]) -> list[Outfit]:
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        items = self._call(lambda: self._data(
            self._t("outfit_items").select("*").eq("owner_id", self.owner_id).in_("outfit_id", ids).order("position").execute()))
        by_outfit: dict[str, list[dict[str, Any]]] = {}
        for it in items:
            by_outfit.setdefault(it["outfit_id"], []).append(it)
        return [Outfit.from_dict({**r, "items": by_outfit.get(r["id"], [])}) for r in rows]

    def list_outfits(self, *, search=None, favorite=None, collection_id=None, occasion=None, limit=None, offset=0):
        def run():
            q = self._t("outfits").select("*", count="exact").eq("owner_id", self.owner_id)
            if collection_id:
                links = self._data(self._t("collection_outfits").select("outfit_id")
                                   .eq("owner_id", self.owner_id).eq("collection_id", collection_id).execute())
                ids = [link["outfit_id"] for link in links] or ["00000000-0000-0000-0000-000000000000"]
                q = q.in_("id", ids)
            if favorite is not None:
                q = q.eq("favorite", favorite)
            if occasion:
                q = q.eq("occasion", occasion)
            s = sanitize_search(search)
            if s:
                q = q.or_(f"name.ilike.*{s}*,notes.ilike.*{s}*,occasion.ilike.*{s}*")
            q = q.order("updated_at", desc=True).order("id", desc=True)
            if limit is not None:
                q = q.range(offset, offset + limit - 1)
            return q.execute()

        resp = self._call(run)
        rows = self._data(resp)
        total = getattr(resp, "count", None)
        return self._attach_items(rows), int(total if total is not None else len(rows))

    def get_outfit(self, outfit_id):
        rows = self._call(lambda: self._data(
            self._t("outfits").select("*").eq("owner_id", self.owner_id).eq("id", outfit_id).limit(1).execute()))
        out = self._attach_items(rows)
        return out[0] if out else None

    def save_outfit(self, outfit):
        outfit._reorder()
        row = outfit.record()
        row.update(owner_id=self.owner_id, updated_at=utcnow())
        if not row.get("created_at"):
            row.pop("created_at")
        self._call(lambda: self._t("outfits").upsert(row, on_conflict="id").execute())
        self._call(lambda: self._t("outfit_items").delete().eq("owner_id", self.owner_id).eq("outfit_id", outfit.id).execute())
        if outfit.items:
            item_rows = []
            for it in outfit.items:
                d = it.to_dict()
                d.update(outfit_id=outfit.id, owner_id=self.owner_id)
                item_rows.append(d)
            self._call(lambda: self._t("outfit_items").insert(item_rows).execute())
        return self.get_outfit(outfit.id)

    def delete_outfit(self, outfit_id):
        if self.get_outfit(outfit_id) is None:
            raise NotFound("Outfit not found")
        # outfit_items and collection_outfits cascade on delete
        self._call(lambda: self._t("outfits").delete().eq("owner_id", self.owner_id).eq("id", outfit_id).execute())

    # ---------------------------------------------------------------- collections
    def list_collections(self):
        rows = self._call(lambda: self._data(
            self._t("outfit_collections").select("*").eq("owner_id", self.owner_id).order("name").execute()))
        return [Collection.from_dict(r) for r in rows]

    def save_collection(self, collection):
        if not collection.name.strip():
            raise ValueError("Collection name is required")
        collection.name = collection.name.strip()[:80]
        row = collection.to_dict()
        row["owner_id"] = self.owner_id
        if not row.get("created_at"):
            row.pop("created_at")
        rows = self._call(lambda: self._data(self._t("outfit_collections").upsert(row, on_conflict="id").execute()))
        return Collection.from_dict(rows[0] if rows else row)

    def delete_collection(self, collection_id):
        self._call(lambda: self._t("outfit_collections").delete().eq("owner_id", self.owner_id).eq("id", collection_id).execute())

    def add_to_collection(self, collection_id, outfit_id):
        row = {"collection_id": collection_id, "outfit_id": outfit_id, "owner_id": self.owner_id}
        self._call(lambda: self._t("collection_outfits").upsert(row, on_conflict="collection_id,outfit_id").execute())

    def remove_from_collection(self, collection_id, outfit_id):
        self._call(lambda: self._t("collection_outfits").delete().eq("owner_id", self.owner_id)
                   .eq("collection_id", collection_id).eq("outfit_id", outfit_id).execute())

    def collections_for_outfit(self, outfit_id):
        rows = self._call(lambda: self._data(self._t("collection_outfits").select("collection_id")
                                             .eq("owner_id", self.owner_id).eq("outfit_id", outfit_id).execute()))
        return sorted(r["collection_id"] for r in rows)

    # ---------------------------------------------------------------- history
    def add_history(self, kind, request, results):
        row = {"id": new_id(), "owner_id": self.owner_id, "kind": kind, "request": request, "results": results}
        self._call(lambda: self._t("recommendation_history").insert(row).execute())

    def list_history(self, limit=20):
        return self._call(lambda: self._data(
            self._t("recommendation_history").select("*").eq("owner_id", self.owner_id)
            .order("created_at", desc=True).limit(limit).execute()))

    # ---------------------------------------------------------------- data management
    def _list_storage_paths(self, prefix: str) -> list[str]:
        out: list[str] = []
        entries = self._call(lambda: self._store().list(prefix, {"limit": 1000})) or []
        for e in entries:
            name = e.get("name")
            if not name:
                continue
            full = f"{prefix}/{name}"
            if e.get("id") is None:  # folder
                out.extend(self._list_storage_paths(full))
            else:
                out.append(full)
        return out

    def delete_all_data(self):
        paths = self._list_storage_paths(self.owner_id)
        for i in range(0, len(paths), 100):
            chunk = paths[i:i + 100]
            self._call(lambda: self._store().remove(chunk))
        # children first (cascades would handle most, but be explicit)
        for table in ("collection_outfits", "outfit_items", "outfit_collections", "outfits",
                      "clothing_images", "wardrobe_items", "recommendation_history", "user_preferences"):
            self._call(lambda t=table: self._t(t).delete().eq("owner_id", self.owner_id).execute())
