"""Camera scanner UI shared by the Scan page (main app) and the companion app.

Flow: pick what it is → point the camera → tap the shutter → colors + quick
recommendations + "do you already own this?" → "Add to my wardrobe?" (pre-filled).
"""

from __future__ import annotations

import hashlib

import streamlit as st

from src.components import ui
from src.i18n import _, cname, format_func, get_language, label
from src.models.domain import CATEGORIES, PATTERNS
from src.services import image_processing as ip
from src.services import scan, session


def _reset_camera() -> None:
    st.session_state["scan_rev"] = st.session_state.get("scan_rev", 0) + 1
    for k in [k for k in st.session_state if k.startswith(("scan_result", "scan_saved", "scan_dismissed", "scan_fix"))]:
        del st.session_state[k]


def _analysis(data: bytes, category: str, override: str | None) -> scan.ScanResult:
    key = "scan_result:" + hashlib.sha1(data).hexdigest()[:16] + f":{category}:{override}:{get_language()}"
    if key not in st.session_state:
        for k in [k for k in st.session_state if k.startswith("scan_result:")]:
            del st.session_state[k]  # keep only the current scan in memory
        st.session_state[key] = scan.analyze(
            data, category, prefs=session.preferences(), wardrobe=session.all_items(), main_hex=override)
    return st.session_state[key]


def render_scanner(full_app: bool = True) -> None:
    rev = st.session_state.get("scan_rev", 0)
    ui.header(_("Scan a piece"),
              _("Point your camera at a piece and tap the shutter — I'll read its colors and tell you what goes with it."))

    category = st.pills(_("What are you scanning?"), CATEGORIES, selection_mode="single", default="tops",
                        key=f"scan_cat_{rev}", format_func=format_func("category")) or "tops"
    shot = st.camera_input(_("Fill the frame with the piece, then take the photo"), key=f"scan_cam_{rev}")
    if not shot:
        ui.muted(_("Tip: daylight and a plain background give the truest colors. Only the centre of the photo is read."))
        return

    data = shot.getvalue()
    digest = hashlib.sha1(data).hexdigest()[:12]
    override = st.session_state.get(f"scan_fix_{digest}")
    try:
        with st.spinner(_("Reading the colors…")):
            first = _analysis(data, category, None)
            result = _analysis(data, category, override) if override and override != first.main_hex else first
    except ip.ImageValidationError as exc:
        st.error(str(exc))
        return

    # ---- what was detected
    with ui.card():
        left, right = st.columns([1, 1.3])
        with left:
            st.image(ip.preview_with_box(ip.open_image(data), scan.SCAN_CROP, max_side=480), width="stretch",
                     caption=_("The framed area is what I read"))
        with right:
            st.markdown("**" + _("This piece is") + "**")
            ui.swatches([(result.main_hex, cname(result.main_hex))] + [(s, None) for s in result.secondary])
            ui.muted(f"{label('shade', result.request.shade)} · {label('category', category)}")
            st.color_picker(_("Not quite right? Correct the main color"), first.main_hex, key=f"scan_fix_{digest}")

    if result.similar_owned:
        names = ", ".join(f"“{w.name}”" for w in result.similar_owned)
        st.info("👀 " + _("You already own something very similar: {names}", names=names))

    # ---- quick recommendations
    st.markdown("### " + _("Wear it with"))
    cols = st.columns(2)
    for n, (cat, recs) in enumerate(result.recommendations.items()):
        with cols[n % 2], ui.card():
            st.markdown(f"**{ui.esc(label('rec', cat))}**")
            ui.swatches([(r.hex, f"{label('color', r.name)} · {r.score:.0f}") for r in recs], show_hex=False)
            if recs:
                ui.muted(recs[0].explanations[0])
            owned = result.owned_matches.get(cat)
            if owned:
                st.markdown(
                    "<span class='cm-eyebrow'>" + ui.esc(_("In your wardrobe")) + "</span><br>" +
                    "".join(ui.chip_html(r.hex, r.wardrobe_item.name) for r in owned), unsafe_allow_html=True)
    if result.nails:
        with ui.card():
            st.markdown("**" + _("Nail colors for this piece") + "**")
            ui.swatches([(n.hex, label("color", n.name)) for n in result.nails], show_hex=False)

    # ---- ask to sync to the wardrobe
    saved_id = st.session_state.get(f"scan_saved_{digest}")
    if saved_id:
        st.success(_("Saved to your wardrobe ✓"))
        a, b = st.columns(2)
        a.button("📷 " + _("Scan another piece"), on_click=_reset_camera, width="stretch", type="primary")
        if full_app and b.button("👗 " + _("Build an outfit with it"), width="stretch"):
            _open_outfit(result, saved_id)
        return
    if st.session_state.get(f"scan_dismissed_{digest}"):
        st.button("📷 " + _("Scan another piece"), on_click=_reset_camera, type="primary")
        return

    with ui.card():
        st.markdown("#### " + _("Add this piece to your wardrobe?"))
        subs = scan.subcategories_for(category)
        sub = st.selectbox(_("Type"), [None, *subs], format_func=format_func("subcategory"), key=f"scan_sub_{digest}_{category}")
        name = st.text_input(_("Name"), value=result.suggested_name(sub), key=f"scan_name_{digest}_{category}_{sub}", max_chars=120)
        c1, c2 = st.columns(2)
        pattern = c1.selectbox(_("Pattern"), PATTERNS, format_func=format_func("pattern"), key=f"scan_pat_{digest}")
        favorite = c2.toggle(_("Favorite"), key=f"scan_fav_{digest}")
        b1, b2 = st.columns(2)
        if b1.button("✓ " + _("Save to my wardrobe"), type="primary", width="stretch", key=f"scan_save_{digest}"):
            if not name.strip():
                st.error(_("Please give the piece a name."))
            else:
                with st.spinner(_("Saving…")):
                    item = scan.save_to_wardrobe(session.repo(), result, name=name, subcategory=sub,
                                                 pattern=pattern, favorite=favorite)
                session.invalidate()
                st.session_state[f"scan_saved_{digest}"] = item.id
                st.toast(_("“{name}” saved", name=item.name))
                st.rerun()
        if b2.button(_("Not now"), width="stretch", key=f"scan_skip_{digest}"):
            st.session_state[f"scan_dismissed_{digest}"] = True
            st.rerun()


def _open_outfit(result: scan.ScanResult, item_id: str) -> None:
    from src.core.recommender import wardrobe_matches
    from src.services.styling import outfit_from_match

    items = session.all_items()
    base = next((i for i in items if i.id == item_id), None)
    owned = {c: wardrobe_matches(result.request, items, c, exclude_id=item_id) for c in result.recommendations}
    session.open_in_studio(outfit_from_match(result.request, result.recommendations, owned, base, session.preferences()))
    st.switch_page("pages/outfit_studio.py")
