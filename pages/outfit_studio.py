"""Outfit Studio: compose a look; the flat-lay and the mannequin render the same outfit.

The editor is form-based (select / recolor / remove / add pieces) — not drag
and drop. Every change updates the single shared ``Outfit`` in the session
and both visualizations re-render from it. Each piece's panel has a stable
key, so it stays open while you change its options.
"""

from __future__ import annotations

import io
import json

import streamlit as st

from src.components import ui
from src.components.looks import export_buttons, mannequin_html
from src.core.beauty import recommend_hairstyles, recommend_nails
from src.core.outfit_engine import OutfitContext, score_outfit
from src.i18n import _, cname, format_func, label
from src.models.domain import (
    HAIR_COLORS,
    HAIR_STYLES,
    NAIL_SHAPES,
    OCCASIONS,
    PATTERNS,
    SEASONS,
    SLOT_TO_CATEGORY,
    STYLES,
    SUBCATEGORIES,
    Outfit,
    OutfitItem,
)
from src.services import session
from src.visualizer import flatlay

ACCESSORY_SLOTS = ("outerwear", "shoes", "bag", "jewelry", "accessory", "scarf", "belt", "hat")
SKIN_TONES = {"Porcelain": "#F3DCCB", "Light": "#E8C4A8", "Medium": "#D2A07C", "Tan": "#B07A55",
              "Deep": "#7E5139", "Rich": "#5A3726"}


def variants_for(slot: str) -> list[str]:
    return list(dict.fromkeys(SUBCATEGORIES[SLOT_TO_CATEGORY[slot]].values()))


def _set_color_widget(key: str, hex_value: str) -> None:
    st.session_state[f"{key}_mode"] = "Custom"
    st.session_state[f"{key}_pick"] = hex_value


def slot_editor(outfit: Outfit, slot: str, k: str) -> None:
    cur = outfit.get(slot)
    items = [i for i in session.all_items() if i.slot == slot]
    options = ["None", "From wardrobe", "Custom color"]
    default = 0 if cur is None else (1 if cur.wardrobe_item_id and any(i.id == cur.wardrobe_item_id for i in items) else 2)
    current = (cur.label or cname(cur.color_hex)) if cur else _("none")
    # stable key: the panel stays open even though its title shows the current choice
    with st.expander(f"{label('slot', slot)} — {current}", expanded=False, key=f"{k}{slot}_panel"):
        src = st.radio(_("Source"), options, index=default, horizontal=True, key=f"{k}{slot}_src",
                       label_visibility="collapsed", format_func=_)
        if src == "None":
            if cur is not None:
                outfit.remove(slot)
            return
        if src == "From wardrobe":
            if not items:
                st.info(_("No pieces of this kind in your wardrobe yet — use a custom color."))
                return
            ids = [i.id for i in items]
            idx = ids.index(cur.wardrobe_item_id) if cur and cur.wardrobe_item_id in ids else 0
            names = {x.id: x.name for x in items}
            choice = st.selectbox(_("Piece"), ids, index=idx, format_func=names.get, key=f"{k}{slot}_item")
            witem = next(x for x in items if x.id == choice)
            new = OutfitItem.from_wardrobe(witem)
            recolor = st.toggle(_("Try it in another color"), key=f"{k}{slot}_recolor",
                                value=bool(cur and cur.wardrobe_item_id == choice and cur.color_hex != witem.primary_color))
            if recolor:
                start = cur.color_hex if cur and cur.wardrobe_item_id == choice else witem.primary_color
                new.color_hex = ui.color_input(_("Color"), f"{k}{slot}_rc", start)
            ui.chips([new.color_hex])
        else:
            vars_ = variants_for(slot)
            v_idx = vars_.index(cur.variant) if cur and cur.variant in vars_ else 0
            variant = st.selectbox(_("Shape"), vars_, index=v_idx, format_func=format_func("variant"), key=f"{k}{slot}_var")
            color = ui.color_input(_("Color"), f"{k}{slot}_col", cur.color_hex if cur else "#C8AD91")
            c1, c2 = st.columns(2)
            pattern = c1.selectbox(_("Pattern"), PATTERNS, index=PATTERNS.index(cur.pattern) if cur else 0,
                                   format_func=format_func("pattern"), key=f"{k}{slot}_pat")
            sec = None
            if pattern != "solid":
                sec = c2.color_picker(_("Pattern color"), (cur.secondary_hex if cur and cur.secondary_hex else "#F8F4EF"),
                                      key=f"{k}{slot}_sec")
            new = OutfitItem(slot=slot, color_hex=color, variant=variant, pattern=pattern, secondary_hex=sec,
                             label=f"{cname(color)} · {label('variant', variant).lower()}")
        if cur is not None:
            new.id = cur.id
        outfit.set_item(new)


