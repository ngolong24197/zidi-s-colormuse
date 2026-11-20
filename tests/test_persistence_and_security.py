"""Restart persistence, owner isolation (RLS emulation), resilience and auth."""

from __future__ import annotations

import pytest

from src.config import _looks_like_service_key, load_settings
from src.database.base import BackendUnavailable, NotAuthorized
from src.database.local_repo import LocalRepository
from src.database.supabase_repo import SupabaseRepository
from src.models.domain import Outfit, OutfitItem, UserPreferences, WardrobeItem
from src.services.auth import AuthError, Throttle, change_password, sign_in
from tests.conftest import make_supabase_repo
from tests.fakes import FakeAPIError, FakeClient, FakeUser


def test_local_data_survives_restart(tmp_path, photo):
    from src.services.image_processing import process_upload

    r1 = LocalRepository(tmp_path, "owner")
    it = r1.save_item(WardrobeItem(name="Coat", category="outerwear", primary_color="#C8AD91"))
    p = process_upload(photo, "c.jpg")
    r1.upload_item_image(it.id, p.full, p.thumb, p.width, p.height)
    o = Outfit(name="Autumn")
    o.set_item(OutfitItem.from_wardrobe(it))
    r1.save_outfit(o)
    r1.save_preferences(UserPreferences(display_name="Zidi"))
    r1.close()
    r2 = LocalRepository(tmp_path, "owner")  # "application restart"
    assert r2.get_item(it.id).name == "Coat"
    assert r2.get_file(r2.get_item(it.id).thumb_path) == p.thumb
    assert r2.get_outfit(o.id).get("outerwear").wardrobe_item_id == it.id
    assert r2.get_preferences().display_name == "Zidi"


def test_supabase_data_survives_new_session(fake_db):
    r1 = make_supabase_repo(fake_db)
    it = r1.save_item(WardrobeItem(name="Coat", category="outerwear", primary_color="#C8AD91"))
    # a brand new client/session for the same user (e.g. app restarted, user signs in again)
    client = FakeClient(fake_db, FakeUser(r1.owner_id, "owner@example.com"))
    r2 = SupabaseRepository(client, r1.owner_id, sleep=lambda s: None)
    assert r2.get_item(it.id).name == "Coat"


def test_local_owner_isolation(tmp_path):
    a = LocalRepository(tmp_path, "alice")
    b = LocalRepository(tmp_path, "bob")
    it = a.save_item(WardrobeItem(name="Secret", category="tops", primary_color="#FFFFFF"))
    assert b.get_item(it.id) is None
    assert b.list_items()[1] == 0
    from src.database.base import NotFound

    with pytest.raises(NotFound):
        b.save_item(WardrobeItem(id=it.id, name="Hijack", category="tops", primary_color="#000000"))
    assert a.get_item(it.id).name == "Secret"


def test_supabase_owner_isolation(fake_db):
    alice = make_supabase_repo(fake_db, "alice@example.com")
    bob = make_supabase_repo(fake_db, "bob@example.com")
    it = alice.save_item(WardrobeItem(name="Secret", category="tops", primary_color="#FFFFFF"))
    assert bob.get_item(it.id) is None and bob.list_items()[1] == 0
    o = Outfit(name="A")
    o.set_item(OutfitItem(slot="top", color_hex="#FFFFFF"))
    alice.save_outfit(o)
    # bob can't attach items to alice's outfit, nor upload into alice's folder
    with pytest.raises(FakeAPIError):
        bob.client.table("outfit_items").insert({"outfit_id": o.id, "slot": "top", "color_hex": "#000000",
                                                 "owner_id": bob.owner_id}).execute()
    with pytest.raises(FakeAPIError):
        bob.client.storage.from_("wardrobe").upload(f"{alice.owner_id}/items/x.jpg", b"x")
    assert bob.get_file(f"{alice.owner_id}/items/x.jpg") is None


def test_transient_errors_are_retried(fake_db):
    repo = make_supabase_repo(fake_db)
    fake_db.fail_next = 2  # two connection failures, then success
    assert repo.list_items()[1] == 0


def test_unavailable_after_retries(fake_db):
    repo = make_supabase_repo(fake_db)
    fake_db.fail_next = 10
    with pytest.raises(BackendUnavailable) as exc:
        repo.list_items()
    assert "paused" in str(exc.value)


