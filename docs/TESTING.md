# Testing

```bash
pip install -r requirements-dev.txt
pytest                      # everything except browser tests
```

| Suite | What it covers |
|---|---|
| `test_color_engine.py` | hex parsing, RGB/HSL/HSV/Lab round-trips, Lab vs scikit-image, CIEDE2000 vs Sharma reference data and scikit-image, contrast ratio, library, harmony angles, palettes, relation classification, every scoring component, configurable weights, pattern clash, recommendation ranking/diversity/determinism, shade filter, preferences, wardrobe matching |
| `test_outfits_and_beauty.py` | domain validation, dress ↔ separates, copy/serialise, preferences normalisation, outfit scoring, occasion suitability, generator (owned-only, deterministic, practical picks, seasons, diversity), nails, hairstyles, hair-color harmony, matcher → outfit |
| `test_images_and_visualizer.py` | upload validation (empty, oversized, wrong type, fake, truncated, tiny, GIF), PNG alpha, WEBP, resize/compress/EXIF strip, EXIF rotation, cropping, dominant + secondary color extraction with background, determinism, SVG path parser, template coverage, mannequin SVG validity/layers/escaping/recolor, all hairstyles, patterns, flat-lay layouts (in-bounds, non-overlapping), photo use + fallback, PNG exports |
| `test_repository_contract.py` | the same CRUD/search/filter/sort/pagination/images/outfits/collections/history/delete-all contract on **both** repositories (Supabase through `tests/fakes.py`, which emulates PostgREST, Storage, Auth and RLS) |
| `test_persistence_and_security.py` | data survives restart (local re-open; new Supabase session), owner isolation, retries, BackendUnavailable, reconnect, JWT refresh, NotAuthorized, local & Supabase sign-in, owner-only, lock-out, password change, config validation incl. service-key detection |
| `test_backup_and_policy.py` | export contents, restore into another backend with ID remapping, invalid backups, **no AI dependencies/imports/API calls**, no committed secrets |
| `test_app_pages.py` | Streamlit AppTest: setup page, sign-in gating, wrong password, every page runs, planner save, studio save, add item, save settings |
| `test_i18n.py` | every `_()`/`N_()` string and dynamic message has Vietnamese, placeholders match, no stale entries, every vocabulary value (categories, types, occasions, styles, hair, nails, 97 colors…) has a Vietnamese label, engine explanations come out in Vietnamese, Vietnamese PNG text renders real glyphs, web font supports Vietnamese |
| `test_schema_postgres.py` (marker `postgres`) | runs `database/*.sql` twice on PostgreSQL 16 (Docker or `COLORMUSE_PG_DSN`) with Supabase stubs: seed, owner CRUD, cross-user read/update/delete blocked, cross-owner inserts rejected, child-parent ownership, anon denied, colors read-only, check/unique constraints, cascades/set-null, updated_at trigger, storage folder policies |
| `tests/e2e/test_browser.py` (marker `e2e`) | Playwright/Chromium: sign-in, all 7 pages at desktop 1366×900 and mobile 390×844 without exceptions (screenshots), wrong password, mannequin SVG in DOM, add piece with photo → color extraction → save, matcher → studio → save → PNG download |

The suite never reads your real `.env`: `tests/conftest.py` sets `COLORMUSE_DOTENV=none`
(the app reads `<project>/.env` by default; `COLORMUSE_DOTENV=<path>` points it elsewhere).

## Browser tests
```bash
python -m playwright install chromium-headless-shell
python scripts/seed_demo_wardrobe.py --dir tests/_artifacts/demo
COLORMUSE_BACKEND=local COLORMUSE_LOCAL_PASSWORD=demo-pass OWNER_EMAIL=zidi@example.com \
  COLORMUSE_LOCAL_DIR=tests/_artifacts/demo streamlit run app.py --server.port 8599 --server.headless true
# in another terminal
COLORMUSE_E2E_URL=http://localhost:8599 pytest tests/e2e
```
Screenshots: `tests/_artifacts/screens/` (git-ignored).

Camera scan in a real browser (Chromium's fake webcam plays a generated video of a sage garment; the test
takes the photo, checks the detected color and recommendations, and saves the piece):
`pytest tests/e2e/test_scan_camera.py --e2e-url=http://localhost:8599` (app started with `COLORMUSE_LANGUAGE=vi`).
Companion app in a real browser: start `streamlit run companion.py --server.port 8600` the same way
(local mode, `COLORMUSE_LANGUAGE=vi`), then `pytest tests/e2e/test_scan_camera.py --e2e-companion-url=http://localhost:8600`
— sign in → choose "Giày" → shutter → colors & recommendations → save → "Quét món khác" resets the camera,
and the piece is verified in the shared wardrobe database.
Scan logic itself: `tests/test_scan.py`; companion app sign-in/screens: `tests/test_app_pages.py`.

Vietnamese browser checks (all pages on desktop + mobile, Studio panel stays open while editing,
several chips selectable without reopening): start the app the same way but with
`COLORMUSE_LANGUAGE=vi`, then `pytest tests/e2e/test_browser_vi.py --e2e-url=http://localhost:8599`.

## Without AI
The whole suite runs with no AI package installed and no API key; `test_backup_and_policy.py`
fails if one is ever added.

## Live deployment check
After deploying, follow "Verify the live app" in DEPLOYMENT.md (sign in, add a photo, reload,
confirm persistence, wrong password rejected).
