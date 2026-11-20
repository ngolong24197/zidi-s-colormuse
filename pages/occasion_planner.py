"""Occasion Planner: complete outfits generated from pieces already owned."""

from __future__ import annotations

import streamlit as st

from src.components import ui
from src.components.looks import mannequin_html, palette_list
from src.core.outfit_engine import OutfitContext, generate_outfits
from src.models.domain import OCCASIONS, SEASONS, STYLES
from src.services import session

OCCASION_ICONS = {
    "casual": "☕", "office": "💼", "date night": "🌹", "party": "🥂", "wedding guest": "💐", "travel": "✈️",
    "beach": "🌊", "formal": "✨", "dinner": "🍷", "interview": "🤝", "daily errands": "🛍️",
}


def _missing(items) -> list[str]:
    slots = {i.slot for i in items}
    out = []
    if "dress" not in slots and not ({"top", "bottom"} <= slots):
        out.append("a top and a bottom (or a dress)")
    if "shoes" not in slots:
        out.append("shoes")
    return out


@ui.guarded
def render() -> None:
    ui.header("Occasion Planner", "Pick the moment — I'll build complete looks from what you already own.")
    prefs = session.preferences()
    preset = st.session_state.pop("planner_occasion", None)
    if preset in OCCASIONS:
        st.session_state["plan_occ"] = preset
    occasion = st.pills("Occasion", OCCASIONS, format_func=lambda o: f"{OCCASION_ICONS[o]} {o.title()}",
                        key="plan_occ", default=None if "plan_occ" in st.session_state else (prefs.occasion_preferences[0] if prefs.occasion_preferences else "casual"))
    c1, c2, c3 = st.columns(3)
    style_default = prefs.preferred_styles[0] if prefs.preferred_styles else None
    style_opts = [None, *STYLES]
    style = c1.selectbox("Style", style_opts, index=style_opts.index(style_default), format_func=lambda x: "Any style" if x is None else x.title(), key="plan_style")
    season = c2.selectbox("Season", [None, *SEASONS], format_func=lambda x: "Any season" if x is None else x.title(), key="plan_season")
    count = c3.slider("How many looks", 2, 8, 4, key="plan_count")

    items = session.all_items()
    missing = _missing(items)
    if missing:
        ui.empty_state("I need a few more pieces", "Add " + " and ".join(missing) + " to My Wardrobe to plan outfits.")
        if st.button("Go to My Wardrobe"):
            st.session_state["wardrobe_mode"] = "add"
            st.switch_page("pages/wardrobe.py")
        return
    if not occasion:
        st.info("Choose an occasion above.")
        return

    ctx = OutfitContext(occasion, style, season, prefs)
    key = f"plan:{occasion}:{style}:{season}:{count}"
    with st.spinner("Styling your looks…"):
        looks = session.cached(key, lambda: generate_outfits(items, ctx, limit=count))
    if not looks:
        ui.empty_state("No complete looks", "Try another season, or add more pieces for this occasion.")
        return
    st.caption(f"{len(looks)} looks for {occasion} · ranked by score · everything is from your wardrobe")
    repo = session.repo()
    cols = st.columns(2)
    for n, g in enumerate(looks):
        with cols[n % 2], ui.card():
            st.markdown(f"**{ui.esc(g.outfit.name)}** &nbsp; {ui.score_badge(g.score)}", unsafe_allow_html=True)
            left, right = st.columns([1, 1.2])
            with left:
                st.markdown(mannequin_html(g.outfit, 380), unsafe_allow_html=True)
            with right:
                palette_list(g.outfit)
                with st.expander("Why it works"):
                    ui.breakdown_bars(g.breakdown)
                    for note in g.breakdown.explanations:
                        st.markdown(f"- {note}")
            b1, b2 = st.columns(2)
            if b1.button("Open in studio", key=f"plan_open_{n}", width="stretch"):
                session.open_in_studio(g.outfit.copy(new_identity=True))
                st.switch_page("pages/outfit_studio.py")
            if b2.button("Save look", key=f"plan_save_{n}", type="primary", width="stretch"):
                repo.save_outfit(g.outfit.copy(new_identity=True))
                session.invalidate()
                st.toast(f"Saved “{g.outfit.name}”")


render()
