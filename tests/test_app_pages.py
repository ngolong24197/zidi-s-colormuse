"""Streamlit AppTest: sign-in gating and every page running in local mode."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]

PAGES = ["pages/home.py", "pages/color_matcher.py", "pages/wardrobe.py", "pages/outfit_studio.py",
         "pages/occasion_planner.py", "pages/saved_looks.py", "pages/settings.py"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    from scripts.seed_demo_wardrobe import seed

    seed(tmp_path)
    monkeypatch.setenv("COLORMUSE_BACKEND", "local")
    monkeypatch.setenv("COLORMUSE_LOCAL_PASSWORD", "demo-pass-123")
    monkeypatch.setenv("OWNER_EMAIL", "zidi@example.com")
    monkeypatch.setenv("COLORMUSE_LOCAL_DIR", str(tmp_path))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.chdir(ROOT)
    return tmp_path


def _signed_in(env) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    at.text_input[0].input("zidi@example.com")
    at.text_input[1].input("demo-pass-123")
    at.button[0].click()
    at.run()
    assert not at.exception, at.exception
    return at


def test_login_required_and_wrong_password(env):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert any("Sign in" in b.label for b in at.button)
    at.text_input[0].input("zidi@example.com")
    at.text_input[1].input("nope")
    at.button[0].click()
    at.run()
    assert any("Incorrect" in e.value for e in at.error)


def test_setup_page_when_unconfigured(monkeypatch, tmp_path):
    for k in ("COLORMUSE_BACKEND", "SUPABASE_URL", "SUPABASE_ANON_KEY", "OWNER_EMAIL", "COLORMUSE_LOCAL_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("COLORMUSE_BACKEND", "supabase")
    monkeypatch.chdir(tmp_path)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert any("SUPABASE_URL" in e.value for e in at.error)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_runs(env, page):
    at = _signed_in(env)
    at.switch_page(page)
    at.run()
    assert not at.exception, at.exception


@pytest.mark.parametrize("page", PAGES)
def test_every_page_runs_in_vietnamese(env, page, monkeypatch):
    monkeypatch.setenv("COLORMUSE_LANGUAGE", "vi")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert any(b.label == "Đăng nhập" for b in at.button)
    at.text_input[0].input("zidi@example.com")
    at.text_input[1].input("demo-pass-123")
    next(b for b in at.button if b.label == "Đăng nhập").click()
    at.run()
    assert not at.exception, at.exception
    at.switch_page(page)
    at.run()
    assert not at.exception, at.exception
    texts = " ".join(m.value for m in at.markdown)
    assert "ColorMuse" in texts


def test_planner_save_and_saved_looks(env):
    at = _signed_in(env)
    at.switch_page("pages/occasion_planner.py")
    at.run()
    save = next(b for b in at.button if b.label == "Save look")
    save.click()
    at.run()
    assert not at.exception
    from src.database.local_repo import LocalRepository

    assert LocalRepository(env, "local-owner").list_outfits()[1] == 4  # 3 seeded + 1 saved


def test_studio_save_persists(env):
    at = _signed_in(env)
    at.switch_page("pages/outfit_studio.py")
    at.run()
    # choose a top from the wardrobe and save
    radios = [r for r in at.radio if r.options == ["None", "From wardrobe", "Custom color"]]
    radios[0].set_value("From wardrobe")
    at.run()
    assert not at.exception
    save = next(b for b in at.button if "Save" in b.label and "new" not in b.label)
    save.click()
    at.run()
    assert not at.exception
    from src.database.local_repo import LocalRepository

    assert LocalRepository(env, "local-owner").list_outfits(search="New look")[1] == 1


def test_wardrobe_add_item_manually(env):
    at = _signed_in(env)
    at.switch_page("pages/wardrobe.py")
    at.run()
    next(b for b in at.button if "Add a piece" in b.label).click()
    at.run()
    name = next(t for t in at.text_input if t.label == "Name")
    name.input("Emerald satin skirt")
    at.run()
    next(b for b in at.button if b.label == "Save piece").click()
    at.run()
    assert not at.exception
    from src.database.local_repo import LocalRepository

    items, _ = LocalRepository(env, "local-owner").list_items(search="Emerald satin")
    assert len(items) == 1 and items[0].category == "tops"


def test_settings_save_preferences(env):
    at = _signed_in(env)
    at.switch_page("pages/settings.py")
    at.run()
    name = next(t for t in at.text_input if t.label == "What should I call you?")
    name.input("Muse")
    next(b for b in at.button if b.label == "Save style profile").click()
    at.run()
    assert not at.exception
    from src.database.local_repo import LocalRepository

    assert LocalRepository(env, "local-owner").get_preferences().display_name == "Muse"

