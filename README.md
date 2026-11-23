# ColorMuse

**Your personal wardrobe. Your personal stylist.**

ColorMuse is a private, single-owner fashion styling web app built with Python and Streamlit.
It helps one person pick clothing colors, coordinate outfits from her own wardrobe, try looks
on a flat-lay board and an illustrated mannequin (including **hairstyle, hair color and nail
polish**), plan outfits for occasions and keep a lookbook of favourite looks.

- 🎨 **Color Matcher** — manual, photo or wardrobe input; complementary, analogous, triadic,
  split-complementary, monochromatic, neutral and contrast harmonies; scored and explained
  suggestions for shirts, skirts, pants, dresses, shoes, handbags, jewelry, accessories,
  outerwear — plus nail colors and colors that flatter your hair.
- 👗 **My Wardrobe** — add/edit/delete, photos (validated, cropped, compressed, thumbnailed),
  automatic dominant-color extraction with manual correction, search, filters, sorting, favorites.
- 🪡 **Outfit Studio** — one outfit model rendered two ways: a **flat-lay** (layout templates,
  your photos or recolorable garment templates) and a **layered SVG mannequin** (recolor,
  patterns, 7 hairstyles, hair color, skin tone, 4 nail shapes). Save, duplicate, export PNG.
- 📅 **Occasion Planner** — 11 occasions; complete looks generated only from pieces you own.
- ♥ **Saved Looks** — favorites, collections, notes, search, duplicate, delete, PNG export.
- ⚙️ **Settings** — style & beauty preferences, favorite/avoided colors, scoring weights,
  password, backup/restore, delete all personal data.

- 📷 **Scan** — point the phone camera at a piece and tap once: colors, what to wear with it, matching
  pieces you own, "you already own something similar", and **Add to my wardrobe?** pre-filled.
  Also available as a standalone phone companion app, `companion.py` (same data, same sign-in).
- 🌐 **English / Tiếng Việt** — switch any time in the top bar (also translates the stylist's explanations,
  color names and PNG exports).

**No AI.** Every recommendation comes from a deterministic, testable color-theory engine.
No AI provider, API key or AI dependency is used.

## Stack

Python · Streamlit · Supabase PostgreSQL (records, RLS) · Supabase Storage (photos) ·
Pillow · OpenCV · NumPy · scikit-image · pytest · Streamlit Community Cloud.

## Quick start (local development)

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt

# Option A — local dev backend (SQLite + folder, no cloud needed)
cp .env.example .env              # then set COLORMUSE_BACKEND=local and COLORMUSE_LOCAL_PASSWORD
python scripts/seed_demo_wardrobe.py   # optional demo wardrobe
streamlit run app.py

# Option B — your Supabase project (same as production)
#   set COLORMUSE_BACKEND=supabase, SUPABASE_URL, SUPABASE_ANON_KEY, OWNER_EMAIL in .env
streamlit run app.py
```

Sign in with `OWNER_EMAIL` and the password (local: `COLORMUSE_LOCAL_PASSWORD`;
Supabase: the owner account's password).

## Deploy (free)

1. Create a Supabase project, run `database/schema.sql`, `database/storage.sql`,
   `database/seed_colors.sql` in the SQL editor.
2. Supabase → Authentication: **disable sign-ups**, create the owner user.
3. Streamlit Community Cloud → New app → this GitHub repo, main file `app.py`, Python 3.12.
4. Paste the secrets (see `.streamlit/secrets.toml.example`).

Full walkthrough: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Backups: [docs/DEPLOYMENT.md#backup-and-recovery](docs/DEPLOYMENT.md#backup-and-recovery).

## Tests

```bash
pytest                         # unit, contract, AppTest and (with Docker) PostgreSQL RLS tests
# browser tests: start the app in local mode on :8599, then
COLORMUSE_E2E_URL=http://localhost:8599 pytest tests/e2e
```

See [docs/TESTING.md](docs/TESTING.md).

## Documentation

[Product](docs/PRODUCT_SPECIFICATION.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Database](docs/DATABASE.md) · [Color engine](docs/COLOR_ENGINE.md) ·
[Visualizer](docs/VISUALIZER.md) · [Deployment](docs/DEPLOYMENT.md) ·
[Security](docs/SECURITY.md) · [Testing](docs/TESTING.md) · [Development log](docs/DEVELOPMENT_LOG.md)

Fonts: Cormorant Garamond and Jost (SIL Open Font License, bundled in `assets/fonts`).
Illustrations in `assets/illustrations` were generated for this project with a local Stable Diffusion model.
