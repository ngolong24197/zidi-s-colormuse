"""My Wardrobe: full clothing management with photos and color extraction."""

from __future__ import annotations

import streamlit as st

from src.components import ui
from src.core.color_convert import shade_of
from src.core.color_library import color_name
from src.database.base import PAGE_SIZE, WARDROBE_SORTS
from src.i18n import _, cname, format_func, label
from src.models.domain import (
    CATEGORIES,
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


def _photo_block(prefix: str):
    """Upload + crop + extract. Returns (bytes, filename, crop_box, extraction) or None."""
    up = st.file_uploader(_("Photo (JPG, PNG or WEBP, up to 10 MB)"), type=["jpg", "jpeg", "png", "webp"], key=f"{prefix}_photo")
    if not up:
        return None
    data = up.getvalue()
    try:
        img = ip.validate_image(data, up.name)
    except ip.ImageValidationError as exc:
        st.error(str(exc))
        return None
    c1, c2 = st.columns(2)
    lr = c1.slider(_("Crop left ↔ right"), 0, 100, (0, 100), key=f"{prefix}_lr")
    tb = c2.slider(_("Crop top ↕ bottom"), 0, 100, (0, 100), key=f"{prefix}_tb")
    box = (lr[0] / 100, tb[0] / 100, max(lr[1], lr[0] + 5) / 100, max(tb[1], tb[0] + 5) / 100)
    reduce_bg = st.toggle(_("Reduce background when detecting colors"), value=True, key=f"{prefix}_bg")
    pc, ec = st.columns([1, 1.3])
    pc.image(ip.preview_with_box(img, box), width="stretch", caption=_("The highlighted area is saved"))
    sig = (up.name, len(data), box, reduce_bg)
    if st.session_state.get(f"{prefix}_sig") != sig:
        with st.spinner(_("Detecting colors…")):
            st.session_state[f"{prefix}_ext"] = ip.extract_colors(img, box, reduce_background=reduce_bg)
            st.session_state[f"{prefix}_sig"] = sig
    ext: ip.ExtractionResult = st.session_state[f"{prefix}_ext"]
    with ec:
        st.markdown("**" + _("Detected colors") + "** — " + _("you can correct them below"))
        ui.swatches([(c.hex, f"{cname(c.hex)} · {int(c.share * 100)}%") for c in ext.colors])
        ui.muted(_("Automatic detection can be fooled by shadows and busy backgrounds."))
    return data, up.name, box, ext


def item_form(existing: WardrobeItem | None) -> None:
    prefix = f"f_{existing.id[:8]}" if existing else "f_new"
    repo = session.repo()
    cat = st.selectbox(_("Category"), CATEGORIES, format_func=format_func("category"),
                       index=CATEGORIES.index(existing.category) if existing else 0, key=f"{prefix}_cat")
    subs = list(SUBCATEGORIES[cat])
    sub_idx = subs.index(existing.subcategory) + 1 if existing and existing.subcategory in subs else 0
    sub = st.selectbox(_("Type"), [None, *subs], index=sub_idx, format_func=format_func("subcategory"),
                       key=f"{prefix}_sub_{cat}")
    name = st.text_input(_("Name"), value=existing.name if existing else "",
                         placeholder=_("e.g. Silk blush blouse"), key=f"{prefix}_name")

    st.markdown("##### " + _("Photo"))
    if existing and existing.thumb_path:
        src = session.image_sources([existing.thumb_path]).get(existing.thumb_path)
        c1, c2 = st.columns([1, 3])
        if src:
            c1.image(src, width="stretch")
        with c2:
            ui.muted(_("Upload a new photo to replace this one."))
            if st.button(_("Remove photo"), key=f"{prefix}_rmphoto"):
                repo.delete_item_images(existing.id)
                session.invalidate()
                st.toast(_("Photo removed"))
                st.rerun()
    photo = _photo_block(prefix)

    st.markdown("##### " + _("Colors"))
    ext = photo[3] if photo else None
    default_primary = ext.primary.hex if ext and ext.primary else (existing.primary_color if existing else "#B77E79")
    sig = default_primary.lstrip("#")
    primary = ui.color_input(_("Main color"), f"{prefix}_pc_{sig}", default_primary)
    default_sec = [c.hex for c in ext.secondary] if ext else (existing.secondary_colors if existing else [])
    secondary = ui.color_multi_choice(_("Secondary colors"), default_sec, key=f"{prefix}_sec_{sig}", max_selections=3)
    c1, c2 = st.columns(2)
    auto_shade = shade_of(primary)
    keep_shade = existing and existing.shade and sig == existing.primary_color.lstrip("#")
    shade = c1.selectbox(_("Shade"), SHADES, index=SHADES.index(existing.shade if keep_shade else auto_shade),
                         format_func=format_func("shade"), key=f"{prefix}_shade_{primary}")
    pattern = c2.selectbox(_("Pattern"), PATTERNS, index=PATTERNS.index(existing.pattern) if existing else 0,
                           format_func=format_func("pattern"), key=f"{prefix}_pat")

    st.markdown("##### " + _("Details"))
    brand = st.text_input(_("Brand"), value=(existing.brand or "") if existing else "", key=f"{prefix}_brand")
    seasons = ui.multi_choice(_("Seasons"), list(SEASONS), existing.seasons if existing else [], f"{prefix}_seasons", "season")
    styles = ui.multi_choice(_("Styles"), list(STYLES), existing.styles if existing else [], f"{prefix}_styles", "style")
    occasions = ui.multi_choice(_("Occasions"), list(OCCASIONS), existing.occasions if existing else [], f"{prefix}_occ", "occasion")
    notes = st.text_area(_("Notes"), value=(existing.notes or "") if existing else "", key=f"{prefix}_notes", height=80)
    favorite = st.toggle(_("Favorite"), value=existing.favorite if existing else False, key=f"{prefix}_fav")

    b1, b2 = st.columns(2)
    if b1.button(_("Save piece"), type="primary", key=f"{prefix}_save", width="stretch"):
        if not name.strip():
            st.error(_("Please give the piece a name."))
            return
        try:
            item = WardrobeItem(
                id=existing.id if existing else new_id(),
                name=name, category=cat, subcategory=sub, primary_color=primary,
                primary_color_name=color_name(primary), secondary_colors=secondary,
                shade=shade, pattern=pattern, brand=brand or None, seasons=seasons, styles=styles,
                occasions=occasions, notes=notes or None, favorite=favorite,
                image_path=existing.image_path if existing else None,
                thumb_path=existing.thumb_path if existing else None,
                created_at=existing.created_at if existing else None,
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        with st.status(_("Saving…"), expanded=True) as status:
            processed = None
            if photo:
                st.write(_("Optimizing photo (resize, compress, thumbnail)…"))
                try:
                    processed = ip.process_upload(photo[0], photo[1], photo[2])
                except (ip.ImageValidationError, ValueError) as exc:
                    status.update(label=_("Photo problem"), state="error")
                    st.error(str(exc))
                    return
            st.write(_("Saving details…"))
            saved = repo.save_item(item)
            if processed:
                st.write(_("Uploading photo ({kb} KB)…", kb=processed.size_bytes // 1024))
                repo.upload_item_image(saved.id, processed.full, processed.thumb, processed.width, processed.height)
            status.update(label=_("Saved ✓"), state="complete")
        session.invalidate()
        for k in [k for k in st.session_state if k.startswith(prefix)]:
            del st.session_state[k]
        st.session_state["wardrobe_mode"] = "list"
        st.session_state.pop("edit_item_id", None)
        st.toast(_("“{name}” saved", name=saved.name))
        st.rerun()
    if b2.button(_("Cancel"), key=f"{prefix}_cancel", width="stretch"):
        st.session_state["wardrobe_mode"] = "list"
        st.session_state.pop("edit_item_id", None)
        st.rerun()


def item_grid() -> None:
    repo = session.repo()
    with ui.card():
        c1, c2, c3, c4 = st.columns([2, 1.3, 1.3, 1])
        search = c1.text_input(_("Search"), placeholder=_("Name, brand, color…"), key="w_search")
        category = c2.selectbox(_("Category"), [None, *CATEGORIES], format_func=format_func("category", "All categories"), key="w_cat")
        sort = c3.selectbox(_("Sort"), list(WARDROBE_SORTS), format_func=format_func("sort"), key="w_sort")
        fav_only = c4.toggle(_("♥ only"), key="w_fav")
        season = st.pills(_("Season"), SEASONS, key="w_season", format_func=format_func("season"))
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
    st.caption(_("{n} pieces", n=total) if total != 1 else _("1 piece"))
    if not items:
        ui.empty_state(_("Nothing here yet"), _("Add a piece, or loosen the filters."))
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
                         help=_("Remove from favorites") if it.favorite else _("Add to favorites"), width="stretch"):
                repo.set_item_favorite(it.id, not it.favorite)
                session.invalidate()
                st.rerun()
            if b2.button(_("Edit"), key=f"edit_{it.id}", width="stretch"):
                st.session_state["edit_item_id"] = it.id
                st.session_state["wardrobe_mode"] = "edit"
                st.rerun()
            confirm_key = f"confirm_del_{it.id}"
            if st.session_state.get(confirm_key):
                st.warning(_("Delete this piece and its photo?"))
                y, n_ = st.columns(2)
                if y.button(_("Delete"), key=f"del_yes_{it.id}", type="primary", width="stretch"):
                    repo.delete_item(it.id)
                    session.invalidate()
                    st.session_state.pop(confirm_key, None)
                    st.toast(_("Deleted"))
                    st.rerun()
                if n_.button(_("Keep"), key=f"del_no_{it.id}", width="stretch"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
            elif b3.button(_("Delete"), key=f"del_{it.id}", width="stretch"):
                st.session_state[confirm_key] = True
                st.rerun()
            with st.expander(_("Details"), key=f"details_{it.id}"):
                lines = [
                    f"**{_('Color')}:** {ui.esc(cname(it.primary_color))} ({it.primary_color}) · "
                    f"{label('shade', it.shade or shade_of(it.primary_color))}",
                    f"**{_('Pattern')}:** {label('pattern', it.pattern)}",
                ]
                if it.brand:
                    lines.append(f"**{_('Brand')}:** {ui.esc(it.brand)}")
                if it.seasons:
                    lines.append(f"**{_('Seasons')}:** {', '.join(label('season', s) for s in it.seasons)}")
                if it.styles:
                    lines.append(f"**{_('Styles')}:** {', '.join(label('style', s) for s in it.styles)}")
                if it.occasions:
                    lines.append(f"**{_('Occasions')}:** {', '.join(label('occasion', o) for o in it.occasions)}")
                if it.notes:
                    lines.append(ui.esc(it.notes))
                st.markdown("  \n".join(lines))
                if st.button(_("Match this piece"), key=f"match_{it.id}"):
                    st.session_state["m_source"] = "Wardrobe piece"
                    st.session_state["m_item_id"] = it.id
                    st.switch_page("pages/color_matcher.py")
    pages = max(1, -(-total // PAGE_SIZE))
    if pages > 1:
        p1, p2, p3 = st.columns([1, 2, 1])
        if p1.button(_("← Previous"), disabled=page == 0, width="stretch"):
            st.session_state["w_page"] = page - 1
            st.rerun()
        p2.markdown(f"<div style='text-align:center;padding-top:.6rem'>{ui.esc(_('Page {page} of {pages}', page=page + 1, pages=pages))}</div>",
                    unsafe_allow_html=True)
        if p3.button(_("Next →"), disabled=page >= pages - 1, width="stretch"):
            st.session_state["w_page"] = page + 1
            st.rerun()


@ui.guarded
def render() -> None:
    ui.header(_("My Wardrobe"), _("Every piece you own, with its true colors."))
    mode = st.session_state.get("wardrobe_mode", "list")
    if mode == "add":
        with ui.card():
            st.markdown("### " + _("Add a piece"))
            item_form(None)
        return
    if mode == "edit":
        item = session.repo().get_item(st.session_state.get("edit_item_id", ""))
        if item is None:
            st.session_state["wardrobe_mode"] = "list"
            st.rerun()
        with ui.card():
            st.markdown("### " + _("Edit “{name}”", name=ui.esc(item.name)))
            item_form(item)
        return
    if st.button("＋ " + _("Add a piece"), type="primary"):
        st.session_state["wardrobe_mode"] = "add"
        st.rerun()
    item_grid()


render()
