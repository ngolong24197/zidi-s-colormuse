"""Apply database/*.sql to a real PostgreSQL and verify constraints + Row Level Security.

Supabase-specific pieces (auth.users, auth.uid(), storage schema, roles) are
stubbed minimally so the real policies run unmodified.

Uses COLORMUSE_PG_DSN if set, otherwise starts a throwaway postgres:16-alpine
container with Docker. Skipped when neither is available.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[1]

SUPABASE_STUBS = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
end $$;
create schema if not exists auth;
create table if not exists auth.users (id uuid primary key, email text);
create or replace function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to anon, authenticated;
grant execute on function auth.uid() to anon, authenticated;
grant usage on schema public to anon, authenticated;

create schema if not exists storage;
create table if not exists storage.buckets (id text primary key, name text, public boolean,
  file_size_limit bigint, allowed_mime_types text[]);
create table if not exists storage.objects (id uuid primary key default gen_random_uuid(), bucket_id text, name text);
alter table storage.objects enable row level security;
create or replace function storage.foldername(name text) returns text[] language sql immutable as
  $$ select (string_to_array(name, '/'))[1:array_length(string_to_array(name, '/'), 1) - 1] $$;
grant usage on schema storage to anon, authenticated;
grant select, insert, update, delete on storage.objects to authenticated;
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def dsn():
    env = os.environ.get("COLORMUSE_PG_DSN")
    if env:
        yield env
        return
    if not shutil.which("docker"):
        pytest.skip("Docker not available and COLORMUSE_PG_DSN not set")
    port = _free_port()
    name = f"colormuse-test-{uuid.uuid4().hex[:8]}"
    try:
        subprocess.run(["docker", "run", "-d", "--rm", "--name", name, "-e", "POSTGRES_PASSWORD=test",
                        "-p", f"127.0.0.1:{port}:5432", "postgres:16-alpine"], check=True, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError) as exc:
        pytest.skip(f"Could not start PostgreSQL container: {exc}")
    url = f"postgresql://postgres:test@127.0.0.1:{port}/postgres"
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with psycopg.connect(url, connect_timeout=2) as c:
                c.execute("select 1")
            break
        except psycopg.OperationalError:
            time.sleep(1)
    else:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        pytest.skip("PostgreSQL container did not become ready")
    try:
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


@pytest.fixture(scope="module")
def db(dsn):
    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute("create extension if not exists pgcrypto")
    conn.execute(SUPABASE_STUBS)
    for f in ("schema.sql", "storage.sql", "seed_colors.sql"):
        conn.execute((ROOT / "database" / f).read_text(encoding="utf-8"))
    # idempotent: running everything a second time must succeed
    for f in ("schema.sql", "storage.sql", "seed_colors.sql"):
        conn.execute((ROOT / "database" / f).read_text(encoding="utf-8"))
    yield conn
    conn.close()


@pytest.fixture
def users(db):
    a, b = uuid.uuid4(), uuid.uuid4()
    db.execute("insert into auth.users (id, email) values (%s, 'a@x.com'), (%s, 'b@x.com')", (a, b))
    return a, b


class As:
    """Run statements as the `authenticated` role with a given JWT subject (or as anon)."""

    def __init__(self, db, uid=None, role="authenticated"):
        self.db, self.uid, self.role = db, uid, role

    def __enter__(self):
        self.tx = self.db.transaction()
        self.tx.__enter__()
        self.db.execute(f"set local role {self.role}")
        self.db.execute("select set_config('request.jwt.claim.sub', %s, true)", (str(self.uid) if self.uid else "",))
        return self.db

    def __exit__(self, *exc):
        return self.tx.__exit__(*exc)


def _insert_item(conn, owner, name="Blouse"):
    return conn.execute(
        "insert into public.wardrobe_items (owner_id, name, category, primary_color) values (%s, %s, 'tops', '#E8C9C5') returning id",
        (owner, name)).fetchone()[0]


def test_seeded_colors(db):
    n = db.execute("select count(*) from public.colors").fetchone()[0]
    from src.core.color_library import COLOR_LIBRARY

    assert n == len(COLOR_LIBRARY)


def test_owner_can_crud_own_rows(db, users):
    a, _ = users
    with As(db, a) as c:
        item = _insert_item(c, a)
        c.execute("update public.wardrobe_items set name = 'Silk blouse' where id = %s", (item,))
        assert c.execute("select name from public.wardrobe_items where id = %s", (item,)).fetchone()[0] == "Silk blouse"
        # owner_id defaults to auth.uid()
        c.execute("insert into public.outfit_collections (name) values ('Mine')")
        assert c.execute("select owner_id from public.outfit_collections where name='Mine'").fetchone()[0] == a


def test_other_user_cannot_see_or_modify(db, users):
    a, b = users
    with As(db, a) as c:
        item = _insert_item(c, a, "Private")
    with As(db, b) as c:
        assert c.execute("select count(*) from public.wardrobe_items where id = %s", (item,)).fetchone()[0] == 0
        assert c.execute("update public.wardrobe_items set name='x' where id=%s", (item,)).rowcount == 0
        assert c.execute("delete from public.wardrobe_items where id=%s", (item,)).rowcount == 0
    with As(db, a) as c:
        assert c.execute("select name from public.wardrobe_items where id=%s", (item,)).fetchone()[0] == "Private"


def test_cannot_insert_rows_for_someone_else(db, users):
    a, b = users
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with As(db, b) as c:
            _insert_item(c, a)


def test_child_rows_must_reference_own_parents(db, users):
    a, b = users
    with As(db, a) as c:
        outfit = c.execute("insert into public.outfits (name) values ('A look') returning id").fetchone()[0]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with As(db, b) as c:
            c.execute("insert into public.outfit_items (outfit_id, slot, color_hex) values (%s, 'top', '#FFFFFF')", (outfit,))


def test_anon_has_no_access(db, users):
    a, _ = users
    with As(db, a) as c:
        _insert_item(c, a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with As(db, None, role="anon") as c:
            c.execute("select count(*) from public.wardrobe_items").fetchone()


def test_colors_read_only_for_authenticated(db, users):
    a, _ = users
    with As(db, a) as c:
        assert c.execute("select count(*) from public.colors").fetchone()[0] > 80
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with As(db, a) as c:
            c.execute("insert into public.colors (name, hex, family) values ('Mine', '#123456', 'x')")


def test_constraints(db, users):
    a, _ = users
    with pytest.raises(psycopg.errors.CheckViolation):
        with As(db, a) as c:
            c.execute("insert into public.wardrobe_items (owner_id, name, category, primary_color) values (%s, 'x', 'tops', 'pink')", (a,))
    with pytest.raises(psycopg.errors.CheckViolation):
        with As(db, a) as c:
            c.execute("insert into public.wardrobe_items (owner_id, name, category, primary_color) values (%s, 'x', 'socks', '#FFFFFF')", (a,))
    with pytest.raises(psycopg.errors.UniqueViolation):
        with As(db, a) as c:
            o = c.execute("insert into public.outfits (name) values ('x') returning id").fetchone()[0]
            c.execute("insert into public.outfit_items (outfit_id, slot, color_hex) values (%s, 'top', '#FFFFFF')", (o,))
            c.execute("insert into public.outfit_items (outfit_id, slot, color_hex) values (%s, 'top', '#000000')", (o,))


def test_cascades_and_set_null(db, users):
    a, _ = users
    with As(db, a) as c:
        item = _insert_item(c, a)
        c.execute("insert into public.clothing_images (wardrobe_item_id, storage_path, thumb_path) values (%s, 'p', 't')", (item,))
        o = c.execute("insert into public.outfits (name) values ('x') returning id").fetchone()[0]
        c.execute("insert into public.outfit_items (outfit_id, wardrobe_item_id, slot, color_hex) values (%s, %s, 'top', '#E8C9C5')", (o, item))
        coll = c.execute("insert into public.outfit_collections (name) values ('c') returning id").fetchone()[0]
        c.execute("insert into public.collection_outfits (collection_id, outfit_id) values (%s, %s)", (coll, o))
        c.execute("insert into public.outfit_items (outfit_id, slot, color_hex, variant) values (%s, 'nails', '#B3112E', 'french')", (o,))
        c.execute("delete from public.wardrobe_items where id = %s", (item,))
        assert c.execute("select count(*) from public.clothing_images where wardrobe_item_id=%s", (item,)).fetchone()[0] == 0
        assert c.execute("select wardrobe_item_id from public.outfit_items where outfit_id=%s and slot='top'", (o,)).fetchone()[0] is None
        c.execute("delete from public.outfits where id = %s", (o,))
        assert c.execute("select count(*) from public.collection_outfits where outfit_id=%s", (o,)).fetchone()[0] == 0


def test_updated_at_trigger(db, users):
    a, _ = users
    with As(db, a) as c:
        item = _insert_item(c, a)
        before = c.execute("select updated_at from public.wardrobe_items where id=%s", (item,)).fetchone()[0]
    time.sleep(0.05)
    with As(db, a) as c:
        c.execute("update public.wardrobe_items set notes='n' where id=%s", (item,))
        after = c.execute("select updated_at from public.wardrobe_items where id=%s", (item,)).fetchone()[0]
    assert after > before


def test_storage_policies_restrict_to_owner_folder(db, users):
    a, b = users
    with As(db, a) as c:
        c.execute("insert into storage.objects (bucket_id, name) values ('wardrobe', %s)", (f"{a}/items/i/1.jpg",))
        assert c.execute("select count(*) from storage.objects").fetchone()[0] >= 1
    with As(db, b) as c:
        assert c.execute("select count(*) from storage.objects where name like %s", (f"{a}/%",)).fetchone()[0] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with As(db, b) as c:
            c.execute("insert into storage.objects (bucket_id, name) values ('wardrobe', %s)", (f"{a}/items/i/2.jpg",))
    bucket = db.execute("select public from storage.buckets where id='wardrobe'").fetchone()[0]
    assert bucket is False
