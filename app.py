"""ColorMuse — your personal wardrobe, your personal stylist.

Entry point for Streamlit (local: `streamlit run app.py`; cloud: Streamlit
Community Cloud main file). It only wires configuration, language, sign-in
and navigation; every feature lives in pages/ and src/.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="ColorMuse",
    page_icon=str(ROOT / "assets" / "icons" / "colormuse-icon.png"),
    layout="wide",
    initial_sidebar_state="collapsed",
)

from src.components import theme, ui  # noqa: E402
from src.database.base import BackendUnavailable  # noqa: E402
from src.i18n import _  # noqa: E402
from src.services import session  # noqa: E402
from src.services.auth import AuthError, Throttle, sign_in  # noqa: E402

theme.inject()
session.init_language()


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


def login_page() -> None:
    _l, right_top = st.columns([4, 1])
    with right_top:
        ui.language_switcher("login_lang")
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.image(str(ROOT / "assets" / "illustrations" / "hero.jpg"), width="stretch")
    with right:
        st.markdown("<div style='height:2.5rem'></div>", unsafe_allow_html=True)
        ui.header("ColorMuse", _("Your personal wardrobe. Your personal stylist."), _("Welcome back"))
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


def main() -> None:
    if session.settings().problems():
        st.navigation([st.Page(setup_page, title=_("Setup"), icon="⚙️")], position="hidden").run()
        return
    if session.current() is None:
        st.navigation([st.Page(login_page, title=_("Sign in"), icon="🔒")], position="hidden").run()
        return
    pages = [
        st.Page("pages/home.py", title=_("Home"), icon=":material/home:", default=True),
        st.Page("pages/color_matcher.py", title=_("Color Matcher"), icon=":material/palette:"),
        st.Page("pages/wardrobe.py", title=_("My Wardrobe"), icon=":material/checkroom:"),
        st.Page("pages/outfit_studio.py", title=_("Outfit Studio"), icon=":material/styler:"),
        st.Page("pages/occasion_planner.py", title=_("Occasions"), icon=":material/event:"),
        st.Page("pages/saved_looks.py", title=_("Saved Looks"), icon=":material/favorite:"),
        st.Page("pages/settings.py", title=_("Settings"), icon=":material/settings:"),
    ]
    nav = st.navigation(pages, position="top")
    top_l, top_r = st.columns([5, 1])
    with top_l:
        if session.settings().backend == "local":
            st.caption("🧪 " + _("Local development mode — data stays on this computer (not for the hosted app)."))
    with top_r:
        ui.language_switcher("nav_lang")
    nav.run()


main()