def beauty_editor(outfit: Outfit, k: str) -> None:
    prefs = session.preferences()
    st.markdown("##### " + _("Hair"))
    styles = list(HAIR_STYLES)
    hs_key = f"{k}hair_style"
    if hs_key not in st.session_state:
        st.session_state[hs_key] = outfit.hair_style
    outfit.hair_style = st.selectbox(_("Hairstyle"), styles, format_func=format_func("hair"), key=hs_key)
    st.caption(_("Suggested for this look:"))
    for s in recommend_hairstyles(outfit, prefs):
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"**{ui.esc(s.label)}** · {s.score:.0f} — <span class='cm-muted'>{ui.esc(' '.join(s.reasons[:2]))}</span>",
                    unsafe_allow_html=True)
        c2.button(_("Use"), key=f"{k}use_hair_{s.style}", on_click=lambda v=s.style: st.session_state.__setitem__(hs_key, v))
    names = list(HAIR_COLORS) + ["Custom"]
    current_name = next((n for n, h in HAIR_COLORS.items() if h == outfit.hair_color), "Custom")
    hc_name = st.selectbox(_("Hair color"), names, index=names.index(current_name), key=f"{k}hair_color_name",
                           format_func=lambda n: _("Custom") if n == "Custom" else label("hair_color", n))
    if hc_name == "Custom":
        outfit.hair_color = st.color_picker(_("Custom hair color"), outfit.hair_color, key=f"{k}hair_color_pick").upper()
    else:
        outfit.hair_color = HAIR_COLORS[hc_name]
    tones = list(SKIN_TONES) + ["Custom"]
    t_name = next((n for n, h in SKIN_TONES.items() if h == outfit.skin_tone), "Custom")
    t_choice = st.selectbox(_("Mannequin skin tone"), tones, index=tones.index(t_name), key=f"{k}skin",
                            format_func=lambda n: _("Custom") if n == "Custom" else label("skin", n))
    outfit.skin_tone = (st.color_picker(_("Custom skin tone"), outfit.skin_tone, key=f"{k}skin_pick").upper()
                        if t_choice == "Custom" else SKIN_TONES[t_choice])

    st.markdown("##### " + _("Nails"))
    cur = outfit.get("nails")
    on = st.toggle(_("Show nail polish"), value=cur is not None, key=f"{k}nails_on")
    if not on:
        if cur:
            outfit.remove("nails")
        return
    nk = f"{k}nails_col"
    color = ui.color_input(_("Polish color"), nk, cur.color_hex if cur else "#B77E79")
    shapes = list(NAIL_SHAPES)
    shape = st.selectbox(_("Nail shape"), shapes, format_func=format_func("nail"),
                         index=shapes.index(cur.variant) if cur and cur.variant in shapes else shapes.index(prefs.nail_shape),
                         key=f"{k}nails_shape")
    outfit.set_item(OutfitItem(slot="nails", color_hex=color, variant=shape, label=_("{color} polish", color=cname(color)),
                               id=cur.id if cur else OutfitItem(slot="nails", color_hex=color).id))
    st.caption(_("Polish that suits this outfit:"))
    recs = recommend_nails(outfit, prefs=prefs, limit=5)
    cols = st.columns(len(recs) or 1)
    for col, r in zip(cols, recs):
        with col:
            st.markdown(ui.swatch_html(r.hex, label("color", r.name), show_hex=False), unsafe_allow_html=True)
            st.button(_("Use"), key=f"{k}use_nail_{r.name}", on_click=_set_color_widget, args=(nk, r.hex), width="stretch")


def _preview_png(outfit: Outfit, layout: str, use_photos: bool) -> bytes:
    sig = json.dumps(outfit.to_dict(), sort_keys=True, default=str) + layout + str(use_photos)
    cache = st.session_state.setdefault("_studio_preview", {})
    if sig not in cache:
        cache.clear()
        img = flatlay.render_preview(outfit, layout, photo_loader=session.photo_loader, use_photos=use_photos, width=720)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        cache[sig] = buf.getvalue()
    return cache[sig]


