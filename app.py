"""ColorMuse — your personal wardrobe, your personal stylist.

Entry point for Streamlit (local: `streamlit run app.py`; cloud: Streamlit
Community Cloud main file). It only wires configuration, sign-in and
navigation; every feature lives in pages/ and src/.
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
from src.services import session  # noqa: E402
from src.services.auth import AuthError, Throttle, sign_in  # noqa: E402

theme.inject()


def setup_page() -> None:
    ui.header("Almost ready", "ColorMuse needs its cloud configuration before the first sign-in.", "Setup")
    for p in session.settings().problems():
        st.error(p)
    st.markdown(
        "Add these keys to **Streamlit Cloud → App settings → Secrets** (or `.streamlit/secrets.toml` / `.env` "
        "locally). The full walkthrough is in `docs/DEPLOYMENT.md`."
    )
    st.code(
        'COLORMUSE_BACKEND = "supabase"\nSUPABASE_URL = "https://<project-ref>.supabase.co"\n'
        'SUPABASE_ANON_KEY = "<anon public key>"\nSUPABASE_BUCKET = "wardrobe"\nOWNER_EMAIL = "<owner email>"',
        language="toml",
    )


def login_page() -> None:
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.image(str(ROOT / "assets" / "illustrations" / "hero.jpg"), width="stretch")
    with right:
        st.markdown("<div style='height:2.5rem'></div>", unsafe_allow_html=True)
        ui.header("ColorMuse", "Your personal wardrobe. Your personal stylist.", "Welcome back")
        throttle: Throttle = st.session_state.setdefault("cm_throttle", Throttle())
        with st.form("login", border=False):
            email = st.text_input("Email", autocomplete="email")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        if submitted:
            try:
                with st.spinner("Signing in…"):
                    sess = sign_in(session.settings(), email, password, throttle)
                session.set_session(sess)
                st.rerun()
            except AuthError as exc:
                st.error(str(exc))
            except BackendUnavailable as exc:
                st.error(f"☁️ {exc}")
        if session.settings().backend == "local":
            st.info("Local development mode — data is stored on this computer only.")
        ui.muted("This is a private app. There is no public sign-up.")


def main() -> None:
    if session.settings().problems():
        st.navigation([st.Page(setup_page, title="Setup", icon="⚙️")], position="hidden").run()
        return
    if session.current() is None:
        st.navigation([st.Page(login_page, title="Sign in", icon="🔒")], position="hidden").run()
        return
    pages = [
        st.Page("pages/home.py", title="Home", icon=":material/home:", default=True),
        st.Page("pages/color_matcher.py", title="Color Matcher", icon=":material/palette:"),
        st.Page("pages/wardrobe.py", title="My Wardrobe", icon=":material/checkroom:"),
        st.Page("pages/outfit_studio.py", title="Outfit Studio", icon=":material/styler:"),
        st.Page("pages/occasion_planner.py", title="Occasions", icon=":material/event:"),
        st.Page("pages/saved_looks.py", title="Saved Looks", icon=":material/favorite:"),
        st.Page("pages/settings.py", title="Settings", icon=":material/settings:"),
    ]
    nav = st.navigation(pages, position="top")
    if session.settings().backend == "local":
        st.caption("🧪 Local development mode — data stays on this computer (not for the hosted app).")
    nav.run()


main()