def test_reconnect_hook_used(fake_db):
    repo = make_supabase_repo(fake_db)
    calls = []
    original = repo.client
    repo._on_reconnect = lambda: calls.append(1) or original
    fake_db.fail_next = 1
    repo.list_collections()
    assert calls == [1]


def test_expired_jwt_refreshes_once(fake_db):
    repo = make_supabase_repo(fake_db)
    fake_db.expired = True
    assert repo.list_collections() == []
    assert repo.client.auth.refreshes == 1


def test_auth_failure_raises_not_authorized(fake_db):
    repo = make_supabase_repo(fake_db)
    repo.client.user = None
    repo.client.auth.refresh_session = lambda: (_ for _ in ()).throw(FakeAPIError("no session", "401", 401))
    with pytest.raises(NotAuthorized):
        repo.list_items()


# ---------------------------------------------------------------- auth & config
def _settings(**kw):
    base = {"COLORMUSE_BACKEND": "local", "COLORMUSE_LOCAL_PASSWORD": "pw-123456", "OWNER_EMAIL": "zidi@example.com"}
    base.update(kw)
    return load_settings(base)


def test_local_sign_in(tmp_path):
    s = _settings(COLORMUSE_LOCAL_DIR=str(tmp_path))
    sess = sign_in(s, "Zidi@Example.com ", "pw-123456", Throttle())
    assert sess.user_id == "local-owner" and sess.repo.backend_name == "local"
    with pytest.raises(AuthError):
        sign_in(s, "zidi@example.com", "wrong", Throttle())
    with pytest.raises(AuthError):
        sign_in(s, "intruder@example.com", "pw-123456", Throttle())
    with pytest.raises(AuthError):
        sign_in(s, "", "", Throttle())


def test_throttle_locks_out_after_repeated_failures(tmp_path):
    s = _settings(COLORMUSE_LOCAL_DIR=str(tmp_path))
    t = Throttle()
    for _ in range(5):
        with pytest.raises(AuthError):
            sign_in(s, "zidi@example.com", "nope", t)
    with pytest.raises(AuthError, match="Too many attempts"):
        sign_in(s, "zidi@example.com", "pw-123456", t)


def test_supabase_sign_in_with_fake(fake_db):
    fake_db.add_user("zidi@example.com", "correct horse")
    s = load_settings({"COLORMUSE_BACKEND": "supabase", "SUPABASE_URL": "https://x.supabase.co",
                       "SUPABASE_ANON_KEY": "anon", "OWNER_EMAIL": "zidi@example.com"})
    sess = sign_in(s, "zidi@example.com", "correct horse", Throttle(), client_factory=lambda: FakeClient(fake_db))
    assert sess.repo.backend_name == "supabase"
    assert sess.repo.list_items()[1] == 0
    with pytest.raises(AuthError):
        sign_in(s, "zidi@example.com", "wrong", Throttle(), client_factory=lambda: FakeClient(fake_db))
    change_password(sess, "a much longer password")
    assert fake_db.users["zidi@example.com"][1] == "a much longer password"
    with pytest.raises(AuthError):
        change_password(sess, "short")


def test_non_owner_account_rejected(fake_db):
    fake_db.add_user("other@example.com", "pw-pw-pw-pw")
    s = load_settings({"COLORMUSE_BACKEND": "supabase", "SUPABASE_URL": "https://x.supabase.co",
                       "SUPABASE_ANON_KEY": "anon", "OWNER_EMAIL": "zidi@example.com"})
    with pytest.raises(AuthError):
        sign_in(s, "other@example.com", "pw-pw-pw-pw", Throttle(), client_factory=lambda: FakeClient(fake_db))


def test_config_problems_and_service_key_detection():
    import base64
    import json

    payload = base64.urlsafe_b64encode(json.dumps({"role": "service_role"}).encode()).decode().rstrip("=")
    service_jwt = f"eyJhbGciOiJIUzI1NiJ9.{payload}.sig"
    assert _looks_like_service_key(service_jwt)
    assert _looks_like_service_key("sb_secret_abc")
    assert not _looks_like_service_key("sb_publishable_abc")
    s = load_settings({"COLORMUSE_BACKEND": "supabase", "SUPABASE_URL": "https://x.supabase.co",
                       "SUPABASE_ANON_KEY": service_jwt, "OWNER_EMAIL": "a@b.c"})
    assert any("service-role" in p for p in s.problems())
    assert load_settings({"COLORMUSE_BACKEND": "supabase"}).problems()
    assert not _settings().problems()
    assert load_settings({"COLORMUSE_BACKEND": "nope"}).problems()
