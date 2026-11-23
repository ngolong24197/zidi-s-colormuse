from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.database.local_repo import LocalRepository  # noqa: E402
from src.database.supabase_repo import SupabaseRepository  # noqa: E402
from tests.fakes import FakeClient, FakeDB, FakeUser, seeded_colors  # noqa: E402


def pytest_addoption(parser):
    parser.addoption("--e2e-url", default=None, help="URL of a running ColorMuse (local mode) for browser tests")
    parser.addoption("--e2e-companion-url", default=None, help="URL of a running companion.py (local mode, vi)")


@pytest.fixture(autouse=True)
def _isolate_from_real_config(monkeypatch):
    """Never let the developer's real .env (e.g. Supabase keys) influence tests."""
    monkeypatch.setenv("COLORMUSE_DOTENV", "none")
    monkeypatch.delenv("COLORMUSE_LANGUAGE", raising=False)
    from src import i18n

    i18n.set_language("en")


@pytest.fixture
def fake_db():
    db = FakeDB()
    seeded_colors(db)
    return db


def make_supabase_repo(db: FakeDB, email: str = "owner@example.com") -> SupabaseRepository:
    uid = db.add_user(email, "secret-password")
    client = FakeClient(db, FakeUser(uid, email))
    return SupabaseRepository(client, uid, "wardrobe", sleep=lambda s: None)


@pytest.fixture(params=["local", "supabase"])
def repo(request, tmp_path, fake_db):
    if request.param == "local":
        r = LocalRepository(tmp_path / "local", "owner-1")
        yield r
        r.close()
    else:
        yield make_supabase_repo(fake_db)


def jpeg_bytes(size=(600, 800), bg=(240, 240, 238), garment=(113, 62, 74), stripes=None, fmt="JPEG") -> bytes:
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    w, h = size
    d.rectangle((w * 0.25, h * 0.2, w * 0.75, h * 0.8), fill=garment)
    if stripes:
        for y in range(int(h * 0.22), int(h * 0.8), 60):
            d.rectangle((w * 0.25, y, w * 0.75, y + 15), fill=stripes)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def photo() -> bytes:
    return jpeg_bytes()
