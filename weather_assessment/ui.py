from __future__ import annotations

import html

import streamlit as st

# Light engineering dashboard palette retained from v0.5.2.
NAVY = "#0B4778"
NAVY_2 = "#126098"
TEAL = "#079C97"
TEAL_DARK = "#087C79"
BLUE = "#1C67C9"
GREEN = "#139A55"
RED = "#C8332B"
AMBER = "#D88700"
TEXT = "#13213A"
MUTED = "#66758A"


def apply_theme() -> None:
    st.markdown(
        f"""
<style>
:root {{ --mfa-navy:{NAVY}; --mfa-teal:{TEAL}; --mfa-text:{TEXT}; }}
html, body, [class*="css"] {{ font-family: Inter, "Segoe UI", Arial, sans-serif; }}
.stApp {{ background:#F7F9FC; color:{TEXT}; }}
[data-testid="stSidebar"] {{
    background:linear-gradient(180deg, {NAVY} 0%, #0A3962 100%);
    border-right:0;
}}
[data-testid="stSidebar"] * {{ color:#EEF7FF; }}
[data-testid="stSidebar"] hr {{ border-color:rgba(255,255,255,.16); }}
.block-container {{ max-width:1500px; padding-top:1.35rem; padding-bottom:3rem; }}
h1,h2,h3,h4 {{ color:{TEXT}; letter-spacing:-.02em; }}
h1 {{ font-size:2rem !important; margin-bottom:.25rem !important; }}
p,label,.stCaption {{ color:{MUTED}; }}

/* Brand and grouped sidebar navigation */
.mfa-brand {{ display:flex; gap:.65rem; align-items:center; padding:.35rem .1rem .75rem; }}
.mfa-brand-title {{ font-weight:750; font-size:1rem; line-height:1.2; }}
.mfa-brand-sub {{ font-size:.75rem; opacity:.82; margin-top:.18rem; overflow-wrap:anywhere; }}
.mfa-nav-heading {{ font-size:.66rem; letter-spacing:.14em; font-weight:800; opacity:.66; margin:.72rem .25rem .22rem; }}
[data-testid="stSidebar"] .stButton {{ margin:.04rem 0; }}
[data-testid="stSidebar"] .stButton button {{
    width:100%; justify-content:flex-start; text-align:left;
    border-radius:.48rem; min-height:2.28rem; padding:.46rem .62rem;
    font-weight:640; font-size:.83rem;
    background:transparent !important;
    color:#F5FBFF !important;
    border:1px solid transparent !important;
    box-shadow:none !important;
}}
[data-testid="stSidebar"] .stButton button:hover {{
    background:rgba(255,255,255,.10) !important;
    border-color:rgba(255,255,255,.12) !important;
}}
[data-testid="stSidebar"] .stButton button[kind="primary"] {{
    background:linear-gradient(90deg, rgba(7,156,151,.96), rgba(18,96,152,.88)) !important;
    color:#FFFFFF !important;
    border-color:rgba(255,255,255,.24) !important;
}}
[data-testid="stSidebar"] .stButton button * {{ color:#F5FBFF !important; }}
[data-testid="stSidebar"] .stButton button:disabled {{ opacity:.55; }}
.mfa-side-status {{
    background:rgba(255,255,255,.10); border:1px solid rgba(255,255,255,.19);
    border-radius:.55rem; padding:.62rem .7rem; font-size:.74rem; line-height:1.45;
    color:#EAF6FF; margin:.5rem 0;
}}
.mfa-side-footer {{ font-size:.69rem; opacity:.68; margin-top:.75rem; padding-top:.55rem; text-align:center; border-top:1px solid rgba(255,255,255,.14); }}

/* Page header */
.mfa-page-head {{ margin:.05rem 0 1.15rem; }}
.mfa-breadcrumb {{ color:{MUTED}; font-size:.82rem; margin:.1rem 0 .55rem; }}
.mfa-breadcrumb b {{ color:{TEAL_DARK}; }}
.mfa-page-title {{ color:{TEXT}; font-size:2rem; font-weight:810; letter-spacing:-.035em; line-height:1.12; }}
.mfa-subtitle {{ color:{MUTED}; margin-top:.35rem; max-width:1000px; }}

/* Summary and workflow cards */
.mfa-card {{
    background:#FFFFFF; border:1px solid #E2E8F0; border-radius:.72rem;
    padding:1rem 1.05rem; box-shadow:0 2px 8px rgba(15,35,60,.045); height:100%;
}}
.mfa-card-title {{ color:#24324A; font-size:.78rem; font-weight:700; margin-bottom:.45rem; }}
.mfa-card-value {{ color:{TEXT}; font-size:1.63rem; font-weight:800; line-height:1.08; }}
.mfa-card-value-wrap {{ display:block; font-size:1.12rem; line-height:1.28; overflow-wrap:anywhere; word-break:break-word; white-space:normal; }}
.mfa-card-unit {{ color:{MUTED}; font-size:.9rem; font-weight:650; margin-left:.15rem; }}
.mfa-card-note {{ color:{MUTED}; font-size:.78rem; margin-top:.45rem; }}
.mfa-card-equal {{ min-height:10.15rem; display:flex; flex-direction:column; }}
.mfa-card-equal .mfa-card-note {{ min-height:2.45rem; }}
.mfa-workflow-card {{ min-height:12.5rem; display:flex; flex-direction:column; justify-content:flex-start; }}
.mfa-workflow-number {{
    width:2rem; height:2rem; border-radius:50%; display:flex; align-items:center; justify-content:center;
    background:#E1F6F4; color:{TEAL_DARK}; font-weight:800; margin-bottom:.7rem;
}}
.mfa-workflow-title {{ font-size:1rem; font-weight:780; color:{TEXT}; line-height:1.25; min-height:2.5rem; }}
.mfa-workflow-body {{ color:{MUTED}; font-size:.79rem; line-height:1.45; margin-top:.55rem; }}
.mfa-panel-title {{ font-size:1rem; font-weight:750; color:#26364F; margin:.1rem 0 .75rem; }}
.mfa-note {{ border-left:4px solid {TEAL}; padding:.7rem .85rem; background:#EFFBFA; border-radius:.35rem; color:#365268; }}
.mfa-footer {{ margin-top:2rem; color:{MUTED}; font-size:.75rem; }}

/* Native Streamlit components */
div[data-testid="stMetric"] {{
    background:#FFFFFF; border:1px solid #E2E8F0; padding:.8rem 1rem;
    border-radius:.7rem; box-shadow:0 2px 8px rgba(15,35,60,.04);
}}
div[data-testid="stMetric"] label {{ color:#526279 !important; }}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {{ color:{TEXT}; font-weight:800; }}
[data-testid="stVerticalBlockBorderWrapper"] > div {{
    background:#FFFFFF; border-color:#E2E8F0 !important; border-radius:.72rem !important;
    box-shadow:0 2px 8px rgba(15,35,60,.04);
}}
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {{
    background:#FFFFFF; border:1px solid #E2E8F0; border-radius:.6rem; overflow:hidden;
}}
[data-baseweb="input"] > div, [data-baseweb="select"] > div, [data-baseweb="textarea"] > div,
[data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"] {{
    background:#FFFFFF !important; border-color:#CBD5E1 !important;
}}
input, textarea, [data-baseweb="select"] span {{ color:{TEXT} !important; }}
[data-baseweb="popover"] * {{ color:{TEXT}; }}
.stButton button, .stDownloadButton button {{ border-radius:.45rem; font-weight:650; }}
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"],
button[data-testid="stBaseButton-primary"] {{
    background:{TEAL} !important; border-color:{TEAL} !important; color:#FFFFFF !important;
}}
.stButton button[kind="primary"] *, .stDownloadButton button[kind="primary"] *,
button[data-testid="stBaseButton-primary"] * {{ color:#FFFFFF !important; }}
.stButton button[kind="primary"]:hover, .stDownloadButton button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover {{ background:{TEAL_DARK} !important; border-color:{TEAL_DARK} !important; }}

/* Campaign-settings form action: blue button with white text. */
div[data-testid="stForm"] button[kind="secondary"],
div[data-testid="stForm"] button[data-testid="stBaseButton-secondaryFormSubmit"] {{
    background:{BLUE} !important; border-color:{BLUE} !important; color:#FFFFFF !important;
}}
div[data-testid="stForm"] button[kind="secondary"] *,
div[data-testid="stForm"] button[data-testid="stBaseButton-secondaryFormSubmit"] * {{ color:#FFFFFF !important; }}
div[data-testid="stForm"] button[kind="secondary"]:hover,
div[data-testid="stForm"] button[data-testid="stBaseButton-secondaryFormSubmit"]:hover {{
    background:#1557AA !important; border-color:#1557AA !important;
}}

/* Keep weather-location tabs close to the simpler v0.5.2 presentation. */
.stTabs [data-baseweb="tab-list"] {{ gap:1.25rem; background:transparent; padding:0; border-bottom:1px solid #D7E0E9; }}
.stTabs [data-baseweb="tab"] {{ color:#34445C; padding:.55rem .15rem; }}
.stTabs [aria-selected="true"] {{ color:{TEAL_DARK} !important; font-weight:750; }}
.stExpander {{ border:1px solid #E2E8F0 !important; border-radius:.65rem !important; background:#FFFFFF; }}
[data-testid="stFileUploader"] section {{ background:#FFFFFF; border:1px dashed #AFC0D0; border-radius:.65rem; }}
[data-testid="stAlert"] {{ border-radius:.65rem; }}
[data-testid="stProgress"] > div > div {{ background:linear-gradient(90deg,{TEAL},{BLUE}) !important; }}
.mfa-status {{ display:inline-block; border-radius:1rem; padding:.15rem .52rem; font-size:.72rem; font-weight:700; }}
.mfa-pass {{ color:#087443; background:#DDF6E9; }}
.mfa-warning {{ color:#8B5A00; background:#FFF1C9; }}
.mfa-error {{ color:#A51F1F; background:#FFE0E0; }}
.mfa-info {{ color:#195FAE; background:#DDEBFF; }}
.js-plotly-plot,.plot-container {{ border-radius:.65rem; overflow:hidden; }}
.mfa-section-gap {{ height:24px; }}
.mfa-section-gap-small {{ height:14px; }}
[data-testid="stHeader"] {{ background:rgba(247,249,252,.88); }}

@media (max-width:900px) {{
  .mfa-page-title {{ font-size:1.7rem; }}
  .mfa-workflow-card {{ min-height:auto; }}
}}
</style>
""",
        unsafe_allow_html=True,
    )


