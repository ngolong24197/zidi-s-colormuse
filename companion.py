"""ColorMuse Scan — the phone companion.

A minimal, camera-first app: point at a piece, tap once, see its colors and what
to wear with it, and add it to the wardrobe. It uses the same code, sign-in and
Supabase data as the main app, so anything saved here appears in ColorMuse.

Run locally:  streamlit run companion.py
Deploy:       a second Streamlit Cloud app from the same repo, main file `companion.py`,
              with the same secrets as the main app (see docs/DEPLOYMENT.md).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="ColorMuse Scan",
    page_icon=str(ROOT / "assets" / "icons" / "colormuse-icon.png"),
    layout="centered",
    initial_sidebar_state="collapsed",
)

from src.components import theme, ui  # noqa: E402
from src.components.auth_pages import login_form, setup_page  # noqa: E402
from src.components.scanner import render_scanner  # noqa: E402
from src.i18n import _  # noqa: E402
from src.services import session  # noqa: E402
from src.services.auth import sign_out  # noqa: E402

theme.inject()
session.init_language()


def scanner_page() -> None:
    top_l, top_r = st.columns([1.2, 1], vertical_alignment="center")
    with top_l:
        st.markdown("<span class='cm-eyebrow'>ColorMuse · " + ui.esc(_("Scan")) + "</span>", unsafe_allow_html=True)
    with top_r:
        ui.language_switcher("scan_lang")
    ui.guarded(render_scanner)(full_app=False)
    st.markdown("---")
    if st.button(_("Sign out"), key="scan_sign_out"):
        sign_out(session.current())
        session.set_session(None)
        st.rerun()


def companion_login() -> None:
    ui.language_switcher("scan_login_lang")
    login_form(_("Point, tap, and know what to wear with it."))


def main() -> None:
    if session.settings().problems():
        st.navigation([st.Page(setup_page, title=_("Setup"), icon="⚙️")], position="hidden").run()
        return
    if session.current() is None:
        st.navigation([st.Page(companion_login, title=_("Sign in"), icon="🔒")], position="hidden").run()
        return
    st.navigation([st.Page(scanner_page, title=_("Scan"), icon="📷", default=True)], position="hidden").run()


main()
