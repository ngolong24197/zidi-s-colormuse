"""Editorial styling layered on top of the Streamlit theme (.streamlit/config.toml)."""

from __future__ import annotations

import streamlit as st

PALETTE = {
    "ivory": "#F8F4EF", "blush": "#E8C9C5", "rose": "#B77E79", "burgundy": "#713E4A",
    "taupe": "#C8AD91", "charcoal": "#302B2B",
}

CSS = """
<style>
:root {
  --cm-ivory:#F8F4EF; --cm-blush:#E8C9C5; --cm-rose:#B77E79; --cm-burgundy:#713E4A;
  --cm-taupe:#C8AD91; --cm-charcoal:#302B2B; --cm-card:#FFFDFB; --cm-line:#E9DBD3;
}
/* page width & breathing room */
.block-container { padding-top: 1.2rem; padding-bottom: 4rem; max-width: 1180px; }
h1, h2, h3 { letter-spacing: .01em; color: var(--cm-burgundy) !important; }
h1 { font-weight: 600 !important; }
p, li, label, .stMarkdown { line-height: 1.6; }

/* Editorial header */
.cm-eyebrow { font-size:.78rem; letter-spacing:.22em; text-transform:uppercase; color:var(--cm-rose); margin-bottom:.1rem; }
.cm-title { font-family:"Cormorant Garamond", Georgia, serif; font-size:clamp(2rem, 5vw, 3rem); font-weight:600;
            color:var(--cm-burgundy); line-height:1.05; margin:0 0 .35rem 0; }
.cm-sub { color:#6B5F5C; font-size:1.02rem; margin-bottom:1.1rem; max-width:44rem; }

/* Cards */
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 18px !important; }
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div > .cm-card-marker) {
  background: var(--cm-card); border-color: var(--cm-line) !important;
  box-shadow: 0 6px 22px rgba(113,62,74,.06); transition: box-shadow .25s ease, transform .25s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div > .cm-card-marker):hover {
  box-shadow: 0 10px 28px rgba(113,62,74,.12);
}
.cm-card-marker { display:none; }

/* Swatches */
.cm-swatch-row { display:flex; flex-wrap:wrap; gap:.55rem; align-items:flex-start; margin:.25rem 0 .5rem; }
.cm-swatch { display:flex; flex-direction:column; align-items:center; width:74px; text-align:center; }
.cm-swatch .dot { width:46px; height:46px; border-radius:50%; border:2px solid #fff;
                  box-shadow:0 0 0 1px var(--cm-line), 0 3px 8px rgba(48,43,43,.12); }
.cm-swatch .nm { font-size:.74rem; margin-top:.3rem; color:var(--cm-charcoal); line-height:1.15; }
.cm-swatch .hx { font-size:.66rem; color:#8B7F7B; letter-spacing:.04em; }
.cm-chip { display:inline-flex; align-items:center; gap:.35rem; background:#fff; border:1px solid var(--cm-line);
           border-radius:999px; padding:.15rem .6rem .15rem .2rem; font-size:.8rem; margin:0 .3rem .3rem 0; }
.cm-chip i { width:16px; height:16px; border-radius:50%; display:inline-block; box-shadow:0 0 0 1px rgba(0,0,0,.08); }

/* Score badge & bars */
.cm-score { display:inline-flex; align-items:baseline; gap:.2rem; background:var(--cm-burgundy); color:#fff;
            border-radius:999px; padding:.18rem .7rem; font-weight:500; font-size:.9rem; }
.cm-score small { opacity:.8; font-size:.7rem; }
.cm-rule { display:inline-block; font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; color:var(--cm-rose);
           border:1px solid var(--cm-blush); border-radius:999px; padding:.05rem .55rem; margin-left:.35rem; }
.cm-bar { display:flex; align-items:center; gap:.5rem; font-size:.78rem; margin:.15rem 0; }
.cm-bar span:first-child { width:9.5rem; color:#6B5F5C; }
.cm-bar .track { flex:1; height:6px; background:#F1E4DF; border-radius:6px; overflow:hidden; }
.cm-bar .fill { height:100%; background:linear-gradient(90deg, var(--cm-blush), var(--cm-rose)); }
.cm-bar span:last-child { width:2.4rem; text-align:right; }

/* Hero */
.cm-hero-text { padding: .5rem 0; }
.cm-muted { color:#7B6F6B; font-size:.9rem; }
.cm-empty { text-align:center; padding:2.2rem 1rem; color:#7B6F6B; border:1px dashed var(--cm-taupe);
            border-radius:18px; background:rgba(255,253,251,.6); }
.cm-empty b { font-family:"Cormorant Garamond", serif; font-size:1.5rem; color:var(--cm-burgundy); display:block; }

/* Buttons: soft, touch-friendly */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  border-radius: 999px !important; min-height: 2.75rem; padding: .35rem 1.2rem; transition: all .2s ease;
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] { box-shadow: 0 4px 14px rgba(113,62,74,.25); }
img { border-radius: 14px; }
.cm-mannequin svg { max-width: 100%; height: auto; display:block; margin: 0 auto; }

/* Tabs */
button[data-baseweb="tab"] { font-size: .95rem; }

/* Mobile */
@media (max-width: 640px) {
  .block-container { padding-left: .8rem; padding-right: .8rem; padding-top: .6rem; }
  .cm-swatch { width: 64px; }
  .cm-swatch .dot { width: 40px; height: 40px; }
  .cm-bar span:first-child { width: 7.5rem; }
}
#MainMenu, footer { visibility: hidden; }
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
