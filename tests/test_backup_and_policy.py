"""Backup/restore round-trip and the 'no AI in the initial release' policy."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from src.database.local_repo import LocalRepository
from src.models.domain import Collection, Outfit, OutfitItem, UserPreferences, WardrobeItem
from src.services.backup import export_data, export_zip, import_zip
from src.services.image_processing import process_upload
from tests.conftest import make_supabase_repo

ROOT = Path(__file__).resolve().parents[1]


def _populate(repo, photo):
    repo.save_preferences(UserPreferences(display_name="Zidi", hair_style="bob"))
    top = repo.save_item(WardrobeItem(name="Blouse", category="tops", primary_color="#E8C9C5"))
    p = process_upload(photo, "b.jpg")
    repo.upload_item_image(top.id, p.full, p.thumb, p.width, p.height)
    o = Outfit(name="Brunch")
    o.set_item(OutfitItem.from_wardrobe(top))
    o.set_item(OutfitItem(slot="nails", color_hex="#B3112E", variant="round"))
    repo.save_outfit(o)
    c = repo.save_collection(Collection(name="Weekend"))
    repo.add_to_collection(c.id, o.id)
    return top, o


def test_export_contains_everything(tmp_path, photo):
    repo = LocalRepository(tmp_path, "owner")
    _populate(repo, photo)
    data = export_data(repo)
    assert data["format"] == "colormuse-backup" and data["preferences"]["display_name"] == "Zidi"
    assert len(data["wardrobe_items"]) == 1 and len(data["outfits"]) == 1
    assert data["collections"][0]["outfit_ids"] == [data["outfits"][0]["id"]]
    zf = zipfile.ZipFile(io.BytesIO(export_zip(repo)))
    names = zf.namelist()
    assert "colormuse.json" in names and any(n.endswith("full.jpg") for n in names)


def test_restore_into_a_different_backend(tmp_path, photo, fake_db):
    src = LocalRepository(tmp_path, "owner")
    _populate(src, photo)
    blob = export_zip(src)
    dst = make_supabase_repo(fake_db)
    counts = import_zip(dst, blob)
    assert counts == {"items": 1, "photos": 1, "outfits": 1, "collections": 1}
    items, _ = dst.list_items()
    assert items[0].name == "Blouse" and dst.get_file(items[0].thumb_path)
    looks, _ = dst.list_outfits()
    assert looks[0].get("top").wardrobe_item_id == items[0].id  # links remapped to new IDs
    assert looks[0].get("nails").variant == "round"
    col = dst.list_collections()[0]
    assert dst.list_outfits(collection_id=col.id)[1] == 1
    assert dst.get_preferences().hair_style == "bob"


def test_restore_rejects_foreign_files(tmp_path):
    repo = LocalRepository(tmp_path, "owner")
    with pytest.raises(ValueError):
        import_zip(repo, b"not a zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("colormuse.json", json.dumps({"format": "something-else"}))
    with pytest.raises(ValueError):
        import_zip(repo, buf.getvalue())


# ---------------------------------------------------------------- AI policy
AI_PACKAGES = re.compile(r"^(openai|anthropic|google-generativeai|google-genai|langchain|transformers|torch|"
                         r"tensorflow|cohere|mistralai|ollama|replicate|huggingface)", re.I | re.M)


def test_no_ai_dependencies():
    for req in ("requirements.txt", "requirements-dev.txt"):
        assert not AI_PACKAGES.search((ROOT / req).read_text()), req


def test_no_ai_imports_or_api_calls_in_app_code():
    pattern = re.compile(r"^\s*(import|from)\s+(openai|anthropic|langchain|transformers|torch|google\.generativeai|cohere)\b"
                         r"|api\.openai\.com|api\.anthropic\.com", re.M)
    files = list((ROOT / "src").rglob("*.py")) + list((ROOT / "pages").glob("*.py")) + [ROOT / "app.py"]
    offenders = [str(f) for f in files if pattern.search(f.read_text(encoding="utf-8"))]
    assert offenders == []


def test_no_secrets_committed():
    assert not (ROOT / ".env").exists() or ".env" in (ROOT / ".gitignore").read_text()
    assert "secrets.toml" in (ROOT / ".gitignore").read_text()
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in ROOT.rglob("*.py")
                     if ".venv" not in p.parts and "_artifacts" not in p.parts)
    assert not re.search(r"eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}", text)
