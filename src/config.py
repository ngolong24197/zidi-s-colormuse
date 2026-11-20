"""Configuration from Streamlit secrets (cloud) or environment / .env (local)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_KEYS = ("COLORMUSE_BACKEND", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_BUCKET", "OWNER_EMAIL",
         "COLORMUSE_LOCAL_PASSWORD", "COLORMUSE_LOCAL_DIR")


def _load_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env parser (KEY=VALUE lines) so we don't need python-dotenv."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _secrets() -> dict[str, str]:
    try:
        import streamlit as st

        return {k: str(st.secrets[k]) for k in _KEYS if k in st.secrets}
    except Exception:  # noqa: BLE001 - no secrets.toml is normal locally
        return {}


@dataclass(frozen=True)
class Settings:
    backend: str
    supabase_url: str
    supabase_anon_key: str
    bucket: str
    owner_email: str
    local_password: str
    local_dir: Path

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    def problems(self) -> list[str]:
        """Human-readable configuration problems (empty when ready)."""
        issues = []
        if self.backend == "supabase":
            if not self.supabase_url:
                issues.append("SUPABASE_URL is not set.")
            if not self.supabase_anon_key:
                issues.append("SUPABASE_ANON_KEY is not set.")
            if self.supabase_anon_key and _looks_like_service_key(self.supabase_anon_key):
                issues.append("SUPABASE_ANON_KEY looks like a service-role key. Use the anon/publishable key only.")
            if not self.owner_email:
                issues.append("OWNER_EMAIL is not set.")
        elif self.backend == "local":
            if not self.local_password:
                issues.append("COLORMUSE_LOCAL_PASSWORD is not set.")
        else:
            issues.append(f"Unknown COLORMUSE_BACKEND '{self.backend}' (use 'supabase' or 'local').")
        return issues


def _looks_like_service_key(key: str) -> bool:
    if key.startswith("sb_secret_"):
        return True
    parts = key.split(".")
    if len(parts) == 3:
        import base64
        import json

        try:
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            return payload.get("role") == "service_role"
        except Exception:  # noqa: BLE001
            return False
    return False


def load_settings(env: dict[str, str] | None = None) -> Settings:
    values: dict[str, str] = {}
    values.update(_load_dotenv(ROOT / ".env"))
    values.update({k: v for k, v in os.environ.items() if k in _KEYS})
    values.update(_secrets())
    if env is not None:
        values = dict(env)
    backend = values.get("COLORMUSE_BACKEND", "").strip().lower()
    if not backend:
        backend = "supabase" if values.get("SUPABASE_URL") else "local" if values.get("COLORMUSE_LOCAL_PASSWORD") else "supabase"
    local_dir = Path(values.get("COLORMUSE_LOCAL_DIR") or ".colormuse_local")
    if not local_dir.is_absolute():
        local_dir = ROOT / local_dir
    return Settings(
        backend=backend,
        supabase_url=values.get("SUPABASE_URL", "").strip(),
        supabase_anon_key=values.get("SUPABASE_ANON_KEY", "").strip(),
        bucket=values.get("SUPABASE_BUCKET", "wardrobe").strip() or "wardrobe",
        owner_email=values.get("OWNER_EMAIL", "").strip().lower(),
        local_password=values.get("COLORMUSE_LOCAL_PASSWORD", ""),
        local_dir=local_dir,
    )
