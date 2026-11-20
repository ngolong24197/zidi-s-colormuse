"""Color Matcher: choose a piece (manually, from a photo or from the wardrobe) and get
explained color recommendations for every category, plus nails and hair."""

from __future__ import annotations

import streamlit as st

from src.components import ui
from src.core.beauty import colors_for_hair, recommend_nails
from src.core.color_convert import normalize_hex, shade_of
from src.core.color_library import COLOR_LIBRARY, color_name
from src.core.harmony import RULE_DESCRIPTIONS, RULES, harmony_palette
from src.core.recommender import (
    RECOMMEND_LABELS,
    MatchRequest,
    recommend,
    wardrobe_matches,
)
from src.models.domain import CATEGORIES, CATEGORY_LABELS, OCCASIONS, PATTERNS, SHADES, STYLES
from src.services import image_processing as ip
from src.services import session
from src.services.styling import outfit_from_match

LIB_NAMES = [c.name for c in COLOR_LIBRARY]
LIB_HEX = {c.name: c.hex for c in COLOR_LIBRARY}


def _photo_input() -> tuple[str, list[str]] | None:
    up = st.file_uploader("Upload a clothing photo", type=sorted(e.strip(".") for e in ip.ALLOWED_EXTENSIONS),
                          key="matcher_photo")
    if not up:
        ui.muted("Tip: photograph the piece flat on a plain background in daylight.")
        return None
    try:
        img = ip.validate_image(up.getvalue(), up.name)
    except ip.ImageValidationError as exc:
        st.error(str(exc))
        return None
    st.markdown("**Select the clothing region** (drag the sliders to crop away background and other items)")
    c1, c2 = st.columns(2)
    lr = c1.slider("Left ↔ right", 0, 100, (8, 92), key="m_lr")
    tb = c2.slider("Top ↕ bottom", 0, 100, (8, 92), key="m_tb")
    box = (lr[0] / 100, tb[0] / 100, max(lr[1], lr[0] + 5) / 100, max(tb[1], tb[0] + 5) / 100)
    reduce_bg = st.toggle("Reduce background interference", value=True, key="m_bg",
                          help="Heuristic (GrabCut + border color removal), not perfect segmentation.")
    pc, rc = st.columns([1, 1.2])
    pc.image(ip.preview_with_box(img, box), width="stretch")
    with rc:
        sig = (up.file_id if hasattr(up, "file_id") else up.name, box, reduce_bg)
        if st.session_state.get("m_sig") != sig:
            with st.spinner("Extracting colors…"):
                st.session_state["m_extract"] = ip.extract_colors(img, box, reduce_background=reduce_bg)
                st.session_state["m_sig"] = sig
        res: ip.ExtractionResult = st.session_state["m_extract"]
        st.markdown("**Detected colors**")
        ui.swatches([(c.hex, f"{c.name} · {int(c.share * 100)}%") for c in res.colors])
        ui.muted(f"Method: {res.method}. Coverage {int(res.mask_coverage * 100)}% of the selected region.")
        primary = st.radio("Main color", [f"{c.name} ({c.hex})" for c in res.colors], key="m_primary_pick")
        p_hex = primary.split("(")[-1].rstrip(")")
        fixed = st.color_picker("Correct the main color if needed", p_hex, key=f"m_fix_{p_hex}")
        secondary = [c.hex for c in res.secondary if c.hex != p_hex][:3]
        return normalize_hex(fixed), secondary


def _wardrobe_input():
    items = session.all_items()
    if not items:
        ui.empty_state("No pieces yet", "Add clothes to My Wardrobe to match them here.")
        return None
    labels = {f"{i.name} — {CATEGORY_LABELS[i.category]}": i for i in items}
    choice = st.selectbox("Choose a piece", list(labels), key="m_item")
    item = labels[choice]
    srcs = session.image_sources([item.thumb_path] if item.thumb_path else [])
    c1, c2 = st.columns([1, 2])
    with c1:
        ui.item_picture(item, srcs.get(item.thumb_path or ""))
    with c2:
        ui.swatches([item.primary_color] + item.secondary_colors)
        st.caption(f"{item.pattern} · {item.shade or shade_of(item.primary_color)}")
    return item


def render_rec_card(rec, key: str) -> None:
    with ui.card():
        left, right = st.columns([1, 2.2])
        with left:
            st.markdown(ui.swatch_html(rec.hex, rec.name), unsafe_allow_html=True)
        with right:
            title = rec.wardrobe_item.name if rec.wardrobe_item else rec.name
            st.markdown(f"**{ui.esc(title)}**<br>{ui.score_badge(rec.score, rec.rule)}", unsafe_allow_html=True)
            st.markdown(f"<span class='cm-muted'>{ui.esc(rec.explanations[0])}</span>", unsafe_allow_html=True)
        with st.expander("Why this works"):
            for e in rec.explanations[1:]:
                st.markdown(f"- {e}")
            ui.breakdown_bars(rec.breakdown)


