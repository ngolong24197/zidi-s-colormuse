# Security

## Threat model
One owner, private data (photos, wardrobe, preferences). Main risks: someone else signing in,
data exposed through the database API, leaked keys, brute-force, malicious uploads.

## Controls
| Area | Control |
|---|---|
| Accounts | No sign-up page. Supabase sign-ups disabled; owner created in the dashboard. App only accepts `OWNER_EMAIL` (constant-time compare) and re-checks the authenticated user's email. |
| Brute force | Per-session lock-out: 5 failures → 60 s wait. Supabase Auth has its own rate limits. |
| Database | RLS on every table; owner-only policies for select/insert/update/delete; restrictive policies so child rows can only reference the owner's parents; `anon` has no privileges; reference `colors` is read-only. The app also filters by `owner_id` (defence in depth). |
| Storage | Private bucket; policies restrict objects to `<auth.uid()>/…`; size (5 MB) and MIME limits; the app refuses paths outside the owner's folder; photos are served by short-lived signed URLs (1 h). |
| Keys | Only the anon/publishable key is used. Config validation rejects a service-role/secret key. Secrets live in Streamlit secrets / `.env` (git-ignored); `.env.example` and `secrets.toml.example` list names only. A test scans the repo for JWT-like strings. |
| Sessions | One Supabase client per browser session in `st.session_state` (never shared caches). Sign-out clears the session and caches. Expired tokens refresh once, else the user is asked to sign in again. |
| Uploads | Extension allow-list, real format check (Pillow), `verify()` for corrupt files, 10 MB limit, 40 MP decompression-bomb guard, minimum size; re-encoded to JPEG (EXIF/metadata stripped) before storage. |
| Output | All user text is HTML-escaped before `unsafe_allow_html`; SVG is generated from trusted assets with validated hex colors and escaped labels; no scripts. |
| Destructive actions | Delete piece/look needs confirmation; "Delete everything" requires typing DELETE. |
| AI | None. No third-party AI calls, no data leaves Supabase/Streamlit. |
| Privacy | Streamlit usage stats disabled in config. |

## Recommendations for the owner
- Use a unique password (≥ 12 chars) and keep the Supabase account protected with 2FA.
- Optionally restrict the Streamlit app to the owner's email in Streamlit Cloud sharing settings.
- Download a backup monthly (Settings → Data).

## Verification
`tests/test_schema_postgres.py` runs the real SQL policies on PostgreSQL (owner isolation, anon
denied, cross-owner inserts rejected, storage folders); `tests/test_persistence_and_security.py`
covers auth, lock-out, owner checks, service-key detection and RLS-emulated isolation.
