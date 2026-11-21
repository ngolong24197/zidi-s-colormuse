"""Saved Looks: browse, search, favorite, duplicate, delete, annotate, organize and export."""

from __future__ import annotations

import streamlit as st

from src.components import ui
from src.components.looks import export_buttons, mannequin_html, palette_list
from src.i18n import _, format_func, label
from src.models.domain import OCCASIONS, Collection
from src.services import session

PAGE = 12


def collections_manager() -> None:
    repo = session.repo()
    with st.expander("📁 " + _("Manage collections"), key="sl_manage"):
        with st.form("new_collection", clear_on_submit=True, border=False):
            c1, c2 = st.columns([3, 1])
            name = c1.text_input(_("New collection"), placeholder=_("e.g. Summer in Italy"), max_chars=80)
            if c2.form_submit_button(_("Create"), width="stretch") and name.strip():
                repo.save_collection(Collection(name=name))
                session.invalidate()
                st.rerun()
        for col in session.collections():
            c1, c2, c3 = st.columns([3, 1, 1])
            new_name = c1.text_input(_("Name"), col.name, key=f"coln_{col.id}", label_visibility="collapsed")
            if c2.button(_("Rename"), key=f"colr_{col.id}", width="stretch") and new_name.strip() and new_name != col.name:
                col.name = new_name
                repo.save_collection(col)
                session.invalidate()
                st.rerun()
            if c3.button(_("Delete"), key=f"cold_{col.id}", width="stretch"):
                repo.delete_collection(col.id)
                session.invalidate()
                st.toast(_("Collection deleted (the looks are kept)"))
                st.rerun()


def look_card(o) -> None:
    repo = session.repo()
    with ui.card():
        st.markdown(f"**{'♥ ' if o.favorite else ''}{ui.esc(o.name)}**" + (f" &nbsp; {ui.score_badge(o.score)}" if o.score else ""),
                    unsafe_allow_html=True)
        meta = " · ".join(x for x in (label("occasion", o.occasion), label("style", o.style), label("season", o.season)) if x)
        if meta:
            ui.muted(meta)
        left, right = st.columns([1, 1.2])
        with left:
            st.markdown(mannequin_html(o, 340), unsafe_allow_html=True)
        with right:
            palette_list(o)
            if o.notes:
                st.markdown(f"<div class='cm-muted' style='margin-top:.5rem'>📝 {ui.esc(o.notes)}</div>", unsafe_allow_html=True)
        b1, b2, b3, b4 = st.columns(4)
        if b1.button(_("Edit"), key=f"sl_edit_{o.id}", width="stretch"):
            session.open_in_studio(o.copy())
            st.switch_page("pages/outfit_studio.py")
        if b2.button("♡" if not o.favorite else "♥", key=f"sl_fav_{o.id}", help=_("Favorite"), width="stretch"):
            repo.set_outfit_favorite(o.id, not o.favorite)
            session.invalidate()
            st.rerun()
        if b3.button(_("Copy"), key=f"sl_dup_{o.id}", help=_("Duplicate"), width="stretch"):
            repo.duplicate_outfit(o.id)
            session.invalidate()
            st.toast(_("Duplicated"))
            st.rerun()
        ck = f"sl_confirm_{o.id}"
        if st.session_state.get(ck):
            y, no = st.columns(2)
            if y.button(_("Delete look"), key=f"sl_dely_{o.id}", type="primary", width="stretch"):
                repo.delete_outfit(o.id)
                session.invalidate()
                st.session_state.pop(ck)
                st.rerun()
            if no.button(_("Keep"), key=f"sl_deln_{o.id}", width="stretch"):
                st.session_state.pop(ck)
                st.rerun()
        elif b4.button(_("Delete"), key=f"sl_del_{o.id}", width="stretch"):
            st.session_state[ck] = True
            st.rerun()
        with st.expander(_("Notes & collections"), key=f"sl_more_{o.id}"):
            notes = st.text_area(_("Notes"), o.notes or "", key=f"sl_notes_{o.id}", height=80)
            cols = session.collections()
            names = {c.id: c.name for c in cols}
            current = [c for c in repo.collections_for_outfit(o.id) if c in names]
            if names:
                chosen = ui.multi_choice(_("Collections"), list(names), current, f"sl_cols_{o.id}", format_func=names.get)
            else:
                chosen = []
                ui.muted(_("Create a collection under “Manage collections” first."))
            if st.button(_("Save"), key=f"sl_save_{o.id}"):
                if (notes or None) != o.notes:
                    o.notes = notes or None
                    repo.save_outfit(o)
                for cid in set(chosen) - set(current):
                    repo.add_to_collection(cid, o.id)
                for cid in set(current) - set(chosen):
                    repo.remove_from_collection(cid, o.id)
                session.invalidate()
                st.toast(_("Updated"))
                st.rerun()
        export_buttons(o, f"sl_{o.id}", photo_loader=session.photo_loader)


@ui.guarded
def render() -> None:
    ui.header(_("Saved Looks"), _("Your favourite outfits, organized your way."))
    collections_manager()
    cols = session.collections()
    names = {c.id: c.name for c in cols}
    c1, c2, c3, c4 = st.columns([2, 1.4, 1.4, 1])
    search = c1.text_input(_("Search looks"), key="sl_search", placeholder=_("Name, notes, occasion…"))
    coll = c2.selectbox(_("Collection"), [None, *names], key="sl_coll",
                        format_func=lambda cid: _("All looks") if cid is None else names[cid])
    occ = c3.selectbox(_("Occasion"), [None, *OCCASIONS], format_func=format_func("occasion", "Any occasion"), key="sl_occ")
    fav = c4.toggle(_("♥ only"), key="sl_favonly")
    page = st.session_state.get("sl_page", 0)
    filters = (search, coll, occ, fav)
    if st.session_state.get("sl_filters") != filters:
        st.session_state["sl_filters"] = filters
        page = st.session_state["sl_page"] = 0
    looks, total = session.cached(f"looks:{filters}:{page}", lambda: session.repo().list_outfits(
        search=search, collection_id=coll, occasion=occ, favorite=True if fav else None, limit=PAGE, offset=page * PAGE))
    st.caption(_("{n} looks", n=total) if total != 1 else _("1 look"))
    if not looks:
        ui.empty_state(_("No saved looks"), _("Save a look from the Outfit Studio or the Occasion Planner."))
        return
    grid = st.columns(2)
    for n, o in enumerate(looks):
        with grid[n % 2]:
            look_card(o)
    pages = max(1, -(-total // PAGE))
    if pages > 1:
        p1, p2, p3 = st.columns([1, 2, 1])
        if p1.button(_("← Previous"), disabled=page == 0, width="stretch"):
            st.session_state["sl_page"] = page - 1
            st.rerun()
        p2.markdown(f"<div style='text-align:center;padding-top:.6rem'>{ui.esc(_('Page {page} of {pages}', page=page + 1, pages=pages))}</div>",
                    unsafe_allow_html=True)
        if p3.button(_("Next →"), disabled=page >= pages - 1, width="stretch"):
            st.session_state["sl_page"] = page + 1
            st.rerun()


render()
