# Deployment (free tier) — Supabase + Streamlit Community Cloud

Total time ≈ 20 minutes. You need a GitHub account (the repo already lives at
`github.com/ngolong24197/zidi-s-colormuse`), a Supabase account and a Streamlit Community
Cloud account (sign in with GitHub).

## 1. Supabase project
1. <https://supabase.com> → **New project** (free plan). Pick a region close to the owner and a
   strong database password (store it in a password manager).
2. **SQL Editor** → New query → paste and run, in order:
   `database/schema.sql`, `database/storage.sql`, `database/seed_colors.sql`.
3. **Authentication → Sign In / Providers → Email**: keep Email enabled, **turn off "Allow new users to sign up"**.
   (Optionally turn off "Confirm email" — the owner account is created by you.)
4. **Authentication → Users → Add user → Create new user**: the owner's email + a strong
   password (≥ 10 characters). Tick "Auto confirm user".
5. **Project Settings → API**: copy the **Project URL** and the **anon / publishable** key.
   ⚠️ Do **not** copy the `service_role` / secret key anywhere — the app refuses to start with it.

## 2. Streamlit Community Cloud
1. <https://share.streamlit.io> → **Create app** → "Deploy a public app from GitHub".
2. Repository `ngolong24197/zidi-s-colormuse`, branch `main`, main file `app.py`.
3. **Advanced settings** → Python **3.12**, and **Secrets**:
   ```toml
   COLORMUSE_BACKEND = "supabase"
   SUPABASE_URL = "https://<project-ref>.supabase.co"
   SUPABASE_ANON_KEY = "<anon public key>"
   SUPABASE_BUCKET = "wardrobe"
   OWNER_EMAIL = "<owner email>"
   ```
4. Deploy. Optionally set a custom subdomain (e.g. `colormuse.streamlit.app`).
5. Recommended: App settings → **Sharing** → "Only specific people can view this app" and add
   the owner's email, for a second lock in front of the app's own sign-in.

## 3. Verify the live app
- Open the URL on a phone and a computer → Sign in with the owner account.
- Add a piece with a photo → it appears with its thumbnail → reload the browser, sign in again →
  it's still there (stored in Supabase).
- Supabase → Table editor shows rows in `wardrobe_items`; Storage → `wardrobe/<user-id>/...` has files.
- Try signing in with a wrong password → rejected; after 5 attempts, a one-minute lock-out.

## Local development against Supabase
Put the same keys in `.env` (or `.streamlit/secrets.toml`) and run `streamlit run app.py`.

## Free-tier notes
- **Streamlit Cloud** apps sleep after a period without visits; the first visit wakes them (≈ 30 s).
- **Supabase free projects pause after ~1 week of inactivity.** The app then shows
  "can't reach its cloud database… restore it from the Supabase dashboard". Fix: Supabase dashboard →
  project → **Restore**. Using the app at least weekly avoids pausing.
- Storage free quota is 1 GB: photos are compressed to ~100–250 KB plus ~15 KB thumbnails, so
  thousands of pieces fit.

## Backup and recovery
Free Supabase plans don't include downloadable automatic backups, so:

1. **In-app backup (recommended, monthly):** Settings → Data → *Prepare backup* → download the
   `.zip` (all records as JSON + every photo). Keep it in cloud storage you trust.
2. **Restore:** Settings → Data → *Restore from a backup* → upload the zip. Records are added
   with new IDs (nothing is overwritten); links between looks, pieces and collections are remapped.
   This also moves data to a brand-new Supabase project after setting it up with steps 1–2.
3. **Database dump (advanced):** Supabase → Project Settings → Database → connection string, then
   `pg_dump "<connection string>" --schema=public --data-only -f colormuse.sql`
   (Storage files are not included in a database dump — use the in-app backup for photos.)
4. **Disaster recovery checklist:** new Supabase project → run the three SQL files → create the
   owner user → update Streamlit secrets → sign in → restore the latest backup zip.

## Updating the app
Push to `main`; Streamlit Cloud redeploys automatically. Schema changes: run the updated SQL
in Supabase **before** pushing code that needs it.
