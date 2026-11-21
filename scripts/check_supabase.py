"""Check the Supabase configuration, schema and owner sign-in without printing secrets.

Run:  python scripts/check_supabase.py

Read-only: it signs in (if COLORMUSE_E2E_PASSWORD is set), reads, and signs out.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import _load_dotenv, dotenv_path, load_settings  # noqa: E402

PLACEHOLDERS = ("your-project-ref", "your-anon", "owner@example.com")
TABLES = ("colors", "user_preferences", "wardrobe_items", "clothing_images", "outfits", "outfit_items",
          "outfit_collections", "collection_outfits", "recommendation_history")


def mask(value: str) -> str:
    if not value:
        return "(empty)"
    return value[:4] + "..." + value[-4:] if len(value) > 10 else "***"


def main() -> int:
    s = load_settings()
    print("backend      :", s.backend)
    print("url          :", (s.supabase_url[:8] + "..." + s.supabase_url[-16:]) if s.supabase_url else "(empty)")
    print("anon key     :", mask(s.supabase_anon_key), "length", len(s.supabase_anon_key))
    print("bucket       :", s.bucket)
    joined = s.supabase_url + s.supabase_anon_key + s.owner_email
    print("placeholders :", "YES - still the example values" if any(p in joined for p in PLACEHOLDERS) else "no")
    problems = s.problems()
    print("problems     :", "; ".join(problems) if problems else "none")
    if not s.supabase_configured:
        return 1

    import httpx

    headers = {"apikey": s.supabase_anon_key, "Authorization": "Bearer " + s.supabase_anon_key}
    base = s.supabase_url.rstrip("/")
    try:
        r = httpx.get(base + "/auth/v1/settings", headers=headers, timeout=20)
        if r.status_code != 200:
            print("auth         : HTTP", r.status_code, r.text[:150])
            return 1
        print("auth         : reachable; public sign-ups disabled =", r.json().get("disable_signup"))
    except httpx.HTTPError as exc:
        print("connection   : FAILED", type(exc).__name__, str(exc)[:200])
        return 1

    dot = dotenv_path()
    password = _load_dotenv(dot).get("COLORMUSE_E2E_PASSWORD", "") if dot else ""
    if not password:
        print("sign-in      : skipped (COLORMUSE_E2E_PASSWORD not set)")
        return 0

    from supabase import create_client

    client = create_client(s.supabase_url, s.supabase_anon_key)
    try:
        resp = client.auth.sign_in_with_password({"email": s.owner_email, "password": password})
    except Exception as exc:  # noqa: BLE001
        print("sign-in      : FAILED -", str(exc)[:200])
        print("               -> create the user in Supabase > Authentication > Users (auto-confirm),")
        print("                  or fix OWNER_EMAIL / COLORMUSE_E2E_PASSWORD in .env")
        return 1
    user = resp.user
    print("sign-in      : OK as owner (user id", str(user.id)[:8] + "...)")

    missing = []
    for t in TABLES:
        try:
            client.table(t).select("*", count="exact").limit(1).execute()
        except Exception as exc:  # noqa: BLE001
            missing.append(t)
            detail = str(exc)[:90]
    if missing:
        print("tables       : MISSING", ", ".join(missing))
        print("               (" + detail + ")")
        print("               -> run database/schema.sql, storage.sql, seed_colors.sql in the Supabase SQL editor")
    else:
        colors = client.table("colors").select("name", count="exact").limit(1).execute()
        print("tables       : all", len(TABLES), "present; colors seeded:", colors.count)

    try:
        client.storage.from_(s.bucket).list(str(user.id), {"limit": 1})
        print("storage      : bucket", repr(s.bucket), "accessible")
    except Exception as exc:  # noqa: BLE001
        print("storage      : bucket", repr(s.bucket), "NOT accessible -", str(exc)[:120])
        missing.append("bucket")
    try:
        client.auth.sign_out()
    except Exception:  # noqa: BLE001
        pass
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
