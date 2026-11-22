"""Browser checks in Vietnamese + the 'stay open' multi-choice behaviour.

Start the app in local mode with COLORMUSE_LANGUAGE=vi (see docs/TESTING.md), then:
    pytest tests/e2e/test_browser_vi.py --e2e-url=http://localhost:8599
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

SHOTS = Path(__file__).resolve().parents[1] / "_artifacts" / "screens"
EMAIL = os.environ.get("COLORMUSE_E2E_EMAIL", "zidi@example.com")
PASSWORD = os.environ.get("COLORMUSE_E2E_PASSWORD", "demo-pass")

PAGES = [
    ("home", "Trang chủ", "Bộ đồ gần đây"),
    ("matcher", "Phối màu", "Bảng màu hài hòa"),
    ("wardrobe", "Tủ đồ của tôi", "món đồ"),
    ("studio", "Xưởng phối đồ", "Trải phẳng"),
    ("occasions", "Dịp mặc", "Lên đồ theo dịp"),
    ("looks", "Bộ đồ đã lưu", "bộ đồ"),
    ("settings", "Cài đặt", "Hồ sơ phong cách"),
]
VIEWPORTS = {"desktop": {"width": 1366, "height": 900}, "mobile": {"width": 390, "height": 844}}


@pytest.fixture(scope="module")
def url(request):
    value = request.config.getoption("--e2e-url") or os.environ.get("COLORMUSE_E2E_VI_URL")
    if not value:
        pytest.skip("pass --e2e-url (app running with COLORMUSE_LANGUAGE=vi)")
    return value


@pytest.fixture(scope="module")
def browser(url):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _no_exception(page) -> None:
    errors = page.locator("[data-testid='stException']")
    assert errors.count() == 0, errors.first.inner_text()[:800]


def _login(page, url: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    try:
        page.get_by_role("textbox", name="Email").wait_for(timeout=90000)
    except Exception:
        page.screenshot(path=str(SHOTS / "vi-login-failure.png"))
        raise
    page.get_by_role("textbox", name="Email").fill(EMAIL)
    page.get_by_role("textbox", name="Mật khẩu").fill(PASSWORD)
    page.get_by_role("button", name="Đăng nhập").click()
    page.get_by_text("Xin chào").first.wait_for(timeout=30000)


def _open(page, title: str) -> None:
    top = page.locator("[data-testid='stTopNavLink']").filter(has_text=title)
    if top.count() and top.first.is_visible():
        top.first.click()
        return
    expand = page.locator("[data-testid='stExpandSidebarButton']")
    if expand.count() and expand.first.is_visible():
        expand.first.click()
        page.wait_for_timeout(500)
    page.locator("[data-testid='stSidebarNavLink']").filter(has_text=title).first.click()
    page.wait_for_timeout(400)
    close = page.locator("[data-testid='stSidebarCollapseButton'] button, [data-testid='stSidebarCollapseButton']")
    if close.count() and close.first.is_visible():
        close.first.click()


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
def test_all_pages_in_vietnamese(browser, url, viewport):
    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(viewport=VIEWPORTS[viewport])
    page = ctx.new_page()
    _login(page, url)
    for slug, title, marker in PAGES:
        _open(page, title)
        page.get_by_text(marker).first.wait_for(timeout=30000)
        page.wait_for_timeout(1200)
        _no_exception(page)
        page.screenshot(path=str(SHOTS / f"vi-{viewport}-{slug}.png"), full_page=True)
    ctx.close()


def test_studio_panel_stays_open_while_editing(browser, url):
    page = browser.new_page(viewport=VIEWPORTS["desktop"])
    _login(page, url)
    _open(page, "Xưởng phối đồ")
    page.get_by_text("Nền bộ đồ").first.wait_for(timeout=30000)
    panel = page.locator("[data-testid='stExpander']").filter(has_text="Áo —").first
    panel.locator("summary").click()
    page.wait_for_timeout(600)
    # pick a source, then change the shape: the panel must remain open after both reruns
    panel.get_by_text("Màu tùy chọn").click()
    page.wait_for_timeout(1500)
    assert panel.get_by_text("Kiểu dáng").first.is_visible(), "panel closed after choosing a source"
    panel.get_by_text("Thư viện màu").first.wait_for(timeout=10000)
    panel.locator("[data-testid='stSelectbox']").first.click()
    page.get_by_role("option").nth(1).click()
    page.wait_for_timeout(1500)
    assert panel.get_by_text("Kiểu dáng").first.is_visible(), "panel closed after changing the shape"
    _no_exception(page)
    page.screenshot(path=str(SHOTS / "vi-studio-panel-open.png"), full_page=True)
    page.close()


def test_multi_choice_chips_select_several_without_reopening(browser, url):
    page = browser.new_page(viewport=VIEWPORTS["desktop"])
    _login(page, url)
    _open(page, "Cài đặt")
    page.get_by_text("Phong cách ưa thích").first.wait_for(timeout=30000)
    group = page.locator("[data-testid='stButtonGroup']").filter(has_text="Lãng mạn").first
    for name in ("Lãng mạn", "Thanh lịch", "Tối giản"):
        group.get_by_role("button", name=name).click()
        page.wait_for_timeout(300)
    pressed = group.locator("button[aria-checked='true'], button[aria-pressed='true'], button[kind*='Active']")
    assert pressed.count() >= 3
    _no_exception(page)
    page.screenshot(path=str(SHOTS / "vi-settings-chips.png"), full_page=True)
    page.close()