def brand(version: str, project_name: str = "") -> None:
    st.markdown(
        f"""
<div class="mfa-brand">
<svg width="38" height="38" viewBox="0 0 64 64" aria-label="Wind turbine logo">
 <path d="M4 51 C14 47 23 55 33 51 S52 47 60 52" fill="none" stroke="#20C7BF" stroke-width="3"/>
 <path d="M8 57 C18 53 27 61 37 57 S53 54 60 58" fill="none" stroke="#75DAD5" stroke-width="2.4"/>
 <line x1="32" y1="22" x2="32" y2="50" stroke="#F4FAFF" stroke-width="2.5"/>
 <path d="M32 21 L31 5 C35 10 35 16 32 21Z" fill="#F4FAFF"/>
 <path d="M33 22 L49 17 C45 22 39 24 33 22Z" fill="#F4FAFF"/>
 <path d="M31 23 L18 33 C19 27 24 23 31 23Z" fill="#F4FAFF"/>
 <circle cx="32" cy="22" r="3" fill="#20C7BF"/>
</svg>
<div><div class="mfa-brand-title">Weather Assessment — v{html.escape(version)}</div><div class="mfa-brand-sub">{html.escape(project_name.strip() or "Untitled project")}</div></div>
</div>
""",
        unsafe_allow_html=True,
    )