@ui.guarded
def render() -> None:
    ui.header(_("Outfit Studio"),
              _("Build a look piece by piece. The flat-lay and the illustrated mannequin always show the same outfit."))
    outfit = session.studio_outfit()
    k = f"s{st.session_state.get('studio_rev', 0)}_"
    prefs = session.preferences()

    edit_col, view_col = st.columns([1, 1.15], gap="large")
    with edit_col:
        t_pieces, t_beauty, t_details = st.tabs([_("Pieces"), _("Hair & nails"), _("Details")])
        with t_details:
            outfit.name = st.text_input(_("Name"), outfit.name, key=f"{k}name", max_chars=120)
            c1, c2, c3 = st.columns(3)
            occ_opts = [None, *OCCASIONS]
            outfit.occasion = c1.selectbox(_("Occasion"), occ_opts, index=occ_opts.index(outfit.occasion) if outfit.occasion in occ_opts else 0,
                                           format_func=format_func("occasion"), key=f"{k}occ")
            sty_opts = [None, *STYLES]
            outfit.style = c2.selectbox(_("Style"), sty_opts, index=sty_opts.index(outfit.style) if outfit.style in sty_opts else 0,
                                        format_func=format_func("style"), key=f"{k}sty")
            sea_opts = [None, *SEASONS]
            outfit.season = c3.selectbox(_("Season"), sea_opts, index=sea_opts.index(outfit.season) if outfit.season in sea_opts else 0,
                                         format_func=format_func("season"), key=f"{k}sea")
            outfit.notes = st.text_area(_("Notes"), outfit.notes or "", key=f"{k}notes", height=90) or None
            lay = list(flatlay.LAYOUTS)
            outfit.layout = st.selectbox(_("Flat-lay layout"), lay, index=lay.index(outfit.layout) if outfit.layout in lay else 0,
                                         format_func=format_func("layout"), key=f"{k}layout")
            st.toggle(_("Use my photos in the flat-lay"), value=True, key=f"{k}photos")
        with t_pieces:
            base_default = 1 if outfit.get("dress") else 0
            base = st.radio(_("Base"), ["Separates (top + bottom)", "Dress"], index=base_default, horizontal=True,
                            key=f"{k}base", format_func=_)
            if base == "Dress":
                outfit.remove("top")
                outfit.remove("bottom")
                slot_editor(outfit, "dress", k)
            else:
                outfit.remove("dress")
                slot_editor(outfit, "top", k)
                slot_editor(outfit, "bottom", k)
            st.caption(_("Shoes, layers & accessories"))
            for slot in ACCESSORY_SLOTS:
                slot_editor(outfit, slot, k)
        with t_beauty:
            beauty_editor(outfit, k)

    ctx = OutfitContext(outfit.occasion, outfit.style, outfit.season, prefs)
    bd = score_outfit(outfit, ctx, session.items_by_id())
    outfit.score = bd.total if outfit.items else None
    use_photos = st.session_state.get(f"{k}photos", True)

    with view_col:
        st.markdown(f"**{ui.esc(outfit.name)}** &nbsp; {ui.score_badge(bd.total)}", unsafe_allow_html=True)
        v_flat, v_mann = st.tabs([_("Flat-lay"), _("Mannequin")])
        with v_flat:
            if outfit.garments:
                st.image(_preview_png(outfit, outfit.layout, use_photos), width="stretch")
            else:
                ui.empty_state(_("An empty board"), _("Add pieces on the left to see your flat-lay."))
        with v_mann:
            st.markdown(mannequin_html(outfit, 600), unsafe_allow_html=True)
        with st.expander(_("Why this score"), expanded=False, key=f"{k}why"):
            ui.breakdown_bars(bd)
            for note in bd.explanations:
                st.markdown(f"- {note}")

        repo = session.repo()
        is_saved = outfit.created_at is not None
        c1, c2, c3 = st.columns(3)
        if c1.button("💾 " + (_("Save changes") if is_saved else _("Save")), type="primary", width="stretch", disabled=not outfit.items):
            saved = repo.save_outfit(outfit)
            session.invalidate()
            st.session_state["studio_outfit"] = saved
            st.toast(_("Look saved"))
            st.rerun()
        if c2.button(_("Save as new"), width="stretch", disabled=not outfit.items):
            clone = outfit.copy(new_identity=True)
            if is_saved:
                clone.name = _("{name} (copy)", name=outfit.name)
            saved = repo.save_outfit(clone)
            session.invalidate()
            session.open_in_studio(saved)
            st.toast(_("Saved as a new look"))
            st.rerun()
        if c3.button(_("New look"), width="stretch"):
            session.open_in_studio(Outfit(name=_("New look"), skin_tone=prefs.skin_tone, hair_color=prefs.hair_color,
                                          hair_style=prefs.hair_style))
            st.rerun()
        if outfit.items:
            export_buttons(outfit, f"studio_{outfit.id}", photo_loader=session.photo_loader if use_photos else None)


render()
