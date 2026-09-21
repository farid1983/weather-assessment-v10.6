from dataclasses import replace

import pandas as pd
import pytest

from weather_assessment.assessment import run_assessment
from weather_assessment.defaults import default_settings, default_activities
from weather_assessment.export import build_excel_export
from weather_assessment.models import Location, SafeToSafeGroup, Activity
from weather_assessment.pdf_report import build_pdf_report
from weather_assessment.ms_project import build_ms_project_xml


def inputs():
    settings = default_settings()
    settings.total_positions = settings.positions_per_cycle = 1
    activity = default_activities()[0]
    activity.activity_type = 2
    activity.milestone = True
    activity.duration_hours = activity.weather_window_hours = 1.25
    frame = pd.DataFrame({"timestamp": pd.date_range("1990-01-01", periods=72, freq="h"),
                          **{name: 0.0 for name in ("wind10", "wind100", "hs", "tp", "current")}})
    return settings, [Location("PORT", "Port")], [activity], {"PORT": frame}


def test_run_snapshot_cannot_be_changed_through_draft_or_returned_objects():
    settings, locations, activities, weather = inputs()
    run = run_assessment(settings, locations, activities, [], {1: 1.0}, [], weather)
    activities[0].duration_hours = 999
    weather["PORT"].loc[:, "wind10"] = 999
    run.results[0].duration_hours = 999
    run.sequence[0].duration_hours = 999
    context = run.report_context(settings)
    assert context["activities"][0].duration_hours == 1.25
    assert run.results[0].duration_hours == 2.0
    assert run.sequence[0].duration_hours == 1.25
    assert run.detail(settings).duration_hours == 2.0
    with pytest.raises(ValueError, match="changed"):
        run.report_context(replace(settings, total_positions=2))


def test_selection_changes_reuse_run_and_replay_reconciles():
    settings, locations, activities, weather = inputs()
    run = run_assessment(settings, locations, activities, [], {1: 1.0}, [], weather)
    selected = replace(settings, percentiles=(25., 50., 95.), detailed_results_basis="Percentile 3 representative hindcast year")
    detail = run.detail(selected)
    assert detail.successful
    assert detail.trace is not None
    assert detail.duration_hours == run.results[0].duration_hours
    assert detail.trace["Duration [h]"].sum() == detail.duration_hours
    analysis = run.analytics(selected)
    assert run.analytics(selected) is analysis
    positions = analysis.table("positions")
    positions.loc[:, "Position"] = 999
    assert analysis.table("positions").iloc[0]["Position"] == 1


def test_independent_group_location_is_aligned_by_service():
    settings, locations, activities, weather = inputs()
    locations.append(Location("ASSESS", "Assessment site"))
    weather["ASSESS"] = weather["PORT"].copy()
    activities.append(Activity.from_dict({**activities[0].to_dict(), "activity_id": 2, "milestone": False}))
    for activity in activities:
        activity.safe_to_safe_group = "G"
    groups = [SafeToSafeGroup("G", assessment_location="ASSESS")]
    run = run_assessment(settings, locations, activities, [], {1: 1.0}, groups, weather, full=True)
    assert run.results[0].successful
    assert run.results[0].downtime_hours == 0


def test_p0_only_exports_need_no_weather_or_hindcast():
    settings, locations, activities, _ = inputs()
    settings.detailed_results_basis = "P0 (no weather)"
    run = run_assessment(settings, locations, activities, [], {1: 1.0}, [], {}, p0_only=True)
    context = run.report_context(settings)
    detail = run.detail(settings)
    assert run.results == []
    assert detail.duration_hours == 1.25
    assert detail.downtime_hours == detail.timestep_adjustment_hours == 0.0
    assert build_excel_export(**context, detailed_result=detail, app_version="test").startswith(b"PK")
    pdf = {key: value for key, value in context.items() if key not in {"bins", "learning_curve"}}
    assert build_pdf_report(**pdf, detailed_result=detail, app_version="test").startswith(b"%PDF")
    assert b"<Project" in build_ms_project_xml(settings, run.sequence, detail, app_version="test", scenario_label="P0")
