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
    if missing:
        return 1
    return 0 if roundtrip(s, password) else 1


def roundtrip(s, password: str) -> bool:
    """Write → new session → read back → delete, through the real SupabaseRepository.

    Only touches records it creates (named 'ColorMuse self-test') and removes them again.
    """
    import io

    from PIL import Image, ImageDraw
    from supabase import create_client

    from src.database.supabase_repo import SupabaseRepository
    from src.models.domain import Collection, Outfit, OutfitItem, WardrobeItem
    from src.services.image_processing import process_upload

    def session():
        c = create_client(s.supabase_url, s.supabase_anon_key)
        uid = str(c.auth.sign_in_with_password({"email": s.owner_email, "password": password}).user.id)
        return c, SupabaseRepository(c, uid, s.bucket)

    img = Image.new("RGB", (600, 800), (238, 238, 236))
    ImageDraw.Draw(img).rectangle((150, 160, 450, 640), fill=(163, 177, 138))
    buf = io.BytesIO()
    img.save(buf, "JPEG")

    c1, repo = session()
    created: dict[str, str] = {}
    ok = True
    try:
        item = repo.save_item(WardrobeItem(name="ColorMuse self-test", category="tops", primary_color="#A3B18A"))
        created["item"] = item.id
        p = process_upload(buf.getvalue(), "self-test.jpg")
        photo = repo.upload_item_image(item.id, p.full, p.thumb, p.width, p.height)
        look = Outfit(name="ColorMuse self-test", hair_style="bun")
        look.set_item(OutfitItem.from_wardrobe(item))
        look.set_item(OutfitItem(slot="nails", color_hex="#B3112E", variant="french"))
        repo.save_outfit(look)
        created["outfit"] = look.id
        col = repo.save_collection(Collection(name="ColorMuse self-test"))
        created["collection"] = col.id
        repo.add_to_collection(col.id, look.id)
        print("write        : piece + photo + look + collection saved")

        c2, fresh = session()  # a brand-new session, like after an app restart
        got = fresh.get_item(item.id)
        thumb = fresh.get_file(got.thumb_path) if got else None
        back = fresh.get_outfit(look.id)
        urls = fresh.signed_urls([photo.thumb_path])
        checks = {
            "piece": got is not None and got.primary_color == "#A3B18A",
            "photo": thumb == p.thumb,
            "signed url": bool(urls.get(photo.thumb_path)),
            "look + nails + hair": back is not None and back.get("nails").variant == "french" and back.hair_style == "bun",
            "collection": fresh.list_outfits(collection_id=col.id)[1] == 1,
        }
        ok = all(checks.values())
        print("read back    :", ", ".join(f"{k} {'OK' if v else 'FAILED'}" for k, v in checks.items()))
        c2.auth.sign_out()
    except Exception as exc:  # noqa: BLE001
        ok = False
        print("roundtrip    : FAILED -", type(exc).__name__, str(exc)[:200])
    finally:
        try:
            if "collection" in created:
                repo.delete_collection(created["collection"])
            if "outfit" in created:
                repo.delete_outfit(created["outfit"])
            if "item" in created:
                photo_path = (repo.get_item(created["item"]) or WardrobeItem(name="x", category="tops", primary_color="#000000")).thumb_path
                repo.delete_item(created["item"])
                gone = repo.get_item(created["item"]) is None and (not photo_path or repo.get_file(photo_path) is None)
                print("cleanup      :", "self-test data and photo removed" if gone else "INCOMPLETE - check the dashboard")
                ok = ok and gone
        except Exception as exc:  # noqa: BLE001
            ok = False
            print("cleanup      : FAILED -", str(exc)[:200])
        c1.auth.sign_out()
    return ok


if __name__ == "__main__":
    raise SystemExit(main())
