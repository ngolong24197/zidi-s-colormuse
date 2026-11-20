"""Settings: fashion & beauty preferences, scoring weights, account, data export/restore/delete."""

from __future__ import annotations

import json
from datetime import date

import streamlit as st

from src.components import ui
from src.core.color_library import COLOR_LIBRARY
from src.core.scoring import COMPONENT_LABELS
from src.models.domain import (
    DEFAULT_WEIGHTS,
    HAIR_COLORS,
    HAIR_STYLES,
    NAIL_SHAPES,
    OCCASIONS,
    SEASONS,
    STYLES,
)
from src.services import backup, session
from src.services.auth import AuthError, change_password, sign_out

LIB = {c.name: c.hex for c in COLOR_LIBRARY}
HEX_TO_NAME = {c.hex: c.name for c in COLOR_LIBRARY}
SKIN_TONES = {"Porcelain": "#F3DCCB", "Light": "#E8C4A8", "Medium": "#D2A07C", "Tan": "#B07A55",
              "Deep": "#7E5139", "Rich": "#5A3726"}


def _names(hexes: list[str]) -> list[str]:
    from src.core.color_library import color_name

    return list(dict.fromkeys(HEX_TO_NAME.get(h) or color_name(h) for h in hexes))


@ui.guarded
def render() -> None:
    ui.header("Settings", "Make ColorMuse yours.")
    repo = session.repo()
    prefs = session.preferences()
    t_style, t_beauty, t_weights, t_account, t_data = st.tabs(["Style profile", "Hair & beauty", "Scoring", "Account", "Data"])

    with t_style:
        with st.form("prefs_style"):
            name = st.text_input("What should I call you?", prefs.display_name, max_chars=40)
            fav = st.multiselect("Favorite colors", list(LIB), default=[n for n in _names(prefs.favorite_colors) if n in LIB])
            dis = st.multiselect("Colors you prefer to avoid", list(LIB), default=[n for n in _names(prefs.disliked_colors) if n in LIB])
            styles = st.multiselect("Preferred styles", STYLES, default=prefs.preferred_styles)
            occ = st.multiselect("Occasions you dress for most", OCCASIONS, default=prefs.occasion_preferences)
            seasons = st.multiselect("Seasons you're shopping/styling for", SEASONS, default=prefs.seasons)
            if st.form_submit_button("Save style profile", type="primary"):
                overlap = set(fav) & set(dis)
                if overlap:
                    st.error(f"A color can't be both favorite and avoided: {', '.join(sorted(overlap))}")
                else:
                    prefs.display_name = name.strip()
                    prefs.favorite_colors = [LIB[n] for n in fav]
                    prefs.disliked_colors = [LIB[n] for n in dis]
                    prefs.preferred_styles, prefs.occasion_preferences, prefs.seasons = styles, occ, seasons
                    repo.save_preferences(prefs)
                    session.invalidate()
                    st.success("Saved. Recommendations now follow your taste.")

    with t_beauty:
        with st.form("prefs_beauty"):
            hs = list(HAIR_STYLES)
            hair_style = st.selectbox("Your usual hairstyle", hs, index=hs.index(prefs.hair_style), format_func=HAIR_STYLES.get,
                                      help="Short styles (bob, pixie) make hairstyle suggestions stay short.")
            hc_names = list(HAIR_COLORS) + ["Custom"]
            hc_cur = next((n for n, h in HAIR_COLORS.items() if h == prefs.hair_color), "Custom")
            hc_name = st.selectbox("Hair color", hc_names, index=hc_names.index(hc_cur))
            hc_custom = st.color_picker("Custom hair color (used when 'Custom' is selected)", prefs.hair_color)
            tones = list(SKIN_TONES) + ["Custom"]
            t_cur = next((n for n, h in SKIN_TONES.items() if h == prefs.skin_tone), "Custom")
            tone = st.selectbox("Mannequin skin tone", tones, index=tones.index(t_cur))
            tone_custom = st.color_picker("Custom skin tone", prefs.skin_tone)
            ns = list(NAIL_SHAPES)
            nail_shape = st.selectbox("Favorite nail shape", ns, index=ns.index(prefs.nail_shape), format_func=NAIL_SHAPES.get)
            if st.form_submit_button("Save hair & beauty", type="primary"):
                prefs.hair_style = hair_style
                prefs.hair_color = hc_custom.upper() if hc_name == "Custom" else HAIR_COLORS[hc_name]
                prefs.skin_tone = tone_custom.upper() if tone == "Custom" else SKIN_TONES[tone]
                prefs.nail_shape = nail_shape
                repo.save_preferences(prefs)
                session.invalidate()
                st.success("Saved. New looks will use these defaults.")

    with t_weights:
        st.markdown("These heuristic weights decide how recommendations are ranked. They're normalised to 100%.")
        with st.form("weights"):
            vals = {k: st.slider(COMPONENT_LABELS[k], 0, 60, int(round(prefs.scoring_weights.get(k, v) * 100)), key=f"w_{k}")
                    for k, v in DEFAULT_WEIGHTS.items()}
            c1, c2 = st.columns(2)
            save = c1.form_submit_button("Save weights", type="primary")
            reset = c2.form_submit_button("Reset to defaults")
        if save:
            if sum(vals.values()) == 0:
                st.error("At least one weight must be above zero.")
            else:
                prefs.scoring_weights = {k: v / 100 for k, v in vals.items()}
                repo.save_preferences(prefs)
                session.invalidate()
                st.success("Weights saved.")
        if reset:
            prefs.scoring_weights = dict(DEFAULT_WEIGHTS)
            repo.save_preferences(prefs)
            session.invalidate()
            for k in DEFAULT_WEIGHTS:
                st.session_state.pop(f"w_{k}", None)
            st.rerun()

    with t_account:
        sess = session.current()
        st.markdown(f"Signed in as **{ui.esc(sess.email)}** · backend: `{repo.backend_name}`")
        with st.form("pw", clear_on_submit=True):
            p1 = st.text_input("New password", type="password", autocomplete="new-password")
            p2 = st.text_input("Repeat new password", type="password", autocomplete="new-password")
            if st.form_submit_button("Change password"):
                if p1 != p2:
                    st.error("The passwords don't match.")
                else:
                    try:
                        change_password(sess, p1)
                        st.success("Password changed.")
                    except AuthError as exc:
                        st.error(str(exc))
        if st.button("Sign out"):
            sign_out(sess)
            session.set_session(None)
            st.rerun()
        st.markdown("---")
        st.markdown("**About** — ColorMuse works entirely without AI: every recommendation comes from a deterministic "
                    "color-theory engine you can inspect (see “Why this works”).")

    with t_data:
        st.markdown("#### Back up your data")
        ui.muted("Free database plans don't include automatic backups — download a backup now and then (monthly is a good habit).")
        include = st.toggle("Include photos", value=True)
        if st.button("Prepare backup"):
            with st.spinner("Collecting your wardrobe, looks and photos…"):
                st.session_state["backup_zip"] = backup.export_zip(repo, include_images=include)
                st.session_state["backup_json"] = json.dumps(backup.export_data(repo), indent=2, default=str)
        if st.session_state.get("backup_zip"):
            c1, c2 = st.columns(2)
            c1.download_button("⬇️ Download backup (.zip)", st.session_state["backup_zip"],
                               f"colormuse-backup-{date.today().isoformat()}.zip", "application/zip", type="primary")
            c2.download_button("Data only (.json)", st.session_state["backup_json"],
                               f"colormuse-data-{date.today().isoformat()}.json", "application/json")

        st.markdown("#### Restore from a backup")
        ui.muted("Adds the backup's pieces, looks and collections to this account (nothing existing is overwritten).")
        up = st.file_uploader("ColorMuse backup .zip", type=["zip"], key="restore_zip")
        if up and st.button("Restore"):
            try:
                with st.spinner("Restoring…"):
                    counts = backup.import_zip(repo, up.getvalue())
                session.invalidate()
                st.success(f"Restored {counts['items']} pieces ({counts['photos']} photos), {counts['outfits']} looks "
                           f"and {counts['collections']} collections.")
            except ValueError as exc:
                st.error(str(exc))

        st.markdown("#### Delete all personal data")
        st.warning("This permanently deletes your wardrobe, photos, looks, collections, history and preferences. "
                   "Download a backup first. Your sign-in account itself remains.")
        confirm = st.text_input("Type DELETE to confirm", key="del_confirm")
        if st.button("Delete everything", disabled=confirm != "DELETE"):
            with st.spinner("Deleting…"):
                repo.delete_all_data()
            session.invalidate()
            st.session_state.pop("studio_outfit", None)
            st.success("All personal data has been deleted.")


render()
