"""Streamlit draft state, navigation and application-service adapters."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
from weather_assessment.defaults import activities_dataframe, safe_to_safe_groups_dataframe, hstp_dataframe, learning_dataframe, locations_dataframe
from weather_assessment.input_workbook import load_project_input_workbook
from weather_assessment.models import Activity, CampaignSettings, HsTpBin, Location, SafeToSafeGroup
from weather_assessment.planning import is_p0_basis
from weather_assessment.ui import apply_theme, brand, dataframe_status_style, nav_heading, sidebar_footer, sidebar_status
from weather_assessment.validation import validate_inputs
from weather_assessment.assessment import run_assessment, simulation_settings, stable_fingerprint
from weather_assessment.weather import load_weather_csv, multi_weather_fingerprint, weather_qa

APP_ROOT = Path(__file__).resolve().parent.parent


APP_VERSION = (APP_ROOT / "VERSION").read_text(encoding="utf-8").strip()


APP_TITLE = f"Weather Assessment — v{APP_VERSION}"


BUILTIN_PROJECT_PATH = APP_ROOT / "Example_Project_Input.xlsx"


BUILTIN_WEATHER_PATH = APP_ROOT / "FM2_WF_weathe_reconciled_Rev.0.csv"


BUILTIN_WEATHER_FILENAME = BUILTIN_WEATHER_PATH.name


BUILTIN_WEATHER_CONFIG = {
    "filename": BUILTIN_WEATHER_FILENAME,
    "skip_rows": 0,
    "delimiter": ",",
    "column_map": {
        "timestamp": "Timestamp",
        "wind10": "Wind10",
        "wind100": "Wind100",
        "hs": "Hs",
        "tp": "Tp",
        "current": "Current",
    },
    "dayfirst": False,
    "date_format": "%Y-%m-%d %H:%M:%S",
}


@st.cache_data(show_spinner=False)
def cached_builtin_project(project_path: str, modified_ns: int):
    del modified_ns
    return load_project_input_workbook(Path(project_path).read_bytes())


@st.cache_data(show_spinner=False)
def cached_builtin_weather(weather_path: str, modified_ns: int):
    del modified_ns
    data = Path(weather_path).read_bytes()
    frame = load_weather_csv(
        data=data,
        skip_rows=0,
        delimiter=",",
        column_map=BUILTIN_WEATHER_CONFIG["column_map"],
        dayfirst=False,
        date_format=BUILTIN_WEATHER_CONFIG["date_format"],
    )
    return data, frame, weather_qa(frame)


PAGES = [
    "00 User guide",
    "01 Weather data",
    "02 Project input",
    "03 Campaign settings",
    "04 Activities",
    "05 Hs–Tp curves",
    "06 Learning curve",
    "07 Generated sequence",
    "08 Run assessment",
    "09 Campaign summary",
    "10 Annual hindcast",
    "11 Planning estimate",
    "12 Monthly statistics",
    "13 Detailed-results summary",
    "14 QA and downtime breakdown",
    "15 Reports and export",
]


NAV_GROUPS = [
    ("Setup", PAGES[0:8]),
    ("Assessment", PAGES[8:9]),
    ("Results", PAGES[9:15]),
    ("Export", PAGES[15:16]),
]


NAV_ICONS = {
    PAGES[0]: "▣", PAGES[1]: "☁", PAGES[2]: "▤", PAGES[3]: "⚙",
    PAGES[4]: "☷", PAGES[5]: "≈", PAGES[6]: "↗", PAGES[7]: "⇥",
    PAGES[8]: "▶", PAGES[9]: "▥", PAGES[10]: "◫", PAGES[11]: "◎",
    PAGES[12]: "▥", PAGES[13]: "◷", PAGES[14]: "✓", PAGES[15]: "⇩",
}


ACTIVITY_COLUMNS = [
    "activity_id", "activity_type", "no_learning_curve", "milestone", "description", "location_id",
    "duration_hours", "weather_window_hours", "safe_to_safe_group", "wind10_limit", "wind100_limit", "hs_limit", "tp_limit",
    "current_limit", "time_start", "time_end", "hstp_curve", "remarks",
]


LOCATION_COLUMNS = ["location_id", "name", "location_type", "timezone", "weather_filename", "notes"]


GROUP_COLUMNS = ["group_id", "description", "assessment_method", "assessment_location", "notes"]


def _result_table(frame: pd.DataFrame):
    """Display calculated decimal values to three places without changing source data."""
    if frame is None or frame.empty:
        return frame
    formats: dict[str, object] = {}
    for column in frame.columns:
        if not pd.api.types.is_numeric_dtype(frame[column]):
            continue
        name = str(column).lower()
        if "%" in name:
            formats[column] = lambda value: "—" if pd.isna(value) else f"{float(value):.3f}%"
        elif "_pct" in name or name.endswith(" pct"):
            formats[column] = lambda value: "—" if pd.isna(value) else f"{float(value) * 100.0:.3f}%"
        elif pd.api.types.is_float_dtype(frame[column]):
            formats[column] = lambda value: "—" if pd.isna(value) else f"{float(value):.3f}"
    return frame.style.format(formats, na_rep="—") if formats else frame


def _qa_styler(frame: pd.DataFrame):
    styled = frame.style.apply(dataframe_status_style("Status"), axis=1)
    formats: dict[str, object] = {}
    for column in frame.columns:
        if pd.api.types.is_float_dtype(frame[column]):
            formats[column] = lambda value: "—" if pd.isna(value) else f"{float(value):.3f}"
    return styled.format(formats, na_rep="—")


def _decimal_axes(fig, *, x: bool = False, y: bool = False):
    """Apply the three-decimal display policy to continuous chart axes."""
    if x:
        fig.update_xaxes(tickformat=",.3f")
    if y:
        fig.update_yaxes(tickformat=",.3f")
    return fig


def _decimal_pie(fig, unit: str = "h"):
    fig.update_traces(
        hovertemplate=f"%{{label}}: %{{value:,.3f}} {unit} (%{{percent:.3%}})<extra></extra>"
    )
    return fig


def initialise_state() -> None:
    if st.session_state.get("initialised_app_version") != APP_VERSION:
        restore_builtin_example()
        st.session_state.initialised_app_version = APP_VERSION
        st.session_state.selected_page = PAGES[0]
    elif "selected_page" not in st.session_state:
        st.session_state.selected_page = PAGES[0]


def clear_results() -> None:
    st.session_state.assessment_run = None
    st.session_state.detail_cache = {}
    st.session_state.export_cache = {}
    st.session_state.aligned_weather = None
    st.session_state.sequence = None
    st.session_state.results = None
    st.session_state.detailed_result = None
    st.session_state.p0_summary = None
    st.session_state.run_mode = None
    st.session_state.run_fingerprint = None


def dataframe_to_locations(frame: pd.DataFrame) -> list[Location]:
    clean = frame.copy().dropna(subset=["location_id"])
    output: list[Location] = []
    for _, row in clean.iterrows():
        data = {column: row.get(column) for column in LOCATION_COLUMNS}
        output.append(Location.from_dict(data))
    return output


def dataframe_to_activities(frame: pd.DataFrame) -> list[Activity]:
    clean = frame.copy().dropna(subset=["activity_id", "activity_type"])
    output: list[Activity] = []
    for _, row in clean.iterrows():
        data = {column: row.get(column) for column in ACTIVITY_COLUMNS}
        data["no_learning_curve"] = False if pd.isna(data.get("no_learning_curve")) else bool(data.get("no_learning_curve"))
        data["milestone"] = False if pd.isna(data.get("milestone")) else bool(data.get("milestone"))
        output.append(Activity.from_dict(data))
    return sorted(output, key=lambda item: item.activity_id)


def dataframe_to_hstp(frame: pd.DataFrame) -> list[HsTpBin]:
    clean = frame.dropna(subset=["curve", "tp_from", "tp_to", "hs_max"])
    return [HsTpBin(str(row["curve"]), float(row["tp_from"]), float(row["tp_to"]), float(row["hs_max"])) for _, row in clean.iterrows()]


def dataframe_to_learning(frame: pd.DataFrame) -> dict[int, float]:
    clean = frame.dropna(subset=["cycle"])
    return {int(row["cycle"]): float(row["multiplier"] if pd.notna(row["multiplier"]) else 1.0) for _, row in clean.iterrows()}


def dataframe_to_safe_to_safe_groups(frame: pd.DataFrame) -> list[SafeToSafeGroup]:
    if frame is None or frame.empty:
        return []
    clean = frame.copy().dropna(subset=["group_id"])
    output: list[SafeToSafeGroup] = []
    for _, row in clean.iterrows():
        output.append(SafeToSafeGroup.from_dict({column: row.get(column) for column in GROUP_COLUMNS}))
    return sorted(output, key=lambda item: item.group_id)


def current_inputs() -> tuple[CampaignSettings, list[Location], list[Activity], list[HsTpBin], dict[int, float], list[SafeToSafeGroup]]:
    return (
        st.session_state.settings,
        dataframe_to_locations(st.session_state.locations_df),
        dataframe_to_activities(st.session_state.activities_df),
        dataframe_to_hstp(st.session_state.hstp_df),
        dataframe_to_learning(st.session_state.learning_df),
        dataframe_to_safe_to_safe_groups(st.session_state.safe_to_safe_groups_df),
    )


def safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(value)).strip("_") or "weather_assessment"


def default_column(columns: list[str], needles: list[str], fallback: int) -> str:
    normal = {column: re.sub(r"[^a-z0-9]", "", str(column).lower()) for column in columns}
    for needle in needles:
        token = re.sub(r"[^a-z0-9]", "", needle.lower())
        for column, clean in normal.items():
            if token in clean:
                return column
    return columns[min(fallback, len(columns) - 1)]


def input_fingerprint() -> str:
    settings, locations, activities, bins, learning, groups = current_inputs()
    payload = {
        "settings": simulation_settings(settings),
        "locations": [item.to_dict() for item in locations],
        "activities": [item.to_dict() for item in activities],
        "bins": [item.to_dict() for item in bins],
        "learning": learning,
        "safe_to_safe_groups": [item.to_dict() for item in groups],
        "weather": multi_weather_fingerprint(st.session_state.weather_data) if st.session_state.weather_data else "",
    }
    return stable_fingerprint(payload)


def stale_results_warning() -> None:
    if st.session_state.results is not None and st.session_state.run_fingerprint != input_fingerprint():
        st.warning("Inputs have changed since the latest assessment. Existing results are no longer current. Run the assessment again.")


def show_validation(errors: list[str]) -> None:
    if not errors:
        st.success("All required checks passed.")
        return
    st.error("Resolve the following items before running:")
    for error in errors:
        st.write(f"• {error}")


def apply_project_inputs(
    settings: CampaignSettings,
    locations: list[Location],
    activities: list[Activity],
    bins: list[HsTpBin],
    learning: dict[int, float],
    safe_to_safe_groups: list[SafeToSafeGroup] | None = None,
) -> None:
    st.session_state.settings = settings
    st.session_state.locations_df = locations_dataframe(locations)
    st.session_state.activities_df = activities_dataframe(activities)
    st.session_state.hstp_df = hstp_dataframe(bins)
    st.session_state.learning_df = learning_dataframe(learning)
    st.session_state.safe_to_safe_groups_df = safe_to_safe_groups_dataframe(safe_to_safe_groups or [])
    clear_results()


def restore_builtin_example() -> None:
    if not BUILTIN_PROJECT_PATH.exists():
        raise FileNotFoundError(f"Built-in project workbook was not found: {BUILTIN_PROJECT_PATH.name}")
    if not BUILTIN_WEATHER_PATH.exists():
        raise FileNotFoundError(f"Built-in weather file was not found: {BUILTIN_WEATHER_PATH.name}")

    settings, locations, activities, bins, learning, groups = cached_builtin_project(
        str(BUILTIN_PROJECT_PATH), BUILTIN_PROJECT_PATH.stat().st_mtime_ns
    )
    data, frame, qa = cached_builtin_weather(
        str(BUILTIN_WEATHER_PATH), BUILTIN_WEATHER_PATH.stat().st_mtime_ns
    )
    st.session_state.settings = settings
    st.session_state.locations_df = locations_dataframe(locations)
    st.session_state.activities_df = activities_dataframe(activities)
    st.session_state.hstp_df = hstp_dataframe(bins)
    st.session_state.learning_df = learning_dataframe(learning)
    st.session_state.safe_to_safe_groups_df = safe_to_safe_groups_dataframe(groups)
    st.session_state.weather_files = {item.location_id: data for item in locations}
    st.session_state.weather_configs = {item.location_id: dict(BUILTIN_WEATHER_CONFIG) for item in locations}
    st.session_state.weather_data = {item.location_id: frame for item in locations}
    st.session_state.weather_qa = {item.location_id: qa for item in locations}
    st.session_state.aligned_weather = None
    st.session_state.sequence = None
    st.session_state.results = None
    st.session_state.detailed_result = None
    st.session_state.p0_summary = None
    st.session_state.run_mode = None
    st.session_state.run_fingerprint = None
    st.session_state.last_run_at = None
    st.session_state.run_history = []
    st.session_state.project_import_message = None
    clear_results()


def load_saved_weather(location_id: str, data: bytes, config: dict[str, Any]) -> None:
    frame = load_weather_csv(
        data=data,
        skip_rows=int(config.get("skip_rows", 0)),
        delimiter=config.get("delimiter", "Auto"),
        column_map=config["column_map"],
        dayfirst=bool(config.get("dayfirst", True)),
        date_format=config.get("date_format") or None,
        source_timezone=config.get("source_timezone", "UTC"),
    )
    qa = weather_qa(frame)
    st.session_state.weather_files[location_id] = data
    st.session_state.weather_configs[location_id] = config
    st.session_state.weather_data[location_id] = frame
    st.session_state.weather_qa[location_id] = qa


def publish_assessment(run, mode):
    st.session_state.assessment_run = run
    st.session_state.sequence = run.sequence
    st.session_state.results = run.results
    st.session_state.p0_summary = run.p0_summary
    st.session_state.detailed_result = None
    st.session_state.detail_cache = {}
    st.session_state.export_cache = {}
    st.session_state.run_mode = mode
    st.session_state.run_fingerprint = input_fingerprint()
    st.session_state.last_run_at = datetime.now()


def current_analysis():
    return st.session_state.assessment_run.analytics(st.session_state.settings)


def current_detail():
    run = st.session_state.get("assessment_run")
    if run is None:
        return None
    settings = st.session_state.settings
    key = (settings.detailed_results_basis, settings.year_of_interest, tuple(settings.percentiles))
    cache = st.session_state.setdefault("detail_cache", {})
    if key not in cache:
        cache[key] = run.detail(settings)
    return cache[key]


def require_results() -> bool:
    errors = validation_errors(require_weather=False)
    if errors:
        show_validation(errors)
        return False
    if st.session_state.get("assessment_run") is None:
        if is_p0_basis(st.session_state.settings):
            try:
                settings, locations, activities, bins, learning, groups = current_inputs()
                run = run_assessment(settings, locations, activities, bins, learning, groups, {}, p0_only=True)
                publish_assessment(run, "p0")
            except ValueError as exc:
                st.error(str(exc))
                return False
        else:
            st.info("Run an assessment on page 08 first.")
            return False
    if st.session_state.run_fingerprint != input_fingerprint():
        stale_results_warning()
        return False
    return True


def sidebar() -> str:
    with st.sidebar:
        settings = st.session_state.settings
        brand(APP_VERSION, settings.project_name)

        current_page = st.session_state.get("selected_page", PAGES[0])
        for group_name, group_pages in NAV_GROUPS:
            nav_heading(group_name)
            for page_name in group_pages:
                icon = NAV_ICONS.get(page_name, "•")
                label = f"{icon}  {page_name}"
                if st.button(
                    label,
                    key=f"nav_{page_name}",
                    type="primary" if page_name == current_page else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.selected_page = page_name
                    st.rerun()

        st.divider()
        if st.session_state.results is not None:
            status = {"full": "Full", "quick": "Quick", "p0": "P0"}.get(st.session_state.run_mode, "Saved")
            last = st.session_state.last_run_at.strftime("%d %b %Y %H:%M") if st.session_state.last_run_at else "Saved in session"
            sidebar_status(f"Latest run: {status} assessment\n{last}")
        elif not st.session_state.weather_data:
            sidebar_status("No assessment has been run in this session.")

        if st.button("Reset to built-in example", use_container_width=True, key="reset_builtin_example"):
            restore_builtin_example()
            st.rerun()
        sidebar_footer("")
    return st.session_state.get("selected_page", PAGES[0])


def validation_errors(require_weather: bool = True) -> list[str]:
    settings, locations, activities, bins, learning, groups = current_inputs()
    loaded = set(st.session_state.weather_data) if require_weather else None
    return validate_inputs(settings, activities, bins, learning, locations, loaded, groups)


def configure_ui() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=str(APP_ROOT / "assets" / "wind_turbine_icon.png"),
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_theme()
    pio.templates["mfa_light"] = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#FFFFFF",
            font=dict(color="#13213A", family="Inter, Segoe UI, Arial"),
            title=dict(font=dict(color="#13213A", size=18)),
            colorway=px.colors.qualitative.Plotly,
            xaxis=dict(gridcolor="#E6ECF2", zerolinecolor="#D7E0E9", linecolor="#C8D4DF"),
            yaxis=dict(gridcolor="#E6ECF2", zerolinecolor="#D7E0E9", linecolor="#C8D4DF"),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=48, r=28, t=62, b=48),
            hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#B9C8D6", font=dict(color="#13213A")),
        )
    )
    pio.templates.default = "mfa_light"

