"""Setup and sign-in screens shared by the main app and the companion scanner."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.components import ui
from src.database.base import BackendUnavailable
from src.i18n import _
from src.services import session
from src.services.auth import AuthError, Throttle, sign_in

ROOT = Path(__file__).resolve().parents[2]


def setup_page() -> None:
    ui.header(_("Almost ready"), _("ColorMuse needs its cloud configuration before the first sign-in."), _("Setup"))
    for p in session.settings().problems():
        st.error(p)
    st.markdown(_("Add these keys to **Streamlit Cloud → App settings → Secrets** (or `.streamlit/secrets.toml` / "
                  "`.env` locally). The full walkthrough is in `docs/DEPLOYMENT.md`."))
    st.code(
        'COLORMUSE_BACKEND = "supabase"\nSUPABASE_URL = "https://<project-ref>.supabase.co"\n'
        'SUPABASE_ANON_KEY = "<anon public key>"\nSUPABASE_BUCKET = "wardrobe"\nOWNER_EMAIL = "<owner email>"',
        language="toml",
    )


def login_form(subtitle: str | None = None) -> None:
    ui.header("ColorMuse", subtitle or _("Your personal wardrobe. Your personal stylist."), _("Welcome back"))
    throttle: Throttle = st.session_state.setdefault("cm_throttle", Throttle())
    with st.form("login", border=False):
        email = st.text_input(_("Email"), autocomplete="email")
        password = st.text_input(_("Password"), type="password", autocomplete="current-password")
        submitted = st.form_submit_button(_("Sign in"), type="primary", width="stretch")
    if submitted:
        try:
            with st.spinner(_("Signing in…")):
                sess = sign_in(session.settings(), email, password, throttle)
            session.set_session(sess)
            st.rerun()
        except AuthError as exc:
            st.error(str(exc))
        except BackendUnavailable as exc:
            st.error(f"☁️ {exc}")
    if session.settings().backend == "local":
        st.info(_("Local development mode — data is stored on this computer only."))
    ui.muted(_("This is a private app. There is no public sign-up."))


def login_page() -> None:
    _l, right_top = st.columns([3.4, 1.6])
    with right_top:
        ui.language_switcher("login_lang")
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.image(str(ROOT / "assets" / "illustrations" / "hero.jpg"), width="stretch")
    with right:
        st.markdown("<div style='height:2.5rem'></div>", unsafe_allow_html=True)
        login_form()