def nav_heading(text: str) -> None:
    st.markdown(f'<div class="mfa-nav-heading">{html.escape(text.upper())}</div>', unsafe_allow_html=True)


def sidebar_status(text: str) -> None:
    st.markdown(f'<div class="mfa-side-status">{html.escape(text)}</div>', unsafe_allow_html=True)


def sidebar_footer(text: str = "") -> None:
    st.markdown(f'<div class="mfa-side-footer">{html.escape(text)}</div>', unsafe_allow_html=True)


def page_header(number: str, title: str, subtitle: str = "") -> None:
    sub = f'<div class="mfa-subtitle">{html.escape(subtitle)}</div>' if subtitle else ""
    st.markdown(
        f"""
<div class="mfa-page-head">
  <div class="mfa-breadcrumb"><b>Overview</b> &nbsp;/&nbsp; {html.escape(title)}</div>
  <div class="mfa-page-title">{html.escape(number)} — {html.escape(title)}</div>
  {sub}
</div>
""",
        unsafe_allow_html=True,
    )


def metric_card(
    label: str,
    value: str,
    unit: str = "",
    note: str = "",
    accent: str | None = None,
    *,
    wrap: bool = False,
    tooltip: str = "",
    equal_height: bool = False,
) -> None:
    color = accent or TEXT
    value_class = "mfa-card-value mfa-card-value-wrap" if wrap else "mfa-card-value"
    card_class = "mfa-card mfa-card-equal" if equal_height else "mfa-card"
    title_attr = f' title="{html.escape(tooltip or value, quote=True)}"' if tooltip or wrap else ""
    st.markdown(
        f"""
<div class="{card_class}">
 <div class="mfa-card-title">{html.escape(label)}</div>
 <div><span class="{value_class}" style="color:{color}"{title_attr}>{html.escape(value)}</span><span class="mfa-card-unit">{html.escape(unit)}</span></div>
 <div class="mfa-card-note">{html.escape(note)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def section_gap(size: str = "large") -> None:
    css = "mfa-section-gap-small" if size == "small" else "mfa-section-gap"
    st.markdown(f'<div class="{css}"></div>', unsafe_allow_html=True)


def workflow_step_card(number: str, title: str, body: str) -> None:
    st.markdown(
        f"""
<div class="mfa-card mfa-workflow-card">
 <div class="mfa-workflow-number">{html.escape(number)}</div>
 <div class="mfa-workflow-title">{html.escape(title)}</div>
 <div class="mfa-workflow-body">{html.escape(body)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def status_badge(text: str, kind: str = "pass") -> str:
    css = {"pass": "mfa-pass", "warning": "mfa-warning", "error": "mfa-error", "info": "mfa-info"}.get(kind, "mfa-info")
    return f'<span class="mfa-status {css}">{html.escape(text)}</span>'


def fixed_bottom_turbine_html(title: str = "Running assessment…", subtitle: str = "Historical scenarios are being calculated.") -> str:
    """Compact fixed-bottom turbine used as the calculation indicator."""
    return f"""
<style>
.mfa-runbox {{
  background:#FFFFFF; border:1px solid #E2E8F0; border-radius:.72rem; padding:.72rem .9rem;
  display:flex; align-items:center; gap:.9rem; box-shadow:0 2px 8px rgba(15,35,60,.045); margin:.2rem 0 .7rem;
}}
.mfa-runbox svg {{ width:88px; height:106px; flex:0 0 auto; }}
.mfa-blades {{ transform-origin:88px 55px; animation:mfa-spin 1.25s linear infinite; }}
@keyframes mfa-spin {{ from{{transform:rotate(0deg)}} to{{transform:rotate(360deg)}} }}
.mfa-run-title {{ font-size:1rem; font-weight:780; color:{TEXT}; }}
.mfa-run-sub {{ color:{MUTED}; font-size:.81rem; margin-top:.22rem; line-height:1.4; }}
</style>
<div class="mfa-runbox">
<svg viewBox="0 0 176 210" role="img" aria-label="Fixed-bottom offshore wind turbine running indicator">
 <defs>
  <linearGradient id="sea" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#CBEAF5"/><stop offset="1" stop-color="#66B4D1"/></linearGradient>
  <linearGradient id="tower" x1="0" x2="1"><stop offset="0" stop-color="#D5E1E8"/><stop offset=".5" stop-color="#FFFFFF"/><stop offset="1" stop-color="#B8CBD7"/></linearGradient>
  <path id="blade" d="M88 55 C84 42 83 22 88 4 C94 22 93 42 88 55 Z"/>
 </defs>
 <rect x="0" y="145" width="176" height="65" rx="10" fill="url(#sea)"/>
 <path d="M0 158 C25 149 44 166 69 157 S116 149 176 159" fill="none" stroke="#E8FAFF" stroke-width="3"/>
 <path d="M0 177 C25 168 44 185 69 176 S116 168 176 178" fill="none" stroke="#9AD8E7" stroke-width="3"/>
 <path d="M82 58 L79 181 L97 181 L94 58 Z" fill="url(#tower)" stroke="#46647A" stroke-width="2"/>
 <rect x="79" y="139" width="18" height="44" rx="2" fill="#E5B01D" stroke="#8E6C0C" stroke-width="2"/>
 <rect x="74" y="134" width="28" height="7" rx="2" fill="#F1C73B" stroke="#8E6C0C" stroke-width="1.5"/>
 <g class="mfa-blades" fill="#F8FBFD" stroke="#35566D" stroke-width="2" stroke-linejoin="round">
  <use href="#blade"/>
  <use href="#blade" transform="rotate(120 88 55)"/>
  <use href="#blade" transform="rotate(240 88 55)"/>
 </g>
 <circle cx="88" cy="55" r="6" fill="#2E5D7A"/>
</svg>
<div><div class="mfa-run-title">{html.escape(title)}</div><div class="mfa-run-sub">{html.escape(subtitle)}</div></div>
</div>
"""


def dataframe_status_style(status_column: str = "Status"):
    def _style(row):
        status = str(row.get(status_column, "")).strip().lower()
        if status == "downtime":
            return ["background-color:#FDE5E5;color:#A51F1F"] * len(row)
        if status == "working":
            return ["background-color:#E5F6EA;color:#17663A"] * len(row)
        return [""] * len(row)
    return _style
