from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pandas as pd

from weather_assessment.defaults import (
    default_activities,
    default_hstp_bins,
    default_locations,
    default_settings,
)
from weather_assessment.export import build_excel_export
from weather_assessment.input_workbook import _read_sheet, _shared_strings, _sheet_paths
from weather_assessment.pdf_report import build_pdf_report
from weather_assessment.ms_project import (
    DOWNTIME_FIELD_ID,
    build_ms_project_xml,
    project_task_list_dataframe,
)
from weather_assessment.sequence import build_sequence, no_weather_summary
from weather_assessment.simulator import simulate_year
from weather_assessment.weather import prepare_weather

def perfect_weather(start: str, end: str) -> pd.DataFrame:
    timestamps = pd.date_range(start, end, freq="1h")
    return pd.DataFrame({
        "timestamp": timestamps,
        "wind10": 0.0,
        "wind100": 0.0,
        "hs": 0.0,
        "tp": 0.0,
        "current": 0.0,
    })


def _small_completed_assessment():
    settings = default_settings()
    settings.total_positions = 1
    settings.positions_per_cycle = 1
    settings.timestep_hours = 0.5
    activities = default_activities()[:1]
    activities[0].activity_type = 2
    activities[0].milestone = True
    activities[0].duration_hours = 1.25
    activities[0].weather_window_hours = 1.25
    activities[0].safe_to_safe_group = ""
    locations = default_locations()
    bins = default_hstp_bins()
    learning = {1: 1.0}
    groups = []
    sequence = build_sequence(settings, activities, learning, groups)
    p0 = no_weather_summary(sequence, settings)
    result = simulate_year(
        prepare_weather(perfect_weather("1990-01-01", "1990-01-03"), settings.timestep_hours),
        sequence,
        bins,
        settings,
        1990,
        include_trace=True,
    )
    assert result.successful
    return settings, locations, activities, bins, learning, groups, sequence, p0, [result], result


def test_excel_export_uses_latest_sheet_structure_and_safe_to_safe_order():
    settings, locations, activities, bins, learning, groups, sequence, p0, results, detailed = _small_completed_assessment()
    data = build_excel_export(
        settings=settings,
        locations=locations,
        activities=activities,
        bins=bins,
        learning_curve=learning,
        safe_to_safe_groups=groups,
        sequence=sequence,
        results=results,
        detailed_result=detailed,
        p0_summary=p0,
        app_version="0.10.6",
    )
    expected_sheets = [
        "Assessment metadata", "IN_general", "IN_locations", "IN_safe to safe",
        "IN_HsTp curve", "IN_learning curve", "IN_sequence", "OUT_years coverage",
        "OUT_P0 run", "OUT_run", "OUT_overall", "OUT_overall MS", "OUT_overall monthly",
        "OUT_specific month", "OUT_overall annual", "OUT_planning summary", "OUT_planning MS",
        "OUT_overall DT", "OUT_P50 DT", "OUT_P50 DT detail",
    ]
    with ZipFile(BytesIO(data)) as archive:
        shared = _shared_strings(archive)
        paths = _sheet_paths(archive)
        assert list(paths) == expected_sheets
        rows = _read_sheet(archive, paths["IN_general"], shared)
        monthly_rows = _read_sheet(archive, paths["OUT_overall monthly"], shared)
        specific_rows = _read_sheet(archive, paths["OUT_specific month"], shared)
        detail_rows = _read_sheet(archive, paths["OUT_P50 DT"], shared)
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        assert any("Selected-basis cycle-grouped XML (P50) available" in str(value) for value in shared)
        chart_xml = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.startswith("xl/charts/chart") and name.endswith(".xml")
        )
        assert "<c:grouping val=\"clustered\"/>" in chart_xml
        assert "Workable time [h]" in chart_xml
        assert "Downtime [h]" in chart_xml
        assert "Representative-year workable time and downtime" in chart_xml
        assert "monthly statistical hours - side-by-side" in chart_xml
        assert "<c:grouping val=\"stacked\"/>" not in chart_xml
        assert "<c:showVal val=\"1\"/>" in chart_xml
        assert "OUT_planning monthly" not in workbook_xml
        assert "OUT_planning coverage" not in workbook_xml
        assert "OUT_planning DT" not in workbook_xml
    # Automatic hindcast range is resolved in IN_general rather than left blank.
    start_row = next(row for row in rows if row and row[0] == "hindcast_start_year")
    end_row = next(row for row in rows if row and row[0] == "hindcast_end_year")
    assert 1990 in start_row
    assert 1990 in end_row

    assert any(row and row[0] == "A. Statistical planning and representative-year selection" for row in monthly_rows)
    assert any(row and row[0] == "C. Representative-year monthly schedules - additive" for row in monthly_rows)
    assert any(row and "P50 - representative year" in str(row[1]) for row in monthly_rows if len(row) > 1)
    assert any(row and "P75 - representative year" in " ".join(str(value) for value in row) for row in monthly_rows)
    assert any(row and "P90 - representative year" in " ".join(str(value) for value in row) for row in monthly_rows)

    specific_note = next(row for row in specific_rows if row and row[0] and "Monthly statistical profile" in str(row[0]))
    assert "non-additive" in str(specific_note[0])
    specific_header = next(row for row in specific_rows if row and row[0] == "Month")
    assert "Downtime hours - P50" in specific_header
    assert "Workable hours - P50" in specific_header

    header = next(row for row in rows if row and row[0] == "activity_id")
    assert header.index("safe_to_safe_group") == header.index("weather_window_hours") + 1



