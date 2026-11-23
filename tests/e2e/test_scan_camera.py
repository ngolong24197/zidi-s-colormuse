"""Real-browser camera test: Chromium's fake camera shows a sage-green garment.

Start the app (local mode, COLORMUSE_LANGUAGE=vi) as in docs/TESTING.md, then:
    pytest tests/e2e/test_scan_camera.py --e2e-url=http://localhost:8599
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

pytestmark = pytest.mark.e2e

SHOTS = Path(__file__).resolve().parents[1] / "_artifacts" / "screens"
EMAIL = os.environ.get("COLORMUSE_E2E_EMAIL", "zidi@example.com")
PASSWORD = os.environ.get("COLORMUSE_E2E_PASSWORD", "demo-pass")


def _fake_camera_feed(path: Path) -> Path:
    """MJPEG file (concatenated JPEG frames) Chromium plays as the webcam."""
    buf = io.BytesIO()
    for _frame in range(30):
        img = Image.new("RGB", (640, 480), (232, 229, 224))
        ImageDraw.Draw(img).rectangle((170, 70, 470, 410), fill=(163, 177, 138))  # sage top, centred
        img.save(buf, "JPEG", quality=92)
    path.write_bytes(buf.getvalue())
    return path


@pytest.fixture(scope="module")
def url(request):
    value = request.config.getoption("--e2e-url") or os.environ.get("COLORMUSE_E2E_VI_URL")
    if not value:
        pytest.skip("pass --e2e-url (app running with COLORMUSE_LANGUAGE=vi)")
    return value


def test_scan_with_camera_then_add_to_wardrobe(url, tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    SHOTS.mkdir(parents=True, exist_ok=True)
    feed = _fake_camera_feed(tmp_path / "feed.mjpeg")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-video-capture={feed}",
        ])
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, permissions=["camera"])
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.get_by_role("textbox", name="Email").wait_for(timeout=90000)
        page.get_by_role("textbox", name="Email").fill(EMAIL)
        page.get_by_role("textbox", name="Mật khẩu").fill(PASSWORD)
        page.get_by_role("button", name="Đăng nhập").click()
        page.get_by_text("Xin chào").first.wait_for(timeout=30000)

        page.get_by_role("button", name="📷 Quét món đồ bằng camera").click()
        page.get_by_text("Bạn đang quét món gì?").first.wait_for(timeout=30000)
        shutter = page.locator("[data-testid='stCameraInputButton'], button:has-text('Take Photo')").first
        shutter.wait_for(timeout=30000)
        page.wait_for_timeout(2500)  # let the camera stream start
        shutter.click()

        page.get_by_text("Món đồ này màu").first.wait_for(timeout=60000)
        page.get_by_text("Phối cùng").first.wait_for(timeout=30000)
        body = page.locator("body").inner_text()
        assert "Xanh xô thơm" in body or "Xanh bạch đàn" in body or "Xanh hạt dẻ cười" in body, body[:600]
        page.screenshot(path=str(SHOTS / "scan-result.png"), full_page=True)

        page.get_by_text("Thêm món này vào tủ đồ?").first.wait_for(timeout=30000)
        page.get_by_role("button", name="✓ Lưu vào tủ đồ").click()
        page.get_by_text("Đã lưu vào tủ đồ ✓").first.wait_for(timeout=60000)
        assert page.locator("[data-testid='stException']").count() == 0
        page.screenshot(path=str(SHOTS / "scan-saved.png"), full_page=True)
        ctx.close()
        browser.close()


def test_companion_app_scan_and_sync(request, tmp_path):
    """The standalone phone companion: sign in → camera → colors → add to wardrobe → scan another."""
    url = request.config.getoption("--e2e-companion-url")
    if not url:
        pytest.skip("pass --e2e-companion-url (companion.py running with COLORMUSE_LANGUAGE=vi)")
    sync_api = pytest.importorskip("playwright.sync_api")
    SHOTS.mkdir(parents=True, exist_ok=True)
    feed = _fake_camera_feed(tmp_path / "feed.mjpeg")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-video-capture={feed}",
        ])
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, permissions=["camera"])
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.get_by_role("textbox", name="Email").wait_for(timeout=90000)
        page.get_by_text("Hướng camera, bấm chụp").first.wait_for(timeout=30000)
        page.get_by_role("textbox", name="Email").fill(EMAIL)
        page.get_by_role("textbox", name="Mật khẩu").fill(PASSWORD)
        page.get_by_role("button", name="Đăng nhập").click()
        page.get_by_text("Bạn đang quét món gì?").first.wait_for(timeout=60000)
        page.screenshot(path=str(SHOTS / "companion-start.png"), full_page=True)
        # tell it this is a pair of shoes
        chips = page.locator("[data-testid='stButtonGroup']").filter(has_text="Thắt lưng").first
        chips.locator("button").filter(has_text=re.compile(r"^\s*Giày\s*$")).first.click()
        page.wait_for_timeout(1000)
        shutter = page.locator("[data-testid='stCameraInputButton'], button:has-text('Take Photo')").first
        shutter.wait_for(timeout=30000)
        page.wait_for_timeout(2500)
        shutter.click()
        page.get_by_text("Món đồ này màu").first.wait_for(timeout=60000)
        body = page.locator("body").inner_text()
        assert "Phối cùng" in body and "Giày" in body
        # no links into the full app from the companion
        assert page.get_by_role("button", name="👗 Phối bộ đồ với món này").count() == 0
        page.get_by_text("Thêm món này vào tủ đồ?").first.wait_for(timeout=30000)
        name_box = page.get_by_role("textbox", name="Tên")
        name_box.fill("Sage ballet flats")
        name_box.press("Tab")
        page.wait_for_timeout(800)
        page.get_by_role("button", name="✓ Lưu vào tủ đồ").click()
        page.get_by_text("Đã lưu vào tủ đồ ✓").first.wait_for(timeout=60000)
        page.screenshot(path=str(SHOTS / "companion-saved.png"), full_page=True)
        page.get_by_role("button", name="📷 Quét món khác").click()
        page.wait_for_timeout(1500)
        assert page.get_by_text("Thêm món này vào tủ đồ?").count() == 0  # camera reset for the next piece
        assert page.locator("[data-testid='stException']").count() == 0
        ctx.close()
        browser.close()

    # synced: the piece is in the shared wardrobe the main app reads
    from src.database.local_repo import LocalRepository

    demo = Path(__file__).resolve().parents[1] / "_artifacts" / "demo_vi"
    items, _total = LocalRepository(demo, "local-owner").list_items(search="Sage ballet flats")
    assert items and items[0].category == "shoes" and items[0].thumb_path
