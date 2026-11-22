# Development log

## 2026-11-21 — Initial release (stages 1–7)

### Environment assessment
Windows 11, Python 3.12.10, Node 24, Docker 28 (used for PostgreSQL tests), GitHub remote
`ngolong24197/zidi-s-colormuse`. No Supabase CLI and no Supabase/Streamlit Cloud credentials
were available to the build agent, so the cloud deployment itself is a documented manual step.

### Stage 1 — Foundation
Python project, `.streamlit/config.toml` theme (ivory/blush/dusty rose/burgundy/taupe/charcoal,
Cormorant Garamond + Jost), config loader (secrets → env → .env), Supabase schema + storage
policies + seed, single-owner auth (Supabase Auth, owner email check, lock-out), app shell with
setup / sign-in / top navigation, editorial CSS and components.

### Stage 2 — Color engine
97-color library, RGB/HSL/HSV/Lab conversions, CIEDE2000 (reference-tested), harmony rules,
six-component configurable scoring with explanations, per-category recommender with diversity,
wardrobe matching.

### Stage 3 — Wardrobe
Repository contract with Supabase and local implementations, photo validation/compression/
thumbnails/cropping, color extraction (OpenCV k-means in Lab, GrabCut + border-color background
reduction), signed-URL thumbnails, full CRUD UI with search/filter/sort/pagination.

### Stage 4 — Visualizer
SVG asset generator (croquis + 33 garments), own path rasteriser (no cairo), 7 patterns,
mannequin (SVG + PNG), flat-lay with 3 layout templates and photo/template pieces, PNG poster export.

### Stage 5 — Styling
Outfit scoring, occasion planner (beam search over owned pieces), garment-type × occasion
suitability, Outfit Studio, Saved Looks with collections/notes, personalisation in Settings,
backup/restore/delete-all.

**Owner request added mid-build: nails and hair (color and style).** Implemented as:
7 hairstyles (long waves, bob, ponytail, bun, curls, pixie, side braid) as back/front SVG layers,
any hair color (natural presets + custom), a `nails` outfit slot with any polish color and
4 shapes (almond, round, square, French) drawn on the mannequin and as a polish card in the
flat-lay; nail-polish recommendations (Color Matcher, Studio, auto-finish in the planner),
rule-based hairstyle suggestions, "colors that flatter your hair", hair-color note in outfit
scores; defaults in Settings → Hair & beauty; stored in `outfits.hair_style`,
`outfit_items (slot='nails')`, `user_preferences.hair_style/nail_shape`.

### Stage 6 — Quality
Test results at the end of this stage (run locally on Windows):
- `pytest` → unit, contract (both backends), AppTest, backup, policy and PostgreSQL RLS suites — all passing.
- `pytest tests/e2e` (Chromium, desktop 1366×900 + mobile 390×844) — all passing.
Bugs found and fixed during testing: tie-breaking timestamps on Windows' coarse clock
(strictly increasing `utcnow`), bags dropped from evening looks (bag slack in the generator),
unrealistic picks (sneakers for office, tote for date night) → suitability table.

### Stage 7 — Deployment
Repository prepared for Streamlit Community Cloud (requirements, config, secrets example, docs).
**Outstanding (needs the owner's accounts):** create the Supabase project, run the SQL, create the
owner user, create the Streamlit app and paste secrets, then verify the live app
(docs/DEPLOYMENT.md §3).

## 2026-11-21 — Connected to the owner's Supabase project
- Owner added `.env` with the project URL, anon key, owner email and a test password.
- Fixed test isolation: the suite now ignores the real `.env` (`COLORMUSE_DOTENV=none`).
- Schema created via `database/setup_all.sql`; public sign-ups disabled.
- `scripts/check_supabase.py` against the real project: all 9 tables, 97 colors, owner sign-in,
  storage, and a full write → fresh-session read-back → cleanup round-trip all passed.
- Still to do: deploy on Streamlit Community Cloud with the same secrets; browser tests against
  the Supabase-backed app (needs permission to start Streamlit locally).

## 2026-11-22 — Vietnamese language + multi-choice usability
- **Tiếng Việt** throughout: all pages, the stylist's explanations (engine sentences are templates),
  garment/occasion/style/hair/nail names, all 97 color names, error messages and PNG exports.
  Switch in the top bar or on the sign-in page; remembered for the session and in the URL (`?lang=vi`);
  default via optional `COLORMUSE_LANGUAGE`. No database change. `src/i18n.py` + `src/i18n_vi.py`.
- Fonts: web body font changed from Jost to **Be Vietnam Pro** (Jost lacks Vietnamese stacked diacritics);
  Vietnamese PNG exports use the bundled Cormorant Garamond (glyph coverage tested).
- **Dropdowns that closed after each pick:** Outfit Studio piece panels now have stable keys (their title
  shows the current choice, which used to recreate and collapse them); seasons/styles/occasions/collections
  use tap-to-toggle chips; color lists use chips in a panel that stays open, with a preview.
- Fixed a latent bug found by the new tests: `_` used as a throwaway variable shadowed the translator.
- Tests: `tests/test_i18n.py` (completeness, placeholders, every vocabulary value, Vietnamese engine
  output, Vietnamese PNG glyphs, fonts) and every page via AppTest in Vietnamese. 184 passed.
- Browser check in Vietnamese (`tests/e2e/test_browser_vi.py`, Chromium, desktop + mobile): all pages,
  Studio panel stays open across reruns, multiple chips selectable — 4/4 passed. Fixed two layout issues it
  revealed: the top row (language switch) hid under the fixed nav bar on desktop, and the switch was clipped.

### Known limitations / next ideas
- Background reduction is heuristic, not segmentation; manual crop and color correction remain available.
- No drag-and-drop in the studio (by design).
- Session ends when the browser tab is reloaded (Streamlit session model) — sign in again.
- Possible next steps: wear-tracking ("last worn"), weather-aware planning, optional AI stylist
  behind the interface sketched in ARCHITECTURE.md.
