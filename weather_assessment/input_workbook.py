from __future__ import annotations

from io import BytesIO
from pathlib import PurePosixPath
import re
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

import xlsxwriter

from .models import Activity, CampaignSettings, HsTpBin, Location, SafeToSafeGroup
from .policies import parse_bool, finite_number

PROJECT_SHEET = "01 Project"
LOCATIONS_SHEET = "02 Locations"
ACTIVITIES_SHEET = "03 Activities"
GROUPS_SHEET = "04 Safe-to-Safe Groups"
HSTP_SHEET = "05 HsTp Curves"
LEARNING_SHEET = "06 Learning Curve"
INSTRUCTIONS_SHEET = "07 Instructions"
LOCATION_GUIDANCE = "Each activity must reference a Location ID. Upload one weather CSV for every used location in the app."
GROUP_GUIDANCE = "MOST_STRINGENT applies the lowest group limits for the full continuous group duration. TIME_PHASED applies each activity's own limits during its expected part of the sequence."

PROJECT_FIELDS: list[tuple[str, str, str]] = [
    ("project_name", "Project / scenario name", "Descriptive name used in results and exported files."),
    ("nominal_year", "Planning year", "Future year used for planning dates, for example 2026."),
    ("start_month", "Campaign start month", "Number from 1 to 12."),
    ("start_day", "Campaign start day", "Number from 1 to 31."),
    ("positions_per_cycle", "Positions per cycle", "Number of Type 2 positions completed in each cycle."),
    ("total_positions", "Total positions", "Total number of installation positions in the campaign."),
    ("percentile_1", "Percentile 1", "Normally 50."),
    ("percentile_2", "Percentile 2", "Normally 75."),
    ("percentile_3", "Percentile 3", "Normally 90."),
    ("timestep_hours", "Simulation time step [h]", "Use 1, 0.5, or 0.25 hours."),
    ("detailed_results_basis", "Detailed results basis", "Use P0 (no weather), Percentile 1, 2 or 3 representative hindcast year, or enter a specific historical year."),
    ("hindcast_start_year", "Hindcast start year", "First historical start year to simulate. May be blank."),
    ("hindcast_end_year", "Hindcast end year", "Last historical start year to simulate. May be blank."),
    ("default_safe_to_safe_method", "Default safe-to-safe method", "MOST_STRINGENT or TIME_PHASED. Individual groups may override this on 04 Safe-to-Safe Groups."),
]

LOCATION_HEADERS = ["Location ID", "Location name", "Type", "Time zone", "Weather file name", "Notes"]
ACTIVITY_HEADERS = [
    "Activity ID", "Type", "No learning curve", "Position complete", "Description", "Work location",
    "Duration [h]", "Weather window [h]", "Safe-to-safe group", "Wind 10 m limit [m/s]", "Wind 100 m limit [m/s]",
    "Hs limit [m]", "Tp limit [s]", "Current limit [m/s]", "Start time [HH:MM]", "End time [HH:MM]",
    "Hs-Tp curve", "Remarks",
]
GROUP_HEADERS = ["Group ID", "Description", "Assessment method", "Assessment location", "Notes"]
HSTP_HEADERS = ["Curve", "Tp from [s]", "Tp to [s]", "Hs maximum [m]"]
LEARNING_HEADERS = ["Cycle", "Duration multiplier"]


def _settings_values(settings: CampaignSettings) -> dict[str, Any]:
    return {
        "project_name": settings.project_name,
        "nominal_year": settings.nominal_year,
        "start_month": settings.start_month,
        "start_day": settings.start_day,
        "positions_per_cycle": settings.positions_per_cycle,
        "total_positions": settings.total_positions,
        "percentile_1": settings.percentiles[0],
        "percentile_2": settings.percentiles[1],
        "percentile_3": settings.percentiles[2],
        "timestep_hours": settings.timestep_hours,
        "detailed_results_basis": (str(settings.year_of_interest) if settings.detailed_results_basis == "Specific hindcast year" and settings.year_of_interest is not None else settings.detailed_results_basis),
        "hindcast_start_year": settings.hindcast_start_year,
        "hindcast_end_year": settings.hindcast_end_year,
        "default_safe_to_safe_method": settings.default_safe_to_safe_method,
    }


