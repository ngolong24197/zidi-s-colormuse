"""Single-owner authentication.

* Supabase backend: Supabase Auth email + password. There is no sign-up page;
  the owner account is created once in the Supabase dashboard and public
  sign-ups are disabled there. Only OWNER_EMAIL may sign in (defence in depth).
* Local backend: password from COLORMUSE_LOCAL_PASSWORD (development only).

Brute force is slowed by a per-session lock-out after repeated failures.
"""

from __future__ import annotations

import hmac
import time
from dataclasses import dataclass, field
from typing import Any

from src.config import Settings
from src.database.base import BackendUnavailable, Repository

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60


class AuthError(Exception):
    """Sign-in failed (wrong credentials, not the owner, locked out...)."""


@dataclass
class Session:
    user_id: str
    email: str
    repo: Repository
    client: Any = None  # supabase client (None for local)


@dataclass
class Throttle:
    failures: list[float] = field(default_factory=list)

    def check(self, now: float | None = None) -> None:
        now = now or time.time()
        self.failures = [t for t in self.failures if now - t < LOCKOUT_SECONDS]
        if len(self.failures) >= MAX_ATTEMPTS:
            wait = int(LOCKOUT_SECONDS - (now - self.failures[0])) + 1
            raise AuthError(f"Too many attempts. Please wait {wait} seconds and try again.")

    def fail(self, now: float | None = None) -> None:
        self.failures.append(now or time.time())

    def reset(self) -> None:
        self.failures.clear()


def _create_supabase_client(settings: Settings):
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_anon_key)


def sign_in(settings: Settings, email: str, password: str, throttle: Throttle, client_factory=None) -> Session:
    throttle.check()
    email = (email or "").strip().lower()
    if not email or not password:
        raise AuthError("Please enter your email and password.")
    if settings.owner_email and not hmac.compare_digest(email, settings.owner_email):
        throttle.fail()
        raise AuthError("Incorrect email or password.")

    if settings.backend == "local":
        from src.database.local_repo import LocalRepository

        if not settings.local_password or not hmac.compare_digest(password.encode(), settings.local_password.encode()):
            throttle.fail()
            raise AuthError("Incorrect email or password.")
        throttle.reset()
        return Session("local-owner", email, LocalRepository(settings.local_dir, "local-owner"))

    from src.database.supabase_repo import SupabaseRepository

    factory = client_factory or (lambda: _create_supabase_client(settings))
    try:
        client = factory()
        resp = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        if name in {"ConnectError", "ConnectTimeout", "ReadTimeout", "TimeoutException"}:
            raise BackendUnavailable("Can't reach the sign-in service. Check your connection or restore the "
                                     "Supabase project if it was paused.") from exc
        throttle.fail()
        raise AuthError("Incorrect email or password.") from exc
    user = getattr(resp, "user", None)
    if user is None or (settings.owner_email and (getattr(user, "email", "") or "").lower() != settings.owner_email):
        throttle.fail()
        try:
            client.auth.sign_out()
        except Exception:  # noqa: BLE001
            pass
        raise AuthError("This account is not allowed to use ColorMuse.")
    throttle.reset()
    session = getattr(resp, "session", None)

    def reconnect():
        """New client re-using the current tokens (after network hiccups)."""
        if session is None:
            return None
        try:
            fresh = factory()
            fresh.auth.set_session(session.access_token, session.refresh_token)
            return fresh
        except Exception:  # noqa: BLE001
            return None

    repo = SupabaseRepository(client, str(user.id), settings.bucket, on_reconnect=reconnect)
    return Session(str(user.id), email, repo, client)


def sign_out(session: Session | None) -> None:
    if session and session.client is not None:
        try:
            session.client.auth.sign_out()
        except Exception:  # noqa: BLE001 - signing out locally is enough
            pass


def change_password(session: Session, new_password: str) -> None:
    if len(new_password) < 10:
        raise AuthError("Use at least 10 characters.")
    if session.client is None:
        raise AuthError("In local development mode the password comes from COLORMUSE_LOCAL_PASSWORD.")
    try:
        session.client.auth.update_user({"password": new_password})
    except Exception as exc:  # noqa: BLE001
        raise AuthError(f"Could not change the password: {exc}") from exc
