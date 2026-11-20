"""Repository contract shared by the Supabase (production) and local (dev) backends.

Pages and services only talk to this interface, so the whole UI works the same
on either backend and the contract test-suite runs against both.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from src.models.domain import ClothingImage, Collection, Outfit, UserPreferences, WardrobeItem

WARDROBE_SORTS: dict[str, str] = {
    "newest": "Newest first",
    "oldest": "Oldest first",
    "name": "Name A–Z",
    "category": "Category",
    "color": "Color (light → dark)",
    "favorites": "Favorites first",
}

PAGE_SIZE = 24


class BackendError(RuntimeError):
    """A database/storage operation failed."""


class BackendUnavailable(BackendError):
    """The cloud service can't be reached (offline, paused free-tier project, timeout)."""


class NotAuthorized(BackendError):
    """The session is missing/expired or the operation is not permitted."""


class NotFound(BackendError):
    """The record does not exist (or does not belong to the owner)."""


_SEARCH_STRIP = re.compile(r"[,()%*\\\"':;]")


def sanitize_search(text: str | None) -> str:
    """Remove characters that have meaning in PostgREST filter syntax."""
    if not text:
        return ""
    return _SEARCH_STRIP.sub(" ", text).strip()[:60]


class Repository(ABC):
    """All persistence for one owner. Every method is scoped to ``owner_id``."""

    owner_id: str
    backend_name: str = "abstract"

    # ---- preferences
    @abstractmethod
    def get_preferences(self) -> UserPreferences: ...

    @abstractmethod
    def save_preferences(self, prefs: UserPreferences) -> UserPreferences: ...

    # ---- wardrobe
    @abstractmethod
    def list_items(
        self,
        *,
        search: str | None = None,
        category: str | None = None,
        favorite: bool | None = None,
        season: str | None = None,
        sort: str = "newest",
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[WardrobeItem], int]: ...

    @abstractmethod
    def get_item(self, item_id: str) -> WardrobeItem | None: ...

    @abstractmethod
    def save_item(self, item: WardrobeItem) -> WardrobeItem: ...

    @abstractmethod
    def delete_item(self, item_id: str) -> None: ...

    def set_item_favorite(self, item_id: str, favorite: bool) -> None:
        item = self.get_item(item_id)
        if item is None:
            raise NotFound("Item not found")
        item.favorite = favorite
        self.save_item(item)

    # ---- images (files in storage, metadata in clothing_images)
    @abstractmethod
    def upload_item_image(self, item_id: str, full: bytes, thumb: bytes, width: int, height: int,
                          content_type: str = "image/jpeg") -> ClothingImage: ...

    @abstractmethod
    def list_item_images(self, item_id: str) -> list[ClothingImage]: ...

    @abstractmethod
    def delete_item_images(self, item_id: str) -> None: ...

    @abstractmethod
    def get_file(self, path: str) -> bytes | None: ...

    def signed_urls(self, paths: list[str]) -> dict[str, str]:
        """Short-lived URLs for private files; backends without URLs return {}."""
        return {}

    # ---- color library (read-only reference data)
    @abstractmethod
    def list_colors(self) -> list[dict[str, Any]]: ...

    # ---- outfits
    @abstractmethod
    def list_outfits(
        self,
        *,
        search: str | None = None,
        favorite: bool | None = None,
        collection_id: str | None = None,
        occasion: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[Outfit], int]: ...

    @abstractmethod
    def get_outfit(self, outfit_id: str) -> Outfit | None: ...

    @abstractmethod
    def save_outfit(self, outfit: Outfit) -> Outfit: ...

    @abstractmethod
    def delete_outfit(self, outfit_id: str) -> None: ...

    def set_outfit_favorite(self, outfit_id: str, favorite: bool) -> None:
        outfit = self.get_outfit(outfit_id)
        if outfit is None:
            raise NotFound("Outfit not found")
        outfit.favorite = favorite
        self.save_outfit(outfit)

    def duplicate_outfit(self, outfit_id: str) -> Outfit:
        outfit = self.get_outfit(outfit_id)
        if outfit is None:
            raise NotFound("Outfit not found")
        clone = outfit.copy(new_identity=True)
        clone.name = f"{outfit.name} (copy)"[:120]
        clone.favorite = False
        return self.save_outfit(clone)

    # ---- collections
    @abstractmethod
    def list_collections(self) -> list[Collection]: ...

    @abstractmethod
    def save_collection(self, collection: Collection) -> Collection: ...

    @abstractmethod
    def delete_collection(self, collection_id: str) -> None: ...

    @abstractmethod
    def add_to_collection(self, collection_id: str, outfit_id: str) -> None: ...

    @abstractmethod
    def remove_from_collection(self, collection_id: str, outfit_id: str) -> None: ...

    @abstractmethod
    def collections_for_outfit(self, outfit_id: str) -> list[str]: ...

    # ---- recommendation history
    @abstractmethod
    def add_history(self, kind: str, request: dict[str, Any], results: list[dict[str, Any]]) -> None: ...

    @abstractmethod
    def list_history(self, limit: int = 20) -> list[dict[str, Any]]: ...

    # ---- data management
    @abstractmethod
    def delete_all_data(self) -> None: ...

    def health_check(self) -> bool:
        """Cheap round-trip used to detect a paused/unreachable backend."""
        self.list_collections()
        return True


# ---------------------------------------------------------------- shared helpers

def item_matches(item: WardrobeItem, search: str, category: str | None, favorite: bool | None, season: str | None) -> bool:
    if category and item.category != category:
        return False
    if favorite is not None and item.favorite != favorite:
        return False
    if season and item.seasons and season not in item.seasons:
        return False
    if search:
        hay = " ".join(filter(None, [item.name, item.brand, item.notes, item.subcategory, item.primary_color_name])).lower()
        if search.lower() not in hay:
            return False
    return True


def sort_items(items: list[WardrobeItem], sort: str) -> list[WardrobeItem]:
    from src.core.color_convert import lightness

    if sort == "oldest":
        return sorted(items, key=lambda i: (i.created_at or "", i.id))
    if sort == "name":
        return sorted(items, key=lambda i: (i.name.lower(), i.id))
    if sort == "category":
        return sorted(items, key=lambda i: (i.category, i.name.lower(), i.id))
    if sort == "color":
        return sorted(items, key=lambda i: (-lightness(i.primary_color), i.id))
    if sort == "favorites":
        return sorted(items, key=lambda i: (not i.favorite, -_ts(i.created_at), i.id))
    return sorted(items, key=lambda i: (-_ts(i.created_at), i.id))


def _ts(value: str | None) -> float:
    from datetime import datetime

    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
