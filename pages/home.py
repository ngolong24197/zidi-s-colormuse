"""Home: welcome, quick styling, recent looks & pieces, favorites, inspiration."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.components import ui
from src.components.looks import mannequin_html
from src.core.harmony import harmony_palette
from src.i18n import N_, _, label
from src.services import session

ROOT = Path(__file__).resolve().parents[1]

INSPIRATION = [
    ("office", N_("Polished office"), "occasion-office.jpg", N_("Muted, tailored neutrals.")),
    ("date night", N_("Date night"), "occasion-date.jpg", N_("Rich, romantic depth.")),
    ("beach", N_("Beach days"), "occasion-beach.jpg", N_("Light, sunny and easy.")),
    ("wedding guest", N_("Wedding guest"), "occasion-wedding.jpg", N_("Soft pastels & jewel tones.")),
]


def go(page: str, **state) -> None:
    st.session_state.update(state)
    st.switch_page(page)


@ui.guarded
def render() -> None:
    prefs = session.preferences()
    name = prefs.display_name or _("beautiful")
    hero_l, hero_r = st.columns([1.1, 1], gap="large")
    with hero_l:
        ui.header(_("Hello, {name}", name=name),
                  _("Your personal wardrobe. Your personal stylist. What are we wearing today?"), "ColorMuse")
        a, b = st.columns(2)
        if a.button("✨ " + _("Match a color"), width="stretch", type="primary"):
            go("pages/color_matcher.py")
        if b.button("👗 " + _("Add a piece"), width="stretch"):
            go("pages/wardrobe.py", wardrobe_mode="add")
        c, d = st.columns(2)
        if c.button("📅 " + _("Plan an outfit"), width="stretch"):
            go("pages/occasion_planner.py")
        if d.button("🎨 " + _("Outfit studio"), width="stretch"):
            go("pages/outfit_studio.py")

        with ui.card():
            st.markdown("##### " + _("Quick styling"))
            qc = st.color_picker(_("Pick a color you want to wear"), "#B77E79", key="home_quick")
            for rule in ("complementary", "analogous", "neutral"):
                pal = harmony_palette(qc, rule)
                st.markdown(f"<span class='cm-rule'>{ui.esc(label('rule', rule))}</span>", unsafe_allow_html=True)
                ui.swatches([(p.hex, label("color", p.name)) for p in pal[:4]], show_hex=False)
            if st.button(_("See full recommendations →"), key="home_full"):
                go("pages/color_matcher.py", matcher_prefill=qc)
    with hero_r:
        st.image(str(ROOT / "assets" / "illustrations" / "hero.jpg"), width="stretch")

    repo = session.repo()
    recent_outfits = session.cached("home:recent_outfits", lambda: repo.list_outfits(limit=3)[0])
    fav_outfits = session.cached("home:fav_outfits", lambda: repo.list_outfits(favorite=True, limit=3)[0])
    items = session.all_items()

    st.markdown("### " + _("Recent outfits"))
    if recent_outfits:
        cols = st.columns(3)
        for col, o in zip(cols, recent_outfits):
            with col, ui.card():
                st.markdown(mannequin_html(o, 300), unsafe_allow_html=True)
                st.markdown(f"**{ui.esc(o.name)}**")
                if st.button(_("Open in studio"), key=f"home_open_{o.id}", width="stretch"):
                    session.open_in_studio(o.copy())
                    st.switch_page("pages/outfit_studio.py")
    else:
        ui.empty_state(_("No looks yet"), _("Create one in the Outfit Studio or let the Occasion Planner suggest some."))

    st.markdown("### " + _("Recently added to your wardrobe"))
    if items:
        recent = items[:6]
        srcs = session.image_sources([i.thumb_path for i in recent if i.thumb_path])
        cols = st.columns(6)
        for col, it in zip(cols, recent):
            with col:
                ui.item_picture(it, srcs.get(it.thumb_path or ""))
                st.caption(it.name)
    else:
        ui.empty_state(_("Your wardrobe is empty"), _("Add your first piece — a photo or just its color."))

    if fav_outfits:
        st.markdown("### " + _("Favorite combinations"))
        cols = st.columns(3)
        for col, o in zip(cols, fav_outfits):
            with col, ui.card():
                st.markdown(f"**♥ {ui.esc(o.name)}**")
                ui.chips(o.colors[:6])

    st.markdown("### " + _("Outfit inspiration"))
    cols = st.columns(4)
    for col, (occ, title, img, blurb) in zip(cols, INSPIRATION):
        with col, ui.card():
            st.image(str(ROOT / "assets" / "illustrations" / img), width="stretch")
            st.markdown(f"**{ui.esc(_(title))}**  \n<span class='cm-muted'>{ui.esc(_(blurb))}</span>",
                        unsafe_allow_html=True)
            if st.button(_("Plan this look"), key=f"insp_{occ}", width="stretch"):
                go("pages/occasion_planner.py", planner_occasion=occ)


render()
