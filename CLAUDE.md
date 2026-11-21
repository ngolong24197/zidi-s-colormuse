# CLAUDE.md — working on ColorMuse

Private, single-owner Streamlit fashion styling app. Supabase (Postgres + Storage + Auth) in
production; a local SQLite backend exists **only** for development and tests.

## Commands
- Run: `streamlit run app.py` (configure `.env`; `COLORMUSE_BACKEND=local` needs `COLORMUSE_LOCAL_PASSWORD`)
- Demo data (local backend only): `python scripts/seed_demo_wardrobe.py`
- Tests: `pytest` (PostgreSQL RLS tests need Docker or `COLORMUSE_PG_DSN`)
- Browser tests: run the app on :8599 in local mode, then `COLORMUSE_E2E_URL=http://localhost:8599 pytest tests/e2e`
- Regenerate SVG assets: `python scripts/build_svg_assets.py`
- Regenerate color seed SQL: `python scripts/generate_color_seed.py` (after editing `src/core/color_library.py`)

## Layout
- `app.py` — config, sign-in gate, `st.navigation`. No feature code here.
- `pages/` — one file per module (home, color_matcher, wardrobe, outfit_studio, occasion_planner, saved_looks, settings).
- `src/core/` — pure, deterministic engine: color conversion, library, harmony, scoring, recommender, outfit engine, beauty (nails/hair).
- `src/models/domain.py` — dataclasses + vocabularies shared everywhere (the single `Outfit` model drives both visualizers).
- `src/database/` — `Repository` contract (`base.py`), `supabase_repo.py`, `local_repo.py`.
- `src/services/` — auth, session/caching, image processing, backup, styling glue.
- `src/visualizer/` — SVG asset parser/rasteriser, patterns, mannequin, flat-lay, PNG poster export.
- `src/components/` — theme CSS and reusable UI pieces.
- `assets/mannequins`, `assets/clothing_templates` — generated SVGs (edit the generator, not the files).
- `database/` — `schema.sql`, `storage.sql`, `seed_colors.sql`.

## Rules
- **No AI** in this release: no AI providers, API keys or AI dependencies (a test enforces this).
- Never use or store the Supabase service-role key. The app uses the anon key + owner session; RLS does the rest.
- Every new table needs `owner_id` + the four owner policies (see `schema.sql`), and a contract test.
- Keep both repositories behaviourally identical; add cases to `tests/test_repository_contract.py`.
- Engine code stays pure and deterministic (sort ties by name/id). Explanations accompany every score.
- Use session-level caches (`src/services/session.py`) for user data; call `session.invalidate()` after writes.
- New garment shapes: add to `scripts/build_svg_assets.py`, map in `SUBCATEGORIES` (domain), regenerate.
- Don't commit secrets, `.env`, `.streamlit/secrets.toml` or `.colormuse_local/`.
- Art style for generated illustrations: "elegant watercolor fashion editorial illustration, soft blush and ivory palette".
- **Bilingual (English / Tiếng Việt).** Wrap every user-visible string in `_("English text")` (or `N_()`
  when translated later via a variable); vocabulary values go through `label(kind, value)`, colors through
  `cname(hex)`. Add the Vietnamese to `src/i18n_vi.py` — `tests/test_i18n.py` fails on any missing entry.
  Never use `_` as a throwaway variable in modules that import it.
- Multi-select UI: use `ui.multi_choice` / `ui.color_multi_choice` (chips that stay open), not `st.multiselect`;
  give expanders whose title changes a stable `key=` so they don't collapse.
- Update `docs/DEVELOPMENT_LOG.md` when finishing a stage.