def build_project_input_workbook(
    settings: CampaignSettings,
    locations: list[Location],
    activities: list[Activity],
    bins: list[HsTpBin],
    learning_curve: dict[int, float],
    safe_to_safe_groups: list[SafeToSafeGroup] | None = None,
    app_version: str = "0.10.5",
) -> bytes:
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    navy = "#174A72"
    input_fill = "#FFF2CC"
    soft_blue = "#DDEBF7"
    green = "#E2F0D9"
    header = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": navy, "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
    input_fmt = workbook.add_format({"bg_color": input_fill, "border": 1, "valign": "top"})
    text_fmt = workbook.add_format({"border": 1, "valign": "top"})
    guide_fmt = workbook.add_format({"border": 1, "text_wrap": True, "valign": "top"})
    title_fmt = workbook.add_format({"bold": True, "font_size": 16, "font_color": navy})
    note_fmt = workbook.add_format({"bg_color": soft_blue, "border": 1, "text_wrap": True})
    pass_fmt = workbook.add_format({"bg_color": green, "border": 1})
    time_fmt = workbook.add_format({"bg_color": input_fill, "border": 1, "num_format": "hh:mm"})

    project = workbook.add_worksheet(PROJECT_SHEET)
    project.freeze_panes(1, 0)
    project.set_column("A:A", 34)
    project.set_column("B:B", 24)
    project.set_column("C:C", 68)
    project.write_row(0, 0, ["Setting", "Value", "Guidance"], header)
    values = _settings_values(settings)
    for row, (key, label, guidance) in enumerate(PROJECT_FIELDS, start=1):
        project.write(row, 0, label, text_fmt)
        project.write(row, 1, values.get(key), input_fmt)
        project.write(row, 2, guidance, guide_fmt)
    project.data_validation(2, 1, 2, 1, {"validate": "integer", "criteria": "between", "minimum": 2000, "maximum": 2200})
    project.data_validation(3, 1, 3, 1, {"validate": "integer", "criteria": "between", "minimum": 1, "maximum": 12})
    project.data_validation(4, 1, 4, 1, {"validate": "integer", "criteria": "between", "minimum": 1, "maximum": 31})
    project.data_validation(10, 1, 10, 1, {"validate": "list", "source": [1, 0.5, 0.25]})
    project.data_validation(len(PROJECT_FIELDS), 1, len(PROJECT_FIELDS), 1, {"validate": "list", "source": ["MOST_STRINGENT", "TIME_PHASED"]})

    location_sheet = workbook.add_worksheet(LOCATIONS_SHEET)
    location_sheet.freeze_panes(1, 0)
    location_sheet.set_column("A:A", 16)
    location_sheet.set_column("B:B", 28)
    location_sheet.set_column("C:C", 14)
    location_sheet.set_column("D:D", 14)
    location_sheet.set_column("E:E", 34)
    location_sheet.set_column("F:F", 48)
    location_sheet.write_row(0, 0, LOCATION_HEADERS, header)
    for row, item in enumerate(locations, start=1):
        location_sheet.write_row(row, 0, [item.location_id, item.name, item.location_type, item.timezone, item.weather_filename, item.notes], input_fmt)
    location_sheet.data_validation(1, 2, 49, 2, {"validate": "list", "source": ["Port", "Transit", "Offshore", "Other"]})
    location_sheet.data_validation(1, 3, 49, 3, {"validate": "list", "source": ["UTC", "Asia/Taipei", "Asia/Kuala_Lumpur", "Europe/Copenhagen"]})
    location_sheet.write(len(locations) + 2, 0, "Each activity must reference a Location ID. Upload one weather CSV for every used location in the app.", note_fmt)
    location_sheet.merge_range(len(locations) + 2, 0, len(locations) + 2, 5, "Each activity must reference a Location ID. Upload one weather CSV for every used location in the app.", note_fmt)

    activity_sheet = workbook.add_worksheet(ACTIVITIES_SHEET)
    activity_sheet.freeze_panes(1, 5)
    widths = [11, 8, 17, 16, 42, 16, 18, 13, 17, 19, 20, 13, 13, 18, 18, 18, 14, 34]
    for col, width in enumerate(widths):
        activity_sheet.set_column(col, col, width)
    activity_sheet.set_row(0, 36)
    activity_sheet.write_row(0, 0, ACTIVITY_HEADERS, header)
    for row, item in enumerate(activities, start=1):
        activity_sheet.write_row(row, 0, [
            item.activity_id, item.activity_type, "Yes" if item.no_learning_curve else "No",
            "Yes" if item.milestone else "No", item.description, item.location_id,
            item.duration_hours, item.weather_window_hours, item.safe_to_safe_group, item.wind10_limit, item.wind100_limit,
            item.hs_limit, item.tp_limit, item.current_limit, item.time_start, item.time_end,
            item.hstp_curve, item.remarks,
        ], input_fmt)
    max_activity_row = max(100, len(activities) + 10)
    activity_sheet.data_validation(1, 1, max_activity_row, 1, {"validate": "list", "source": [1, 2, 3]})
    activity_sheet.data_validation(1, 2, max_activity_row, 3, {"validate": "list", "source": ["Yes", "No"]})
    activity_sheet.data_validation(1, 5, max_activity_row, 5, {"validate": "list", "source": f"='{LOCATIONS_SHEET}'!$A$2:$A$50"})
    activity_sheet.data_validation(1, 16, max_activity_row, 16, {"validate": "list", "source": ["None"] + sorted({item.curve for item in bins})})

    group_sheet = workbook.add_worksheet(GROUPS_SHEET)
    group_sheet.freeze_panes(1, 0)
    group_sheet.set_column("A:A", 14)
    group_sheet.set_column("B:B", 34)
    group_sheet.set_column("C:C", 24)
    group_sheet.set_column("D:D", 22)
    group_sheet.set_column("E:E", 56)
    group_sheet.write_row(0, 0, GROUP_HEADERS, header)
    for row, item in enumerate(safe_to_safe_groups or [], start=1):
        group_sheet.write_row(row, 0, [item.group_id, item.description, item.assessment_method, item.assessment_location, item.notes], input_fmt)
    group_sheet.data_validation(1, 2, 99, 2, {"validate": "list", "source": ["MOST_STRINGENT", "TIME_PHASED"]})
    group_sheet.data_validation(1, 3, 99, 3, {"validate": "list", "source": f"='{LOCATIONS_SHEET}'!$A$2:$A$50"})
    group_sheet.merge_range(max(3, len(safe_to_safe_groups or []) + 2), 0, max(3, len(safe_to_safe_groups or []) + 2), 4,
        "MOST_STRINGENT applies the lowest group limits for the full continuous group duration. TIME_PHASED applies each activity's own limits during its expected part of the sequence.", note_fmt)

    curve_sheet = workbook.add_worksheet(HSTP_SHEET)
    curve_sheet.freeze_panes(1, 0)
    curve_sheet.set_column("A:A", 18)
    curve_sheet.set_column("B:D", 18)
    curve_sheet.write_row(0, 0, HSTP_HEADERS, header)
    for row, item in enumerate(bins, start=1):
        curve_sheet.write_row(row, 0, [item.curve, item.tp_from, item.tp_to, item.hs_max], input_fmt)

    learning_sheet = workbook.add_worksheet(LEARNING_SHEET)
    learning_sheet.freeze_panes(1, 0)
    learning_sheet.set_column("A:B", 22)
    learning_sheet.write_row(0, 0, LEARNING_HEADERS, header)
    for row, (cycle, multiplier) in enumerate(sorted(learning_curve.items()), start=1):
        learning_sheet.write_row(row, 0, [cycle, multiplier], input_fmt)

    instructions = workbook.add_worksheet(INSTRUCTIONS_SHEET)
    instructions.set_column("A:A", 28)
    instructions.set_column("B:B", 92)
    instructions.write(0, 0, f"Weather Assessment — v{app_version}", title_fmt)
    instructions.write(2, 0, "Important", header)
    instructions.write(2, 1, "This workbook is an input format, not an approved installation procedure. Verify all durations and weather limits.", note_fmt)
    instructions.write_row(4, 0, ["Item", "Explanation"], header)
    guidance = [
        ("How to use", "Complete the yellow cells, save as .xlsx, upload it on page 02, and review validation before running."),
        ("Locations", "Define each work location on 02 Locations. A separate weather CSV can be uploaded for Port, Transit, Offshore or other locations."),
        ("Work location", "Select the Location ID whose weather conditions control the activity."),
        ("Safe-to-safe group", "Enter the same Group ID, for example G1, on consecutive activities that must have one complete forecast window before the first activity starts. Leave blank for standalone activities."),
        ("Activity Type 1", "Performed once at the start of every cycle."),
        ("Activity Type 2", "Repeated for every position in the cycle."),
        ("Activity Type 3", "Performed once at the end of every cycle."),
        ("No learning curve", "Yes keeps the original duration; No applies the cycle multiplier."),
        ("Position complete", "Mark Yes on exactly one Type 2 activity."),
        ("Weather window", "Minimum continuous workable period required before the activity can start or continue."),
        ("Safe-to-safe methods", "MOST_STRINGENT applies the group's lowest limits over the full continuous group duration. TIME_PHASED assesses each activity using its own limits at its expected execution time. Group overrides are set on 04 Safe-to-Safe Groups."),
        ("Safe-to-safe execution", "Both methods pre-check the complete committed sequence before the first activity starts. Once started, no weather waiting is allowed until the group end."),
        ("Percentile direction", "P90 is higher for duration/downtime, but lower for positions completed/workable hours."),
        ("Historical synchronization", "A hindcast scenario uses the same historical year at every work location."),
        ("P0 and timestep", "P0 uses exact learning-adjusted durations and does not change with the simulation timestep. Timestep-grid adjustment is reported separately from weather downtime."),
        ("Downtime attribution", "Downtime is attributed to the exact blocking weather criterion or criterion combination. Direct exceedance and Window pre-check are mechanisms only; Hs-Tp curve use remains recorded as the assessment basis."),
        ("Data coverage", "A scenario that reaches the end of the available weather data before completion is marked incomplete and excluded from percentile calculations."),
        ("Display precision", "Calculated decimal values and percentages are displayed to three decimal places. Raw uploaded weather values retain their source precision."),
        ("Detailed results basis", "Select P0 (no weather), Percentile 1, 2 or 3 representative hindcast year, or enter one historical hindcast year for detailed review."),
        ("Reports", "Page 15 exports the detailed Excel workbook, executive PDF summary and a cycle-grouped Microsoft Project XML schedule based on the selected detailed-results basis."),
    ]
    for row, values_row in enumerate(guidance, start=5):
        instructions.write(row, 0, values_row[0], text_fmt)
        instructions.write(row, 1, values_row[1], guide_fmt)

    workbook.close()
    return output.getvalue()


