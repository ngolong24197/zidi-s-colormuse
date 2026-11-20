"""Per-browser-session state: signed-in owner, repository, caches, current outfit.

Caching rules (Streamlit Community Cloud has ~1 GB RAM):
* Repository reads are memoised per session in a small dict that is cleared
  on every write (``invalidate``), so pages don't re-query on each rerun.
* Image bytes and signed URLs use bounded LRU caches.
* Nothing user-specific goes into global ``st.cache_*`` except pure functions
  of their (hashable) arguments, e.g. rendering a garment template.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable

import streamlit as st

from src.config import Settings, load_settings
from src.database.base import Repository
from src.models.domain import Outfit, UserPreferences, WardrobeItem
from src.services.auth import Session

_CACHE_KEY = "_cm_cache"
_BYTES_KEY = "_cm_bytes"
_URLS_KEY = "_cm_urls"
MAX_BYTES_ENTRIES = 48
URL_TTL = 50 * 60


def settings() -> Settings:
    if "_cm_settings" not in st.session_state:
        st.session_state["_cm_settings"] = load_settings()
    return st.session_state["_cm_settings"]


def current() -> Session | None:
    return st.session_state.get("cm_session")


def set_session(sess: Session | None) -> None:
    st.session_state["cm_session"] = sess
    for k in (_CACHE_KEY, _BYTES_KEY, _URLS_KEY, "studio_outfit"):
        st.session_state.pop(k, None)


def repo() -> Repository:
    sess = current()
    if sess is None:
        raise RuntimeError("Not signed in")
    return sess.repo


# ---------------------------------------------------------------- memoised reads
def cached(key: str, loader: Callable[[], Any]) -> Any:
    cache: dict[str, Any] = st.session_state.setdefault(_CACHE_KEY, {})
    if key not in cache:
        cache[key] = loader()
    return cache[key]


def invalidate() -> None:
    st.session_state[_CACHE_KEY] = {}


def preferences() -> UserPreferences:
    return cached("prefs", lambda: repo().get_preferences())


def all_items() -> list[WardrobeItem]:
    """Whole wardrobe (used by matcher/planner/studio). Personal wardrobes are small."""
    return cached("items:all", lambda: repo().list_items(sort="newest")[0])


def items_by_id() -> dict[str, WardrobeItem]:
    return {i.id: i for i in all_items()}


def collections():
    return cached("collections", lambda: repo().list_collections())


# ---------------------------------------------------------------- images
def file_bytes(path: str | None) -> bytes | None:
    if not path:
        return None
    lru: OrderedDict[str, bytes | None] = st.session_state.setdefault(_BYTES_KEY, OrderedDict())
    if path in lru:
        lru.move_to_end(path)
        return lru[path]
    data = repo().get_file(path)
    lru[path] = data
    while len(lru) > MAX_BYTES_ENTRIES:
        lru.popitem(last=False)
    return data


def image_sources(paths: list[str]) -> dict[str, Any]:
    """URL (Supabase signed URL) or bytes (local backend) for each path."""
    urls: dict[str, tuple[str, float]] = st.session_state.setdefault(_URLS_KEY, {})
    now = time.time()
    missing = [p for p in paths if p and (p not in urls or now - urls[p][1] > URL_TTL)]
    if missing:
        fresh = repo().signed_urls(missing)
        for p, u in fresh.items():
            urls[p] = (u, now)
    if len(urls) > 500:
        for p in sorted(urls, key=lambda k: urls[k][1])[:250]:
            urls.pop(p, None)
    out: dict[str, Any] = {}
    for p in paths:
        if not p:
            continue
        if p in urls:
            out[p] = urls[p][0]
        else:
            data = file_bytes(p)
            if data:
                out[p] = data
    return out


def photo_loader(item_id: str) -> bytes | None:
    """For the flat-lay: medium-size photo bytes of a wardrobe item."""
    item = items_by_id().get(item_id)
    if not item:
        return None
    return file_bytes(item.image_path or item.thumb_path)


# ---------------------------------------------------------------- studio outfit (shared by both visualizers)
def studio_outfit() -> Outfit:
    if "studio_outfit" not in st.session_state:
        prefs = preferences()
        st.session_state["studio_outfit"] = Outfit(
            name="New look", skin_tone=prefs.skin_tone, hair_color=prefs.hair_color, hair_style=prefs.hair_style)
    return st.session_state["studio_outfit"]


def open_in_studio(outfit: Outfit) -> None:
    st.session_state["studio_outfit"] = outfit
    st.session_state["studio_rev"] = st.session_state.get("studio_rev", 0) + 1
