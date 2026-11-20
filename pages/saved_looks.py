"""Saved Looks: browse, search, favorite, duplicate, delete, annotate, organize and export."""

from __future__ import annotations

import streamlit as st

from src.components import ui
from src.components.looks import export_buttons, mannequin_html, palette_list
from src.models.domain import OCCASIONS, Collection
from src.services import session

PAGE = 12


def collections_manager() -> None:
    repo = session.repo()
    with st.expander("📁 Manage collections"):
        with st.form("new_collection", clear_on_submit=True, border=False):
            c1, c2 = st.columns([3, 1])
            name = c1.text_input("New collection", placeholder="e.g. Summer in Italy", max_chars=80)
            if c2.form_submit_button("Create", width="stretch") and name.strip():
                repo.save_collection(Collection(name=name))
                session.invalidate()
                st.rerun()
        for col in session.collections():
            c1, c2, c3 = st.columns([3, 1, 1])
            new_name = c1.text_input("Name", col.name, key=f"coln_{col.id}", label_visibility="collapsed")
            if c2.button("Rename", key=f"colr_{col.id}", width="stretch") and new_name.strip() and new_name != col.name:
                col.name = new_name
                repo.save_collection(col)
                session.invalidate()
                st.rerun()
            if c3.button("Delete", key=f"cold_{col.id}", width="stretch"):
                repo.delete_collection(col.id)
                session.invalidate()
                st.toast("Collection deleted (the looks are kept)")
                st.rerun()


def look_card(o, n: int) -> None:
    repo = session.repo()
    with ui.card():
        st.markdown(f"**{'♥ ' if o.favorite else ''}{ui.esc(o.name)}**" + (f" &nbsp; {ui.score_badge(o.score)}" if o.score else ""),
                    unsafe_allow_html=True)
        meta = " · ".join(x.title() for x in (o.occasion, o.style, o.season) if x)
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
        if b1.button("Edit", key=f"sl_edit_{o.id}", width="stretch"):
            session.open_in_studio(o.copy())
            st.switch_page("pages/outfit_studio.py")
        if b2.button("♡" if not o.favorite else "♥", key=f"sl_fav_{o.id}", help="Favorite", width="stretch"):
            repo.set_outfit_favorite(o.id, not o.favorite)
            session.invalidate()
            st.rerun()
        if b3.button("Copy", key=f"sl_dup_{o.id}", help="Duplicate", width="stretch"):
            repo.duplicate_outfit(o.id)
            session.invalidate()
            st.toast("Duplicated")
            st.rerun()
        ck = f"sl_confirm_{o.id}"
        if st.session_state.get(ck):
            y, no = st.columns(2)
            if y.button("Delete look", key=f"sl_dely_{o.id}", type="primary", width="stretch"):
                repo.delete_outfit(o.id)
                session.invalidate()
                st.session_state.pop(ck)
                st.rerun()
            if no.button("Keep", key=f"sl_deln_{o.id}", width="stretch"):
                st.session_state.pop(ck)
                st.rerun()
        elif b4.button("Delete", key=f"sl_del_{o.id}", width="stretch"):
            st.session_state[ck] = True
            st.rerun()
        with st.expander("Notes & collections"):
            notes = st.text_area("Notes", o.notes or "", key=f"sl_notes_{o.id}", height=80)
            cols = session.collections()
            current = repo.collections_for_outfit(o.id)
            chosen = st.multiselect("Collections", [c.id for c in cols], default=[c for c in current if c in {x.id for x in cols}],
                                    format_func=lambda cid: next(c.name for c in cols if c.id == cid), key=f"sl_cols_{o.id}")
            if st.button("Save", key=f"sl_save_{o.id}"):
                if (notes or None) != o.notes:
                    o.notes = notes or None
                    repo.save_outfit(o)
                for cid in set(chosen) - set(current):
                    repo.add_to_collection(cid, o.id)
                for cid in set(current) - set(chosen):
                    repo.remove_from_collection(cid, o.id)
                session.invalidate()
                st.toast("Updated")
                st.rerun()
        export_buttons(o, f"sl_{o.id}", photo_loader=session.photo_loader)


@ui.guarded
def render() -> None:
    ui.header("Saved Looks", "Your favourite outfits, organized your way.")
    collections_manager()
    cols = session.collections()
    c1, c2, c3, c4 = st.columns([2, 1.4, 1.4, 1])
    search = c1.text_input("Search looks", key="sl_search", placeholder="Name, notes, occasion…")
    coll = c2.selectbox("Collection", [None] + [c.id for c in cols],
                        format_func=lambda cid: "All looks" if cid is None else next(c.name for c in cols if c.id == cid), key="sl_coll")
    occ = c3.selectbox("Occasion", [None, *OCCASIONS], format_func=lambda x: "Any occasion" if x is None else x.title(), key="sl_occ")
    fav = c4.toggle("♥ only", key="sl_favonly")
    page = st.session_state.get("sl_page", 0)
    filters = (search, coll, occ, fav)
    if st.session_state.get("sl_filters") != filters:
        st.session_state["sl_filters"] = filters
        page = st.session_state["sl_page"] = 0
    looks, total = session.cached(f"looks:{filters}:{page}", lambda: session.repo().list_outfits(
        search=search, collection_id=coll, occasion=occ, favorite=True if fav else None, limit=PAGE, offset=page * PAGE))
    st.caption(f"{total} look{'s' if total != 1 else ''}")
    if not looks:
        ui.empty_state("No saved looks", "Save a look from the Outfit Studio or the Occasion Planner.")
        return
    grid = st.columns(2)
    for n, o in enumerate(looks):
        with grid[n % 2]:
            look_card(o, n)
    pages = max(1, -(-total // PAGE))
    if pages > 1:
        p1, p2, p3 = st.columns([1, 2, 1])
        if p1.button("← Previous", disabled=page == 0, width="stretch"):
            st.session_state["sl_page"] = page - 1
            st.rerun()
        p2.markdown(f"<div style='text-align:center;padding-top:.6rem'>Page {page + 1} of {pages}</div>", unsafe_allow_html=True)
        if p3.button("Next →", disabled=page >= pages - 1, width="stretch"):
            st.session_state["sl_page"] = page + 1
            st.rerun()


render()