# Lightweight .xlsx XML reader. This intentionally avoids a runtime dependency on openpyxl.
_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    result = 0
    for character in letters:
        result = result * 26 + (ord(character.upper()) - 64)
    return result - 1


def _normalise(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for item in root.findall(f"{{{_NS_MAIN}}}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{{{_NS_MAIN}}}t")))
    return values


def _sheet_paths(archive: ZipFile) -> dict[str, str]:
    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relations = {item.attrib["Id"]: item.attrib["Target"] for item in rel_root.findall(f"{{{_NS_PACKAGE_REL}}}Relationship")}
    result: dict[str, str] = {}
    sheets_node = workbook_root.find(f"{{{_NS_MAIN}}}sheets")
    for sheet in [] if sheets_node is None else list(sheets_node):
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[f"{{{_NS_REL}}}id"]
        target = relations[rel_id]
        result[name] = str(PurePosixPath("xl") / target) if not target.startswith("/") else target.lstrip("/")
    return result


def _read_sheet(archive: ZipFile, path: str, shared: list[str]) -> list[list[Any]]:
    root = ET.fromstring(archive.read(path))
    data = root.find(f"{{{_NS_MAIN}}}sheetData")
    if data is None:
        return []
    rows: list[list[Any]] = []
    for row_node in data.findall(f"{{{_NS_MAIN}}}row"):
        cells: dict[int, Any] = {}
        for cell in row_node.findall(f"{{{_NS_MAIN}}}c"):
            reference = cell.attrib.get("r", "A1")
            col = _column_index(reference)
            cell_type = cell.attrib.get("t")
            value_node = cell.find(f"{{{_NS_MAIN}}}v")
            inline = cell.find(f"{{{_NS_MAIN}}}is")
            value: Any = None
            if cell_type == "inlineStr" and inline is not None:
                value = "".join(node.text or "" for node in inline.iter(f"{{{_NS_MAIN}}}t"))
            elif value_node is not None:
                raw = value_node.text or ""
                if cell_type == "s":
                    try:
                        value = shared[int(raw)]
                    except (ValueError, IndexError):
                        value = raw
                elif cell_type == "b":
                    value = raw == "1"
                elif cell_type in ("str", "e"):
                    value = raw
                else:
                    try:
                        number = float(raw)
                        value = int(number) if number.is_integer() else number
                    except ValueError:
                        value = raw
            cells[col] = value
        if cells:
            width = max(cells) + 1
            row = [None] * width
            for col, value in cells.items():
                row[col] = value
            rows.append(row)
    return rows


