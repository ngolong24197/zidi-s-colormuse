"""Settings: language, fashion & beauty preferences, scoring weights, account, data export/restore/delete."""

from __future__ import annotations

import json
from datetime import date

import streamlit as st

from src.components import ui
from src.i18n import LANGUAGES, _, format_func, get_language, label
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

SKIN_TONES = {"Porcelain": "#F3DCCB", "Light": "#E8C4A8", "Medium": "#D2A07C", "Tan": "#B07A55",
              "Deep": "#7E5139", "Rich": "#5A3726"}


@ui.guarded
def render() -> None:
    ui.header(_("Settings"), _("Make ColorMuse yours."))
    repo = session.repo()
    prefs = session.preferences()
    t_style, t_beauty, t_weights, t_account, t_data = st.tabs(
        [_("Style profile"), _("Hair & beauty"), _("Scoring"), _("Account"), _("Data")])

    with t_style:
        st.markdown("##### " + _("Language"))
        langs = list(LANGUAGES)
        choice = st.radio(_("Language"), langs, index=langs.index(get_language()), horizontal=True,
                          format_func=LANGUAGES.get, key=f"set_lang_{get_language()}", label_visibility="collapsed")
        if choice != get_language():
            session.set_language(choice)
            st.rerun()
        ui.muted(_("Tip: bookmark the page after choosing — the link remembers your language."))
        with st.form("prefs_style"):
            name = st.text_input(_("What should I call you?"), prefs.display_name, max_chars=40)
            fav = ui.color_multi_choice(_("Favorite colors"), prefs.favorite_colors, key="pref_fav")
            dis = ui.color_multi_choice(_("Colors you prefer to avoid"), prefs.disliked_colors, key="pref_dis")
            styles = ui.multi_choice(_("Preferred styles"), list(STYLES), prefs.preferred_styles, "pref_styles", "style")
            occ = ui.multi_choice(_("Occasions you dress for most"), list(OCCASIONS), prefs.occasion_preferences, "pref_occ", "occasion")
            seasons = ui.multi_choice(_("Seasons you're styling for"), list(SEASONS), prefs.seasons, "pref_seasons", "season")
            if st.form_submit_button(_("Save style profile"), type="primary"):
                overlap = set(fav) & set(dis)
                if overlap:
                    st.error(_("A color can't be both favorite and avoided: {colors}",
                               colors=", ".join(sorted(ui.cname(h) for h in overlap))))
                else:
                    prefs.display_name = name.strip()
                    prefs.favorite_colors, prefs.disliked_colors = fav, dis
                    prefs.preferred_styles, prefs.occasion_preferences, prefs.seasons = styles, occ, seasons
                    repo.save_preferences(prefs)
                    session.invalidate()
                    st.success(_("Saved. Recommendations now follow your taste."))

    with t_beauty:
        with st.form("prefs_beauty"):
            hs = list(HAIR_STYLES)
            hair_style = st.selectbox(_("Your usual hairstyle"), hs, index=hs.index(prefs.hair_style), format_func=format_func("hair"),
                                      help=_("Short styles (bob, pixie) make hairstyle suggestions stay short."))
            hc_names = list(HAIR_COLORS) + ["Custom"]
            hc_cur = next((n for n, h in HAIR_COLORS.items() if h == prefs.hair_color), "Custom")
            hc_name = st.selectbox(_("Hair color"), hc_names, index=hc_names.index(hc_cur),
                                   format_func=lambda n: _("Custom") if n == "Custom" else label("hair_color", n))
            hc_custom = st.color_picker(_("Custom hair color (used when 'Custom' is selected)"), prefs.hair_color)
            tones = list(SKIN_TONES) + ["Custom"]
            t_cur = next((n for n, h in SKIN_TONES.items() if h == prefs.skin_tone), "Custom")
            tone = st.selectbox(_("Mannequin skin tone"), tones, index=tones.index(t_cur),
                                format_func=lambda n: _("Custom") if n == "Custom" else label("skin", n))
            tone_custom = st.color_picker(_("Custom skin tone"), prefs.skin_tone)
            ns = list(NAIL_SHAPES)
            nail_shape = st.selectbox(_("Favorite nail shape"), ns, index=ns.index(prefs.nail_shape), format_func=format_func("nail"))
            if st.form_submit_button(_("Save hair & beauty"), type="primary"):
                prefs.hair_style = hair_style
                prefs.hair_color = hc_custom.upper() if hc_name == "Custom" else HAIR_COLORS[hc_name]
                prefs.skin_tone = tone_custom.upper() if tone == "Custom" else SKIN_TONES[tone]
                prefs.nail_shape = nail_shape
                repo.save_preferences(prefs)
                session.invalidate()
                st.success(_("Saved. New looks will use these defaults."))

    with t_weights:
        st.markdown(_("These heuristic weights decide how recommendations are ranked. They're normalised to 100%."))
        with st.form("weights"):
            vals = {k: st.slider(label("component", k), 0, 60, int(round(prefs.scoring_weights.get(k, v) * 100)), key=f"w_{k}")
                    for k, v in DEFAULT_WEIGHTS.items()}
            c1, c2 = st.columns(2)
            save = c1.form_submit_button(_("Save weights"), type="primary")
            reset = c2.form_submit_button(_("Reset to defaults"))
        if save:
            if sum(vals.values()) == 0:
                st.error(_("At least one weight must be above zero."))
            else:
                prefs.scoring_weights = {k: v / 100 for k, v in vals.items()}
                repo.save_preferences(prefs)
                session.invalidate()
                st.success(_("Weights saved."))
        if reset:
            prefs.scoring_weights = dict(DEFAULT_WEIGHTS)
            repo.save_preferences(prefs)
            session.invalidate()
            for k in DEFAULT_WEIGHTS:
                st.session_state.pop(f"w_{k}", None)
            st.rerun()

    with t_account:
        sess = session.current()
        st.markdown(_("Signed in as **{email}**", email=ui.esc(sess.email)) + f" · `{repo.backend_name}`")
        with st.form("pw", clear_on_submit=True):
            p1 = st.text_input(_("New password"), type="password", autocomplete="new-password")
            p2 = st.text_input(_("Repeat new password"), type="password", autocomplete="new-password")
            if st.form_submit_button(_("Change password")):
                if p1 != p2:
                    st.error(_("The passwords don't match."))
                else:
                    try:
                        change_password(sess, p1)
                        st.success(_("Password changed."))
                    except AuthError as exc:
                        st.error(str(exc))
        if st.button(_("Sign out")):
            sign_out(sess)
            session.set_session(None)
            st.rerun()
        st.markdown("---")
        st.markdown(_("**About** — ColorMuse works entirely without AI: every recommendation comes from a deterministic "
                      "color-theory engine you can inspect (see “Why this works”)."))

    with t_data:
        st.markdown("#### " + _("Back up your data"))
        ui.muted(_("Free database plans don't include automatic backups — download a backup now and then (monthly is a good habit)."))
        include = st.toggle(_("Include photos"), value=True)
        if st.button(_("Prepare backup")):
            with st.spinner(_("Collecting your wardrobe, looks and photos…")):
                st.session_state["backup_zip"] = backup.export_zip(repo, include_images=include)
                st.session_state["backup_json"] = json.dumps(backup.export_data(repo), indent=2, default=str)
        if st.session_state.get("backup_zip"):
            c1, c2 = st.columns(2)
            c1.download_button("⬇️ " + _("Download backup (.zip)"), st.session_state["backup_zip"],
                               f"colormuse-backup-{date.today().isoformat()}.zip", "application/zip", type="primary")
            c2.download_button(_("Data only (.json)"), st.session_state["backup_json"],
                               f"colormuse-data-{date.today().isoformat()}.json", "application/json")

        st.markdown("#### " + _("Restore from a backup"))
        ui.muted(_("Adds the backup's pieces, looks and collections to this account (nothing existing is overwritten)."))
        up = st.file_uploader(_("ColorMuse backup .zip"), type=["zip"], key="restore_zip")
        if up and st.button(_("Restore")):
            try:
                with st.spinner(_("Restoring…")):
                    counts = backup.import_zip(repo, up.getvalue())
                session.invalidate()
                st.success(_("Restored {items} pieces ({photos} photos), {outfits} looks and {collections} collections.", **counts))
            except ValueError as exc:
                st.error(_(str(exc)))

        st.markdown("#### " + _("Delete all personal data"))
        st.warning(_("This permanently deletes your wardrobe, photos, looks, collections, history and preferences. "
                     "Download a backup first. Your sign-in account itself remains."))
        confirm = st.text_input(_("Type DELETE to confirm"), key="del_confirm")
        if st.button(_("Delete everything"), disabled=confirm != "DELETE"):
            with st.spinner(_("Deleting…")):
                repo.delete_all_data()
            session.invalidate()
            st.session_state.pop("studio_outfit", None)
            st.success(_("All personal data has been deleted."))


render()
