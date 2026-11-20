# Architecture

```
Browser ──websocket──▶ Streamlit app (app.py + pages/)      ← Streamlit Community Cloud
                          │
                          ├─ src/components   UI building blocks, theme CSS
                          ├─ src/services     auth · session cache · image processing · backup · styling
                          ├─ src/core         color engine (pure, deterministic)
                          ├─ src/visualizer   SVG assets → SVG markup / Pillow PNG
                          ├─ src/models       dataclasses shared by every layer
                          └─ src/database     Repository contract
                                 ├─ SupabaseRepository ──HTTPS──▶ Supabase Postgres (RLS) + Storage
                                 └─ LocalRepository   (dev/tests only: SQLite + folder)
```

There is no separate backend: Streamlit is both UI and application server.

## Request flow
1. `app.py` loads settings (Streamlit secrets → env → `.env`), shows **Setup** if config is
   missing, **Sign in** if there's no session, otherwise `st.navigation` (top bar; collapses into
   a drawer on phones).
2. Sign-in (`src/services/auth.py`) creates a per-browser-session Supabase client with the
   anon key and the owner's JWT, and wraps it in `SupabaseRepository`. The client is stored in
   `st.session_state` — never in a global cache — so tokens can't leak between sessions.
3. Pages call `session.repo()` and the memoised helpers in `src/services/session.py`.

## Key decisions
| Decision | Why |
|---|---|
| Repository interface with two implementations | Same UI on dev and prod; one contract test-suite runs against both (Supabase via an in-memory fake that emulates RLS). |
| Pure engine in `src/core` | Deterministic, fast to test, reusable by a future AI layer. |
| One `Outfit` model for both visualizers | Changing the outfit updates flat-lay and mannequin identically. |
| Own SVG path rasteriser (no cairo) | Streamlit Cloud needs no system packages; SVG preview and PNG export come from the same geometry. |
| Form-based studio, no drag-and-drop | Reliable on touchscreens and Streamlit; no fake interactivity. |
| Session-level caches invalidated on write | Avoids re-querying Supabase on every rerun without stale data; bounded LRUs for image bytes and signed URLs. |
| Signed URLs for thumbnails | Private bucket; browser loads images directly from Supabase CDN (fast, low app memory). |
| Single owner enforced three ways | Sign-ups disabled in Supabase, `OWNER_EMAIL` check in the app, RLS on every row/object. |

## Performance on the free tier
- Images are resized to ≤1280 px (JPEG q84) and 360 px thumbnails before upload.
- Grids show thumbnails via signed URLs; flat-lay downloads medium photos lazily (LRU of 48).
- Wardrobe and looks are paginated; the whole wardrobe is loaded once per session for the
  engine (personal wardrobes are small) and refreshed after writes.
- `st.cache_data` is used only for pure functions (garment thumbnail rendering, bounded).
- Heavy imports (scikit-image) are lazy, used only during photo color extraction.
- PNG exports are rendered on demand ("Export images" → downloads).

## Resilience
`SupabaseRepository._call` classifies failures: transient network/5xx/timeouts are retried
with backoff (0.4 s, 1.2 s) and a client reconnect; an expired JWT triggers one token refresh;
otherwise domain errors are raised (`BackendUnavailable`, `NotAuthorized`, `BackendError`).
`ui.guarded` turns them into friendly messages with **Retry** / **Sign in again** — including
the common "free Supabase project paused after inactivity" case.

## Future AI stylist (not implemented — design only)
AI is disabled in this release; nothing imports or calls an AI provider. If added later, it
should be an optional service behind an interface such as:

```python
class StylistProvider(Protocol):
    def explain_outfit(self, outfit: Outfit, breakdown: ScoreBreakdown, prefs: UserPreferences) -> str: ...
    def suggest_edits(self, outfit: Outfit, wardrobe: list[WardrobeItem], ctx: OutfitContext) -> list[Outfit]: ...
```

Rules for that future work: the deterministic engine stays the source of truth for scores;
AI output must be validated against owned items and the domain model; the feature must be
toggleable and the app must keep working with it off; API keys live in Streamlit secrets.