def test_excel_export_selected_detail_sheet_follows_campaign_setting():
    settings, locations, activities, bins, learning, groups, sequence, p0, results, detailed = _small_completed_assessment()
    settings.detailed_results_basis = "Percentile 2 representative hindcast year"
    p75_data = build_excel_export(
        settings=settings, locations=locations, activities=activities, bins=bins,
        learning_curve=learning, safe_to_safe_groups=groups, sequence=sequence,
        results=results, detailed_result=detailed, p0_summary=p0, app_version="0.10.6",
    )
    with ZipFile(BytesIO(p75_data)) as archive:
        paths = _sheet_paths(archive)
        assert "OUT_P75 DT" in paths
        assert "OUT_P75 DT detail" in paths
        assert "OUT_P50 DT" not in paths

    settings.detailed_results_basis = "Specific hindcast year"
    settings.year_of_interest = 1990
    year_data = build_excel_export(
        settings=settings, locations=locations, activities=activities, bins=bins,
        learning_curve=learning, safe_to_safe_groups=groups, sequence=sequence,
        results=results, detailed_result=detailed, p0_summary=p0, app_version="0.10.6",
    )
    with ZipFile(BytesIO(year_data)) as archive:
        paths = _sheet_paths(archive)
        assert "OUT_1990 DT" in paths
        assert "OUT_1990 DT detail" in paths



def test_p0_selected_basis_has_no_weather_detail_sheet_and_exact_trace():
    from weather_assessment.sequence import p0_simulation_result
    settings, locations, activities, bins, learning, groups, sequence, p0, results, detailed = _small_completed_assessment()
    settings.detailed_results_basis = "P0 (no weather)"
    p0_result = p0_simulation_result(sequence, settings)
    assert p0_result.downtime_hours == 0.0
    assert p0_result.timestep_adjustment_hours == 0.0
    assert abs(float(p0_result.duration_hours) - float(p0["duration_hours"])) < 1e-9
    data = build_excel_export(
        settings=settings, locations=locations, activities=activities, bins=bins,
        learning_curve=learning, safe_to_safe_groups=groups, sequence=sequence,
        results=results, detailed_result=p0_result, p0_summary=p0, app_version="0.10.6",
    )
    with ZipFile(BytesIO(data)) as archive:
        paths = _sheet_paths(archive)
        assert "OUT_P0 run" in paths
        assert "OUT_run" in paths
        assert "OUT_P0 DT" not in paths
        assert "OUT_P0 DT detail" not in paths


