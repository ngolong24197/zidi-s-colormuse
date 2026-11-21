"""Check the Supabase configuration and connectivity without printing secrets.

Run:  python scripts/check_supabase.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_settings  # noqa: E402

PLACEHOLDERS = ("your-project-ref", "your-anon", "owner@example.com")


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
    if "@" in s.owner_email:
        user, domain = s.owner_email.split("@", 1)
        print("owner email  :", user[:2] + "...@" + domain)
    else:
        print("owner email  : (missing or invalid)")
    joined = s.supabase_url + s.supabase_anon_key + s.owner_email
    print("placeholders :", "YES - still the example values" if any(p in joined for p in PLACEHOLDERS) else "no")
    problems = s.problems()
    print("problems     :", "; ".join(problems) if problems else "none")
    if not s.supabase_configured:
        return 1

    import httpx

    headers = {"apikey": s.supabase_anon_key, "Authorization": "Bearer " + s.supabase_anon_key}
    base = s.supabase_url.rstrip("/")
    ok = True
    try:
        r = httpx.get(base + "/auth/v1/settings", headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            print("auth         : reachable; signups disabled =", data.get("disable_signup"))
        else:
            ok = False
            print("auth         : HTTP", r.status_code, r.text[:150])
        r = httpx.get(base + "/rest/v1/colors", params={"select": "name", "limit": "1"}, headers=headers, timeout=15)
        if r.status_code == 200:
            print("schema       : colors table exists (anon sees", len(r.json()), "rows - expected 0 because of RLS)")
        else:
            print("schema       : HTTP", r.status_code, r.text[:200])
    except httpx.HTTPError as exc:
        ok = False
        print("connection   :", type(exc).__name__, str(exc)[:200])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
