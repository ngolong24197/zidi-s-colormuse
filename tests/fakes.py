"""In-memory stand-in for the supabase-py client (PostgREST + Storage + Auth subset).

Implements exactly the query-builder calls SupabaseRepository uses, and
emulates Row Level Security: every row is visible/writable only when its
owner_id equals the signed-in user's id.
"""

from __future__ import annotations

import copy
import fnmatch
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class FakeAPIError(Exception):
    def __init__(self, message: str, code: str | int = "400", status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


class FakeConnectError(Exception):
    """Named like httpx.ConnectError so the repository classifies it as transient."""


FakeConnectError.__name__ = "ConnectError"


@dataclass
class Resp:
    data: Any
    count: int | None = None


UNIQUE = {
    "user_preferences": [("owner_id",)],
    "outfit_items": [("outfit_id", "slot")],
    "collection_outfits": [("collection_id", "outfit_id")],
}
CASCADE = {  # parent table -> [(child table, fk column, action)]
    "wardrobe_items": [("clothing_images", "wardrobe_item_id", "cascade"), ("outfit_items", "wardrobe_item_id", "set null")],
    "outfits": [("outfit_items", "outfit_id", "cascade"), ("collection_outfits", "outfit_id", "cascade")],
    "outfit_collections": [("collection_outfits", "collection_id", "cascade")],
}
PK = {"user_preferences": "owner_id"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Query:
    def __init__(self, db: "FakeDB", table: str):
        self.db, self.table = db, table
        self.op = "select"
        self.filters: list = []
        self.orders: list[tuple[str, bool]] = []
        self.rng: tuple[int, int] | None = None
        self.lim: int | None = None
        self.payload: Any = None
        self.count_mode: str | None = None
        self.on_conflict: str | None = None

    # ---- builders
    def select(self, cols="*", count=None):
        self.op, self.count_mode = "select", count
        return self

    def insert(self, rows):
        self.op, self.payload = "insert", rows
        return self

    def upsert(self, rows, on_conflict=None):
        self.op, self.payload, self.on_conflict = "upsert", rows, on_conflict
        return self

    def update(self, values):
        self.op, self.payload = "update", values
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters.append(lambda r, c=col, v=val: r.get(c) == v)
        return self

    def in_(self, col, vals):
        vals = list(vals)
        self.filters.append(lambda r, c=col: r.get(c) in vals)
        return self

    def or_(self, expr: str):
        parts = re.split(r",(?![^{]*\})", expr)
        preds = []
        for part in parts:
            col, op, val = part.split(".", 2)
            if op == "ilike":
                pat = val.replace("*", "%").lower()
                rx = "^" + re.escape(pat).replace("%", ".*") + "$"
                preds.append(lambda r, c=col, rx=rx: bool(re.match(rx, str(r.get(c) or "").lower())))
            elif op == "cs":
                want = val.strip("{}").split(",") if val.strip("{}") else []
                preds.append(lambda r, c=col, w=want: all(x in (r.get(c) or []) for x in w))
            elif op == "eq" and val == "{}":
                preds.append(lambda r, c=col: not r.get(c))
            else:
                raise NotImplementedError(part)
        self.filters.append(lambda r: any(p(r) for p in preds))
        return self

    def order(self, col, desc=False):
        self.orders.append((col, desc))
        return self

    def range(self, a, b):
        self.rng = (a, b)
        return self

    def limit(self, n):
        self.lim = n
        return self

    # ---- execution
    def _visible(self) -> list[dict]:
        uid = self.db.require_user()
        rows = self.db.tables.setdefault(self.table, [])
        if self.table == "colors":
            return rows
        return [r for r in rows if r.get("owner_id") == uid]

    def execute(self) -> Resp:
        self.db.maybe_fail()
        uid = self.db.require_user()
        if self.op == "select":
            rows = [r for r in self._visible() if all(f(r) for f in self.filters)]
            for col, desc in reversed(self.orders):
                rows.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            total = len(rows)
            if self.rng:
                rows = rows[self.rng[0]: self.rng[1] + 1]
            if self.lim is not None:
                rows = rows[: self.lim]
            return Resp(copy.deepcopy(rows), total if self.count_mode else None)
        if self.op in ("insert", "upsert"):
            if self.table == "colors":
                raise FakeAPIError("permission denied for table colors", "42501")
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for row in rows:
                row = copy.deepcopy(row)
                row.setdefault("owner_id", uid)
                if row["owner_id"] != uid:
                    raise FakeAPIError("new row violates row-level security policy", "42501")
                self._check_parents(row, uid)
                pk = PK.get(self.table, "id")
                if pk == "id":
                    row.setdefault("id", str(uuid.uuid4()))
                table = self.db.tables.setdefault(self.table, [])
                keys = [tuple(self.on_conflict.split(","))] if self.on_conflict else [(pk,)]
                existing = None
                for key in keys + UNIQUE.get(self.table, []):
                    if all(k in row for k in key):
                        existing = next((r for r in table if all(r.get(k) == row[k] for k in key)), None)
                        if existing:
                            break
                if existing is not None:
                    if self.op == "insert":
                        raise FakeAPIError("duplicate key value violates unique constraint", "23505")
                    if existing.get("owner_id") != uid:
                        raise FakeAPIError("new row violates row-level security policy", "42501")
                    existing.update(row)
                    out.append(copy.deepcopy(existing))
                else:
                    row.setdefault("created_at", _now())
                    if self.table in ("wardrobe_items", "outfits", "user_preferences"):
                        row.setdefault("updated_at", _now())
                    table.append(row)
                    out.append(copy.deepcopy(row))
            return Resp(out)
        if self.op == "update":
            rows = [r for r in self._visible() if all(f(r) for f in self.filters)]
            for r in rows:
                r.update(self.payload)
            return Resp(copy.deepcopy(rows))
        if self.op == "delete":
            rows = [r for r in self._visible() if all(f(r) for f in self.filters)]
            for r in rows:
                self.db.delete_row(self.table, r)
            return Resp(copy.deepcopy(rows))
        raise NotImplementedError(self.op)

    def _check_parents(self, row: dict, uid: str) -> None:
        checks = {"outfit_items": [("outfit_id", "outfits")], "clothing_images": [("wardrobe_item_id", "wardrobe_items")],
                  "collection_outfits": [("collection_id", "outfit_collections"), ("outfit_id", "outfits")]}
        for col, parent in checks.get(self.table, []):
            if not any(p["id"] == row.get(col) and p["owner_id"] == uid for p in self.db.tables.get(parent, [])):
                raise FakeAPIError("new row violates row-level security policy", "42501")


class FakeBucket:
    def __init__(self, db: "FakeDB", name: str):
        self.db, self.name = db, name

    def _check(self, path: str) -> None:
        uid = self.db.require_user()
        if path.split("/", 1)[0] != uid:
            raise FakeAPIError("new row violates row-level security policy", "403", 403)

    def upload(self, path, data, file_options=None):
        self.db.maybe_fail()
        self._check(path)
        files = self.db.files.setdefault(self.name, {})
        if path in files and str((file_options or {}).get("upsert", "false")).lower() != "true":
            raise FakeAPIError("The resource already exists", "409", 409)
        files[path] = bytes(data)
        return {"path": path}

    def download(self, path):
        self.db.maybe_fail()
        self._check(path)
        files = self.db.files.setdefault(self.name, {})
        if path not in files:
            raise FakeAPIError("Object not found", "404", 404)
        return files[path]

    def remove(self, paths):
        self.db.maybe_fail()
        for p in paths:
            self._check(p)
            self.db.files.setdefault(self.name, {}).pop(p, None)
        return [{"name": p} for p in paths]

    def create_signed_urls(self, paths, expires_in):
        for p in paths:
            self._check(p)
        return [{"path": p, "signedURL": f"https://fake.supabase.co/storage/v1/sign/{self.name}/{p}?token=t"} for p in paths]

    def list(self, prefix="", options=None):
        self._check(prefix + "/x")
        files = self.db.files.setdefault(self.name, {})
        entries: dict[str, dict] = {}
        for p in files:
            if not p.startswith(prefix + "/"):
                continue
            rest = p[len(prefix) + 1:]
            head = rest.split("/", 1)[0]
            entries[head] = {"name": head, "id": "file" if "/" not in rest else None}
        return list(entries.values())


class FakeStorage:
    def __init__(self, db):
        self.db = db

    def from_(self, name):
        return FakeBucket(self.db, name)


@dataclass
class FakeUser:
    id: str
    email: str


@dataclass
class FakeSession:
    access_token: str
    refresh_token: str


@dataclass
class FakeAuthResponse:
    user: FakeUser | None
    session: FakeSession | None


class FakeAuth:
    def __init__(self, db: "FakeDB", client: "FakeClient"):
        self.db, self.client = db, client
        self.refreshes = 0

    def sign_in_with_password(self, creds):
        user = self.db.users.get(creds["email"].lower())
        if not user or user[1] != creds["password"]:
            raise FakeAPIError("Invalid login credentials", "400", 400)
        self.client.user = FakeUser(user[0], creds["email"].lower())
        return FakeAuthResponse(self.client.user, FakeSession("access", "refresh"))

    def sign_out(self):
        self.client.user = None

    def refresh_session(self):
        self.refreshes += 1
        self.db.expired = False
        return FakeAuthResponse(self.client.user, FakeSession("access2", "refresh2"))

    def set_session(self, access, refresh):
        return None

    def update_user(self, attrs):
        if self.client.user is None:
            raise FakeAPIError("not signed in", "401", 401)
        email = self.client.user.email
        uid, _ = self.db.users[email]
        self.db.users[email] = (uid, attrs["password"])


class FakeDB:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.files: dict[str, dict[str, bytes]] = {}
        self.users: dict[str, tuple[str, str]] = {}
        self.fail_next = 0  # number of upcoming calls that raise a transient error
        self.expired = False
        self.current: FakeClient | None = None

    def add_user(self, email: str, password: str) -> str:
        uid = str(uuid.uuid4())
        self.users[email.lower()] = (uid, password)
        return uid

    def maybe_fail(self):
        if self.fail_next > 0:
            self.fail_next -= 1
            raise FakeConnectError("connection refused")
        if self.expired:
            raise FakeAPIError("JWT expired", "PGRST301", 401)

    def require_user(self) -> str:
        if self.current is None or self.current.user is None:
            raise FakeAPIError("JWT missing", "401", 401)
        return self.current.user.id

    def delete_row(self, table: str, row: dict) -> None:
        self.tables[table].remove(row)
        for child, col, action in CASCADE.get(table, []):
            for r in list(self.tables.get(child, [])):
                if r.get(col) == row.get("id"):
                    if action == "cascade":
                        self.delete_row(child, r)
                    else:
                        r[col] = None


class FakeClient:
    """One client = one signed-in browser session."""

    def __init__(self, db: FakeDB, user: FakeUser | None = None):
        self.db = db
        self.user = user
        self.auth = FakeAuth(db, self)
        self.storage = FakeStorage(db)

    def table(self, name):
        self.db.current = self
        return Query(self.db, name)

    def __getattribute__(self, name):
        if name in ("table", "storage"):
            object.__getattribute__(self, "db").current = self
        return object.__getattribute__(self, name)


def seeded_colors(db: FakeDB) -> None:
    from src.core.color_library import COLOR_LIBRARY

    db.tables["colors"] = [{"id": str(uuid.uuid4()), "name": c.name, "hex": c.hex, "family": c.family,
                            "is_neutral": c.is_neutral} for c in COLOR_LIBRARY]


__all__ = ["FakeDB", "FakeClient", "FakeUser", "FakeAPIError", "FakeConnectError", "seeded_colors", "fnmatch"]
