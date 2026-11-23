"""ColorMuse — your personal wardrobe, your personal stylist.

Entry point for Streamlit (local: `streamlit run app.py`; cloud: Streamlit
Community Cloud main file). It only wires configuration, language, sign-in
and navigation; every feature lives in pages/ and src/.
The phone-first camera companion is `companion.py` (same code, same data).
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
from src.components.auth_pages import login_page, setup_page  # noqa: E402
from src.i18n import _  # noqa: E402
from src.services import session  # noqa: E402

theme.inject()
session.init_language()


def main() -> None:
    if session.settings().problems():
        st.navigation([st.Page(setup_page, title=_("Setup"), icon="⚙️")], position="hidden").run()
        return
    if session.current() is None:
        st.navigation([st.Page(login_page, title=_("Sign in"), icon="🔒")], position="hidden").run()
        return
    pages = [
        st.Page("pages/home.py", title=_("Home"), icon=":material/home:", default=True),
        st.Page("pages/quick_scan.py", title=_("Scan"), icon=":material/photo_camera:", url_path="scan"),
        st.Page("pages/color_matcher.py", title=_("Color Matcher"), icon=":material/palette:"),
        st.Page("pages/wardrobe.py", title=_("My Wardrobe"), icon=":material/checkroom:"),
        st.Page("pages/outfit_studio.py", title=_("Outfit Studio"), icon=":material/styler:"),
        st.Page("pages/occasion_planner.py", title=_("Occasions"), icon=":material/event:"),
        st.Page("pages/saved_looks.py", title=_("Saved Looks"), icon=":material/favorite:"),
        st.Page("pages/settings.py", title=_("Settings"), icon=":material/settings:"),
    ]
    nav = st.navigation(pages, position="top")
    top_l, top_r = st.columns([3.4, 1.6], vertical_alignment="center")
    with top_l:
        if session.settings().backend == "local":
            st.caption("🧪 " + _("Local development mode — data stays on this computer (not for the hosted app)."))
    with top_r:
        ui.language_switcher("nav_lang")
    nav.run()


main()