@ui.guarded
def render() -> None:
    ui.header("Color Matcher", "Tell me about a piece and I'll show you what to wear with it — and why.")
    prefs = session.preferences()

    tab_manual, tab_photo, tab_owned = st.tabs(["Choose manually", "From a photo", "From my wardrobe"])
    base_item = None
    with tab_manual:
        c1, c2 = st.columns(2)
        with c1:
            m_cat = st.selectbox("Category", CATEGORIES, format_func=CATEGORY_LABELS.get, key="m_cat")
            default = st.session_state.pop("matcher_prefill", None) or "#B77E79"
            m_hex = ui.color_input("Primary color", "m_primary", default)
        with c2:
            m_sec_names = st.multiselect("Secondary colors (optional)", LIB_NAMES, max_selections=3, key="m_sec")
            m_pattern = st.selectbox("Pattern", PATTERNS, key="m_pattern")
            auto_shade = shade_of(m_hex)
            m_shade = st.selectbox("Shade", SHADES, index=SHADES.index(auto_shade), key=f"m_shade_{auto_shade}",
                                   help="Detected automatically from the color — correct it if needed.")
    with tab_photo:
        photo = _photo_input()
        p_cat = st.selectbox("What is it?", CATEGORIES, format_func=CATEGORY_LABELS.get, key="p_cat")
        p_pattern = st.selectbox("Pattern ", PATTERNS, key="p_pattern")
    with tab_owned:
        owned_item = _wardrobe_input()

    source = st.radio("Match using", ["Manual choice", "Photo", "Wardrobe piece"], horizontal=True, key="m_source")
    if source == "Photo":
        if not photo:
            st.info("Upload a photo in the “From a photo” tab first.")
            return
        req_args = dict(base_hex=photo[0], base_category=p_cat, secondary=photo[1], pattern=p_pattern)
    elif source == "Wardrobe piece":
        if not owned_item:
            st.info("Choose a piece in the “From my wardrobe” tab first.")
            return
        base_item = owned_item
        req_args = dict(base_hex=owned_item.primary_color, base_category=owned_item.category,
                        secondary=owned_item.secondary_colors, pattern=owned_item.pattern, shade=owned_item.shade)
    else:
        req_args = dict(base_hex=m_hex, base_category=m_cat, secondary=[LIB_HEX[n] for n in m_sec_names],
                        pattern=m_pattern, shade=m_shade)

    with ui.card():
        c1, c2, c3 = st.columns(3)
        occasion = c1.selectbox("Occasion", [None, *OCCASIONS], format_func=lambda x: "Any occasion" if x is None else x.title(), key="m_occ")
        style = c2.selectbox("Style", [None, *STYLES], format_func=lambda x: "Any style" if x is None else x.title(), key="m_style")
        shade_filter = c3.selectbox("Suggested shades", [None, *SHADES], format_func=lambda x: "Any depth" if x is None else f"Only {x}", key="m_shadef")

    req = MatchRequest(**req_args, occasion=occasion, style=style, shade_filter=shade_filter, prefs=prefs)
    results = recommend(req)
    items = session.all_items()
    owned = {cat: wardrobe_matches(req, items, cat, exclude_id=base_item.id if base_item else None) for cat in results}

    st.markdown(f"### Matching {color_name(req.base_hex)} {CATEGORY_LABELS.get(req.base_category, '').lower()}")
    ui.swatches([(req.base_hex, color_name(req.base_hex))] + [(s, None) for s in req.secondary])

    a, b = st.columns(2)
    if a.button("👗 Build an outfit from these matches", type="primary", width="stretch"):
        session.open_in_studio(outfit_from_match(req, results, owned, base_item, prefs))
        st.switch_page("pages/outfit_studio.py")
    if b.button("Save to recommendation history", width="stretch"):
        session.repo().add_history(
            "color_match",
            {"base_hex": req.base_hex, "category": req.base_category, "occasion": occasion, "style": style},
            [{"category": c, "hex": r.hex, "name": r.name, "score": r.score} for c, recs in results.items() for r in recs[:2]],
        )
        st.toast("Saved to your history")

    with st.expander("🎨 Harmony palettes (color theory)", expanded=False):
        for rule in RULES:
            pal = harmony_palette(req.base_hex, rule)
            st.markdown(f"**{rule.title()}** — <span class='cm-muted'>{RULE_DESCRIPTIONS[rule]}</span>", unsafe_allow_html=True)
            ui.swatches([(req.base_hex, "Your piece")] + [(p.hex, p.name) for p in pal])

    for cat, recs in results.items():
        st.markdown(f"#### {RECOMMEND_LABELS[cat]}")
        cols = st.columns(2)
        for n, rec in enumerate(recs):
            with cols[n % 2]:
                render_rec_card(rec, f"{cat}_{n}")
        if owned.get(cat):
            st.markdown("<span class='cm-eyebrow'>Already in your wardrobe</span>", unsafe_allow_html=True)
            ocols = st.columns(3)
            for n, rec in enumerate(owned[cat]):
                with ocols[n % 3]:
                    render_rec_card(rec, f"own_{cat}_{n}")

    st.markdown("### Beauty: nails & hair")
    nl, hr = st.columns(2)
    with nl, ui.card():
        st.markdown("**Nail colors for this piece**")
        nails = recommend_nails(base_colors=[(req.base_category, req.base_hex)], occasion=occasion, style=style,
                                prefs=prefs, skin_tone=prefs.skin_tone)
        ui.swatches([(n.hex, f"{n.name} · {n.score:.0f}") for n in nails], show_hex=False)
        for n in nails[:3]:
            st.markdown(f"- **{n.name}** — {n.explanations[0] if n.explanations else ''}")
    with hr, ui.card():
        st.markdown(f"**Colors that flatter your {color_name(prefs.hair_color).lower()} hair**")
        hair = colors_for_hair(prefs.hair_color, prefs=prefs)
        ui.swatches([(h.hex, h.name) for h in hair], show_hex=False)
        ui.muted("Worn near the face (tops, scarves, dresses). Set your hair color in Settings → Beauty.")


render()