def test_pdf_report_smoke():
    settings, locations, activities, _bins, _learning, groups, sequence, p0, results, detailed = _small_completed_assessment()
    data = build_pdf_report(
        settings=settings,
        locations=locations,
        activities=activities,
        safe_to_safe_groups=groups,
        sequence=sequence,
        results=results,
        detailed_result=detailed,
        p0_summary=p0,
        app_version="0.10.6",
        weather_filenames={"PORT": "weather.csv"},
        selected_percentile=50.0,
    )
    assert data.startswith(b"%PDF")
    assert len(data) > 5000


def test_ms_project_xml_groups_tasks_by_cycle_and_rolls_downtime_into_activity():
    from xml.etree import ElementTree as ET

    settings = default_settings()
    settings.total_positions = 2
    settings.positions_per_cycle = 1
    settings.timestep_hours = 1.0
    activities = default_activities()[:1]
    activities[0].activity_type = 2
    activities[0].milestone = True
    activities[0].duration_hours = 1.25
    activities[0].weather_window_hours = 1.25
    activities[0].safe_to_safe_group = ""
    sequence = build_sequence(settings, activities, {1: 1.0, 2: 1.0}, [])

    weather = perfect_weather("1990-01-01", "1990-01-05")
    weather.loc[0, "wind10"] = 100.0
    activities[0].wind10_limit = 10.0
    sequence = build_sequence(settings, activities, {1: 1.0, 2: 1.0}, [])
    result = simulate_year(weather, sequence, default_hstp_bins(), settings, 1990, include_trace=True)
    assert result.successful
    assert result.downtime_hours > 0

    review = project_task_list_dataframe(settings, sequence, result)
    summaries = review.loc[review["Outline level"] == 1]
    assert summaries["Task name"].tolist() == ["Cycle 01 — Position 1", "Cycle 02 — Position 2"]
    assert len(review) == 4
    expected_p0 = sum(float(item.duration_hours) for item in sequence)
    assert abs(float(summaries["Plan duration [days]"].sum()) * 24.0 - expected_p0) < 1e-9
    assert abs(float(summaries["Downtime [days]"].sum()) * 24.0 - result.downtime_hours) < 1e-9
    assert abs(float(summaries["Total duration [days]"].sum()) * 24.0 - float(result.duration_hours)) < 1e-9

    xml_data = build_ms_project_xml(
        settings=settings,
        sequence=sequence,
        result=result,
        app_version="0.10.6",
        percentile=50.0,
    )
    root = ET.fromstring(xml_data)
    ns = {"m": "http://schemas.microsoft.com/project"}
    tasks = root.findall("m:Tasks/m:Task", ns)
    assert len(tasks) == 4
    assert tasks[0].findtext("m:Name", namespaces=ns) == "Cycle 01 — Position 1"
    assert tasks[0].findtext("m:Summary", namespaces=ns) == "1"
    assert tasks[1].findtext("m:OutlineLevel", namespaces=ns) == "2"
    field_values = {
        item.findtext("m:FieldID", namespaces=ns): item.findtext("m:Value", namespaces=ns)
        for item in tasks[0].findall("m:ExtendedAttribute", ns)
    }
    assert DOWNTIME_FIELD_ID in field_values
    assert float(field_values[DOWNTIME_FIELD_ID]) > 0
    aliases = {
        item.findtext("m:Alias", namespaces=ns)
        for item in root.findall("m:ExtendedAttributes/m:ExtendedAttribute", ns)
    }
    assert "Duration WDT [days]" in aliases
    assert tasks[1].findtext("m:Manual", namespaces=ns) == "1"
    assert tasks[1].find("m:ActualDuration", ns) is None
    assert tasks[1].find("m:RemainingDuration", ns) is None
    assert b"24:00:00" not in xml_data
