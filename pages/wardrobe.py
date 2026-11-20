"""My Wardrobe: full clothing management with photos and color extraction."""

from __future__ import annotations

import streamlit as st

from src.components import ui
from src.core.color_convert import shade_of
from src.core.color_library import COLOR_LIBRARY, color_name
from src.database.base import PAGE_SIZE, WARDROBE_SORTS
from src.models.domain import (
    CATEGORIES,
    CATEGORY_LABELS,
    OCCASIONS,
    PATTERNS,
    SEASONS,
    SHADES,
    STYLES,
    SUBCATEGORIES,
    WardrobeItem,
    new_id,
)
from src.services import image_processing as ip
from src.services import session

LIB_NAMES = [c.name for c in COLOR_LIBRARY]
LIB_HEX = {c.name: c.hex for c in COLOR_LIBRARY}


def _photo_block(prefix: str):
    """Upload + crop + extract. Returns (bytes, filename, crop_box, extraction) or None."""
    up = st.file_uploader("Photo (JPG, PNG or WEBP, up to 10 MB)", type=["jpg", "jpeg", "png", "webp"], key=f"{prefix}_photo")
    if not up:
        return None
    data = up.getvalue()
    try:
        img = ip.validate_image(data, up.name)
    except ip.ImageValidationError as exc:
        st.error(str(exc))
        return None
    c1, c2 = st.columns(2)
    lr = c1.slider("Crop left ↔ right", 0, 100, (0, 100), key=f"{prefix}_lr")
    tb = c2.slider("Crop top ↕ bottom", 0, 100, (0, 100), key=f"{prefix}_tb")
    box = (lr[0] / 100, tb[0] / 100, max(lr[1], lr[0] + 5) / 100, max(tb[1], tb[0] + 5) / 100)
    reduce_bg = st.toggle("Reduce background when detecting colors", value=True, key=f"{prefix}_bg")
    pc, ec = st.columns([1, 1.3])
    pc.image(ip.preview_with_box(img, box), width="stretch", caption="The highlighted area is saved")
    sig = (up.name, len(data), box, reduce_bg)
    if st.session_state.get(f"{prefix}_sig") != sig:
        with st.spinner("Detecting colors…"):
            st.session_state[f"{prefix}_ext"] = ip.extract_colors(img, box, reduce_background=reduce_bg)
            st.session_state[f"{prefix}_sig"] = sig
    ext: ip.ExtractionResult = st.session_state[f"{prefix}_ext"]
    with ec:
        st.markdown("**Detected colors** — you can correct them below")
        ui.swatches([(c.hex, f"{c.name} · {int(c.share * 100)}%") for c in ext.colors])
        ui.muted(f"{ext.method}; automatic detection can be fooled by shadows and busy backgrounds.")
    return data, up.name, box, ext