def _sheet_by_alias(sheets: dict[str, list[list[Any]]], aliases: list[str], required: bool = True) -> list[list[Any]]:
    normalised = {_normalise(name): rows for name, rows in sheets.items()}
    for alias in aliases:
        if _normalise(alias) in normalised:
            return normalised[_normalise(alias)]
    if required:
        raise ValueError(f"Required sheet not found. Expected one of: {', '.join(aliases)}")
    return []


def _records(rows: list[list[Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    output: list[dict[str, Any]] = []
    for row in rows[1:]:
        padded = row + [None] * max(0, len(headers) - len(row))
        record = {headers[index]: padded[index] for index in range(len(headers)) if headers[index]}
        if any(value not in (None, "") for value in record.values()):
            output.append(record)
    return output


def _as_bool(value: Any) -> bool:
    return parse_bool(value)


def _as_int(value: Any, *, optional: bool = False) -> int | None:
    if value in (None, "") and optional:
        return None
    number = float(value)
    if not finite_number(number) or not number.is_integer():
        raise ValueError(f"Expected an integer, got {value!r}.")
    return int(number)


def _as_float(value: Any, *, optional: bool = False) -> float | None:
    if value in (None, "") and optional:
        return None
    return float(value)


def _as_time(value: Any) -> str:
    if value in (None, ""):
        return "00:00"
    if isinstance(value, (int, float)):
        fraction = float(value) % 1.0
        total_minutes = int(round(fraction * 24 * 60)) % (24 * 60)
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
    text = str(value).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        number = float(text)
        if 0 <= number < 1:
            total_minutes = int(round(number * 24 * 60)) % (24 * 60)
            return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", text)
    if match:
        hours, minutes = int(match.group(1)), int(match.group(2))
        if hours > 23 or minutes > 59:
            raise ValueError(f"Invalid time {value!r}; use HH:MM within 00:00–23:59.")
        return f"{hours:02d}:{minutes:02d}"
    return text


def _field(record: dict[str, Any], aliases: list[str], default: Any = None) -> Any:
    normalised = {_normalise(key): value for key, value in record.items()}
    for alias in aliases:
        key = _normalise(alias)
        if key in normalised:
            return normalised[key]
    return default


def load_project_input_workbook(
    data: bytes,
) -> tuple[CampaignSettings, list[Location], list[Activity], list[HsTpBin], dict[int, float], list[SafeToSafeGroup]]:
    try:
        with ZipFile(BytesIO(data)) as archive:
            shared = _shared_strings(archive)
            paths = _sheet_paths(archive)
            sheets = {name: _read_sheet(archive, path, shared) for name, path in paths.items()}
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError("The uploaded file is not a readable .xlsx workbook.") from exc

    project_rows = _sheet_by_alias(sheets, [PROJECT_SHEET, "Project", "Campaign settings"])
    project_records = _records(project_rows)
    project_values: dict[str, Any] = {}
    label_to_key = {_normalise(label): key for key, label, _ in PROJECT_FIELDS}
    label_to_key[_normalise("Year of interest")] = "detailed_results_basis"
    for record in project_records:
        setting = _field(record, ["Setting", "Field", "Parameter"])
        value = _field(record, ["Value", "Input"])
        key = label_to_key.get(_normalise(setting))
        if key:
            project_values[key] = value
    required_project = ["project_name", "nominal_year", "start_month", "start_day", "positions_per_cycle", "total_positions"]
    missing = [key for key in required_project if project_values.get(key) in (None, "")]
    if missing:
        raise ValueError("Project sheet is missing required values: " + ", ".join(missing))
    basis_raw = project_values.get("detailed_results_basis")
    detailed_results_basis = "Percentile 1 representative hindcast year"
    year_of_interest = None
    if basis_raw not in (None, ""):
        text = str(basis_raw).strip()
        lowered = text.lower()
        try:
            year_of_interest = int(float(text))
            detailed_results_basis = "Specific hindcast year"
        except ValueError:
            if lowered in {"p0", "p0 (no weather)", "p0 - no weather", "deterministic p0"}:
                detailed_results_basis = "P0 (no weather)"
            elif "specific" in lowered:
                detailed_results_basis = "Specific hindcast year"
            elif "percentile 2" in lowered:
                detailed_results_basis = "Percentile 2 representative hindcast year"
            elif "percentile 3" in lowered:
                detailed_results_basis = "Percentile 3 representative hindcast year"
            else:
                detailed_results_basis = "Percentile 1 representative hindcast year"

    settings = CampaignSettings(
        project_name=str(project_values["project_name"]),
        nominal_year=int(_as_int(project_values["nominal_year"])),
        start_month=int(_as_int(project_values["start_month"])),
        start_day=int(_as_int(project_values["start_day"])),
        positions_per_cycle=int(_as_int(project_values["positions_per_cycle"])),
        total_positions=int(_as_int(project_values["total_positions"])),
        percentiles=(
            float(_as_float(project_values.get("percentile_1", 50))),
            float(_as_float(project_values.get("percentile_2", 75))),
            float(_as_float(project_values.get("percentile_3", 90))),
        ),
        timestep_hours=float(_as_float(project_values.get("timestep_hours", 1))),
        detailed_results_basis=detailed_results_basis,
        year_of_interest=year_of_interest,
        hindcast_start_year=_as_int(project_values.get("hindcast_start_year"), optional=True),
        hindcast_end_year=_as_int(project_values.get("hindcast_end_year"), optional=True),
        default_safe_to_safe_method=str(project_values.get("default_safe_to_safe_method", "MOST_STRINGENT") or "MOST_STRINGENT").strip().upper(),
    )

    location_rows = _records(_sheet_by_alias(sheets, [LOCATIONS_SHEET, "Locations", "Work locations"], required=False))
    locations: list[Location] = []
    for row in location_rows:
        location_id = _field(row, ["Location ID", "location_id"])
        if location_id in (None, ""):
            continue
        location_id_text = str(location_id).strip()
        if location_id_text == LOCATION_GUIDANCE:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]+", location_id_text):
            raise ValueError(f"Invalid location ID: {location_id_text!r}.")
        locations.append(Location(
            location_id=location_id_text,
            name=str(_field(row, ["Location name", "Name", "name"], location_id)),
            location_type=str(_field(row, ["Type", "Location type", "location_type"], "Other")),
            timezone=str(_field(row, ["Time zone", "Timezone", "timezone"], "UTC")),
            weather_filename=str(_field(row, ["Weather file name", "Weather file", "weather_filename"], "") or ""),
            notes=str(_field(row, ["Notes", "Remarks", "notes"], "") or ""),
        ))

    activity_rows = _records(_sheet_by_alias(sheets, [ACTIVITIES_SHEET, "02 Activities", "Activities", "Input activities"]))
    activities: list[Activity] = []
    for row in activity_rows:
        activity_id = _field(row, ["Activity ID", "activity_id"])
        activity_type = _field(row, ["Type", "Activity type", "activity_type"])
        if activity_id in (None, "") and activity_type in (None, ""):
            continue
        activities.append(Activity(
            activity_id=int(_as_int(activity_id)),
            activity_type=int(_as_int(activity_type)),
            no_learning_curve=_as_bool(_field(row, ["No learning curve", "no_learning_curve"])),
            milestone=_as_bool(_field(row, ["Position complete", "milestone"])),
            description=str(_field(row, ["Description", "Activity description", "description"], "")),
            location_id=str(_field(row, ["Work location", "Location ID", "location_id"], "OFFSHORE") or "OFFSHORE"),
            safe_to_safe_group=str(_field(row, ["Safe-to-safe group", "Commitment group", "Group ID", "safe_to_safe_group"], "") or "").strip(),
            duration_hours=float(_as_float(_field(row, ["Duration [h]", "Duration hours", "duration_hours"]))),
            weather_window_hours=float(_as_float(_field(row, ["Weather window [h]", "Minimum weather window", "weather_window_hours"]))),
            wind10_limit=float(_as_float(_field(row, ["Wind 10 m limit [m/s]", "Wind 10 m", "wind10_limit"]))),
            wind100_limit=float(_as_float(_field(row, ["Wind 100 m limit [m/s]", "Wind 100 m", "wind100_limit"]))),
            hs_limit=float(_as_float(_field(row, ["Hs limit [m]", "Hs", "hs_limit"]))),
            tp_limit=float(_as_float(_field(row, ["Tp limit [s]", "Tp", "tp_limit"]))),
            current_limit=float(_as_float(_field(row, ["Current limit [m/s]", "Current", "current_limit"]))),
            time_start=_as_time(_field(row, ["Start time [HH:MM]", "Start time", "time_start"], "00:00")),
            time_end=_as_time(_field(row, ["End time [HH:MM]", "End time", "time_end"], "00:00")),
            hstp_curve=str(_field(row, ["Hs-Tp curve", "Combined Hs/Tp", "hstp_curve"], "None") or "None"),
            remarks=str(_field(row, ["Remarks", "Notes", "remarks"], "") or ""),
        ))
    activities.sort(key=lambda item: item.activity_id)
    if not locations:
        unique_locations = sorted({item.location_id for item in activities} or {"OFFSHORE"})
        locations = [Location(item, item.title()) for item in unique_locations]

    group_rows = _records(_sheet_by_alias(sheets, [GROUPS_SHEET, "Safe-to-Safe Groups", "Safe to Safe Groups", "Commitment Groups"], required=False))
    groups: list[SafeToSafeGroup] = []
    for row in group_rows:
        group_id = _field(row, ["Group ID", "Group", "group_id"])
        if group_id in (None, ""):
            continue
        group_id_text = str(group_id).strip()
        if group_id_text == GROUP_GUIDANCE:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]+", group_id_text):
            raise ValueError(f"Invalid group ID: {group_id_text!r}.")
        groups.append(SafeToSafeGroup.from_dict({
            "group_id": group_id_text,
            "description": _field(row, ["Description", "Group description"], ""),
            "assessment_method": _field(row, ["Assessment method", "Method"], settings.default_safe_to_safe_method),
            "assessment_location": _field(row, ["Assessment location", "Location"], ""),
            "notes": _field(row, ["Notes", "Remarks"], ""),
        }))
    if not groups:
        for group_id in sorted({item.safe_to_safe_group for item in activities if item.safe_to_safe_group}):
            members = [item for item in activities if item.safe_to_safe_group == group_id]
            member_locations = sorted({item.location_id for item in members})
            groups.append(SafeToSafeGroup(
                group_id=group_id,
                description=f"{members[0].description} to {members[-1].description}" if members else group_id,
                assessment_method=settings.default_safe_to_safe_method,
                assessment_location=member_locations[0] if len(member_locations) == 1 else "",
            ))

    hstp_rows = _records(_sheet_by_alias(sheets, [HSTP_SHEET, "04 HsTp Curves", "03 HsTp Curves", "HsTp Curves", "HsTp", "Combined HsTp curves"]))
    bins: list[HsTpBin] = []
    for row in hstp_rows:
        curve = _field(row, ["Curve", "curve"])
        if curve in (None, ""):
            continue
        bins.append(HsTpBin(
            curve=str(curve),
            tp_from=float(_as_float(_field(row, ["Tp from [s]", "Tp from", "tp_from"]))),
            tp_to=float(_as_float(_field(row, ["Tp to [s]", "Tp to", "tp_to"]))),
            hs_max=float(_as_float(_field(row, ["Hs maximum [m]", "Hs maximum", "hs_max"]))),
        ))

    learning_rows = _records(_sheet_by_alias(sheets, [LEARNING_SHEET, "05 Learning Curve", "04 Learning Curve", "Learning Curve", "Learning"]))
    learning: dict[int, float] = {}
    for row in learning_rows:
        cycle = _field(row, ["Cycle", "cycle"])
        if cycle in (None, ""):
            continue
        multiplier = _field(row, ["Duration multiplier", "Multiplier", "multiplier"], 1.0)
        learning[int(_as_int(cycle))] = float(_as_float(multiplier))
    return settings, locations, activities, bins, learning, groups