def item_form(existing: WardrobeItem | None) -> None:
    prefix = f"f_{existing.id[:8]}" if existing else "f_new"
    repo = session.repo()
    cat = st.selectbox("Category", CATEGORIES, format_func=CATEGORY_LABELS.get,
                       index=CATEGORIES.index(existing.category) if existing else 0, key=f"{prefix}_cat")
    subs = list(SUBCATEGORIES[cat])
    sub_idx = subs.index(existing.subcategory) + 1 if existing and existing.subcategory in subs else 0
    sub = st.selectbox("Type", [None, *subs], index=sub_idx, format_func=lambda x: "—" if x is None else x, key=f"{prefix}_sub_{cat}")
    name = st.text_input("Name", value=existing.name if existing else "", placeholder="e.g. Silk blush blouse", key=f"{prefix}_name")

    st.markdown("##### Photo")
    if existing and existing.thumb_path:
        src = session.image_sources([existing.thumb_path]).get(existing.thumb_path)
        c1, c2 = st.columns([1, 3])
        if src:
            c1.image(src, width="stretch")
        with c2:
            ui.muted("Upload a new photo to replace this one.")
            if st.button("Remove photo", key=f"{prefix}_rmphoto"):
                repo.delete_item_images(existing.id)
                session.invalidate()
                st.toast("Photo removed")
                st.rerun()
    photo = _photo_block(prefix)

    st.markdown("##### Colors")
    ext = photo[3] if photo else None
    default_primary = ext.primary.hex if ext and ext.primary else (existing.primary_color if existing else "#B77E79")
    sig = default_primary.lstrip("#")
    primary = ui.color_input("Main color", f"{prefix}_pc_{sig}", default_primary)
    default_sec = ([color_name(c.hex) for c in ext.secondary] if ext else
                   [color_name(c) for c in (existing.secondary_colors if existing else [])])
    secondary_names = st.multiselect("Secondary colors", LIB_NAMES, default=[n for n in dict.fromkeys(default_sec) if n in LIB_NAMES][:3],
                                     max_selections=3, key=f"{prefix}_sec_{sig}")
    c1, c2 = st.columns(2)
    auto_shade = shade_of(primary)
    shade = c1.selectbox("Shade", SHADES, index=SHADES.index(existing.shade if existing and existing.shade and sig == existing.primary_color.lstrip('#') else auto_shade),
                         key=f"{prefix}_shade_{primary}")
    pattern = c2.selectbox("Pattern", PATTERNS, index=PATTERNS.index(existing.pattern) if existing else 0, key=f"{prefix}_pat")

    st.markdown("##### Details")
    c1, c2 = st.columns(2)
    brand = c1.text_input("Brand", value=(existing.brand or "") if existing else "", key=f"{prefix}_brand")
    seasons = c2.multiselect("Seasons", SEASONS, default=existing.seasons if existing else [], key=f"{prefix}_seasons")
    styles = c1.multiselect("Styles", STYLES, default=existing.styles if existing else [], key=f"{prefix}_styles")
    occasions = c2.multiselect("Occasions", OCCASIONS, default=existing.occasions if existing else [], key=f"{prefix}_occ")
    notes = st.text_area("Notes", value=(existing.notes or "") if existing else "", key=f"{prefix}_notes", height=80)
    favorite = st.toggle("Favorite", value=existing.favorite if existing else False, key=f"{prefix}_fav")

    b1, b2 = st.columns(2)
    if b1.button("Save piece", type="primary", key=f"{prefix}_save", width="stretch"):
        if not name.strip():
            st.error("Please give the piece a name.")
            return
        try:
            item = WardrobeItem(
                id=existing.id if existing else new_id(),
                name=name, category=cat, subcategory=sub, primary_color=primary,
                primary_color_name=color_name(primary), secondary_colors=[LIB_HEX[n] for n in secondary_names],
                shade=shade, pattern=pattern, brand=brand or None, seasons=seasons, styles=styles,
                occasions=occasions, notes=notes or None, favorite=favorite,
                image_path=existing.image_path if existing else None,
                thumb_path=existing.thumb_path if existing else None,
                created_at=existing.created_at if existing else None,
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        with st.status("Saving…", expanded=True) as status:
            processed = None
            if photo:
                st.write("Optimizing photo (resize, compress, thumbnail)…")
                try:
                    processed = ip.process_upload(photo[0], photo[1], photo[2])
                except (ip.ImageValidationError, ValueError) as exc:
                    status.update(label="Photo problem", state="error")
                    st.error(str(exc))
                    return
            st.write("Saving details…")
            saved = repo.save_item(item)
            if processed:
                st.write(f"Uploading photo ({processed.size_bytes // 1024} KB)…")
                repo.upload_item_image(saved.id, processed.full, processed.thumb, processed.width, processed.height)
            status.update(label="Saved ✓", state="complete")
        session.invalidate()
        for k in [k for k in st.session_state if k.startswith(prefix)]:
            del st.session_state[k]
        st.session_state["wardrobe_mode"] = "list"
        st.session_state.pop("edit_item_id", None)
        st.toast(f"“{saved.name}” saved")
        st.rerun()
    if b2.button("Cancel", key=f"{prefix}_cancel", width="stretch"):
        st.session_state["wardrobe_mode"] = "list"
        st.session_state.pop("edit_item_id", None)
        st.rerun()


def item_grid() -> None:
    repo = session.repo()
    with ui.card():
        c1, c2, c3, c4 = st.columns([2, 1.3, 1.3, 1])
        search = c1.text_input("Search", placeholder="Name, brand, color…", key="w_search")
        category = c2.selectbox("Category", [None, *CATEGORIES], format_func=lambda x: "All categories" if x is None else CATEGORY_LABELS[x], key="w_cat")
        sort = c3.selectbox("Sort", list(WARDROBE_SORTS), format_func=WARDROBE_SORTS.get, key="w_sort")
        fav_only = c4.toggle("♥ only", key="w_fav")
        season = st.pills("Season", SEASONS, key="w_season")
    page = st.session_state.get("w_page", 0)
    filters = (search, category, sort, fav_only, season)
    if st.session_state.get("w_filters") != filters:
        st.session_state["w_filters"] = filters
        page = st.session_state["w_page"] = 0
    items, total = session.cached(
        f"items:{filters}:{page}",
        lambda: repo.list_items(search=search, category=category, favorite=True if fav_only else None,
                                season=season, sort=sort, limit=PAGE_SIZE, offset=page * PAGE_SIZE),
    )
    st.caption(f"{total} piece{'s' if total != 1 else ''}")
    if not items:
        ui.empty_state("Nothing here yet", "Add a piece, or loosen the filters.")
        return
    srcs = session.image_sources([i.thumb_path for i in items if i.thumb_path])
    cols = st.columns(3)
    for n, it in enumerate(items):
        with cols[n % 3], ui.card():
            ui.item_picture(it, srcs.get(it.thumb_path or ""))
            st.markdown(ui.item_caption(it), unsafe_allow_html=True)
            ui.chips([it.primary_color] + it.secondary_colors)
            b1, b2, b3 = st.columns(3)
            if b1.button("♥" if it.favorite else "♡", key=f"fav_{it.id}",
                         help="Remove from favorites" if it.favorite else "Add to favorites", width="stretch"):
                repo.set_item_favorite(it.id, not it.favorite)
                session.invalidate()
                st.rerun()
            if b2.button("Edit", key=f"edit_{it.id}", width="stretch"):
                st.session_state["edit_item_id"] = it.id
                st.session_state["wardrobe_mode"] = "edit"
                st.rerun()
            confirm_key = f"confirm_del_{it.id}"
            if st.session_state.get(confirm_key):
                st.warning("Delete this piece and its photo?")
                y, n_ = st.columns(2)
                if y.button("Delete", key=f"del_yes_{it.id}", type="primary", width="stretch"):
                    repo.delete_item(it.id)
                    session.invalidate()
                    st.session_state.pop(confirm_key, None)
                    st.toast("Deleted")
                    st.rerun()
                if n_.button("Keep", key=f"del_no_{it.id}", width="stretch"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
            elif b3.button("Delete", key=f"del_{it.id}", width="stretch"):
                st.session_state[confirm_key] = True
                st.rerun()
            with st.expander("Details"):
                st.markdown(
                    f"**Color:** {ui.esc(color_name(it.primary_color))} ({it.primary_color}) · {it.shade or shade_of(it.primary_color)}  \n"
                    f"**Pattern:** {it.pattern}" + (f"  \n**Brand:** {ui.esc(it.brand)}" if it.brand else "")
                    + (f"  \n**Seasons:** {', '.join(it.seasons)}" if it.seasons else "")
                    + (f"  \n**Styles:** {', '.join(it.styles)}" if it.styles else "")
                    + (f"  \n**Occasions:** {', '.join(it.occasions)}" if it.occasions else "")
                    + (f"  \n{ui.esc(it.notes)}" if it.notes else ""))
                if st.button("Match this piece", key=f"match_{it.id}"):
                    st.session_state["m_source"] = "Wardrobe piece"
                    st.session_state["m_item"] = f"{it.name} — {CATEGORY_LABELS[it.category]}"
                    st.switch_page("pages/color_matcher.py")
    pages = max(1, -(-total // PAGE_SIZE))
    if pages > 1:
        p1, p2, p3 = st.columns([1, 2, 1])
        if p1.button("← Previous", disabled=page == 0, width="stretch"):
            st.session_state["w_page"] = page - 1
            st.rerun()
        p2.markdown(f"<div style='text-align:center;padding-top:.6rem'>Page {page + 1} of {pages}</div>", unsafe_allow_html=True)
        if p3.button("Next →", disabled=page >= pages - 1, width="stretch"):
            st.session_state["w_page"] = page + 1
            st.rerun()


@ui.guarded
def render() -> None:
    ui.header("My Wardrobe", "Every piece you own, with its true colors.")
    mode = st.session_state.get("wardrobe_mode", "list")
    if mode == "add":
        with ui.card():
            st.markdown("### Add a piece")
            item_form(None)
        return
    if mode == "edit":
        item = session.repo().get_item(st.session_state.get("edit_item_id", ""))
        if item is None:
            st.session_state["wardrobe_mode"] = "list"
            st.rerun()
        with ui.card():
            st.markdown(f"### Edit “{ui.esc(item.name)}”")
            item_form(item)
        return
    if st.button("＋ Add a piece", type="primary"):
        st.session_state["wardrobe_mode"] = "add"
        st.rerun()
    item_grid()


render()
