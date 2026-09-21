from pathlib import Path
from dataclasses import replace

import pandas as pd
from streamlit.testing.v1 import AppTest

from weather_assessment.defaults import (
    default_settings, default_activities, locations_dataframe, activities_dataframe,
    learning_dataframe, hstp_dataframe, safe_to_safe_groups_dataframe,
)
from weather_assessment.models import Location
from weather_assessment.weather import weather_qa


def small_app(*, p0=False, bad_weather=False):
    app = AppTest.from_file("app.py", default_timeout=30)
    settings = default_settings()
    settings.total_positions = settings.positions_per_cycle = 1
    if p0:
        settings.detailed_results_basis = "P0 (no weather)"
    activity = default_activities()[0]
    activity.activity_type = 2
    activity.milestone = True
    activity.duration_hours = activity.weather_window_hours = 1.25
    frame = pd.DataFrame({"timestamp": pd.date_range("1990-01-01", periods=72, freq="h"),
                          **{name: 1000.0 if bad_weather else 0.0 for name in ("wind10", "wind100", "hs", "tp", "current")}})
    initial = dict(initialised_app_version=Path("VERSION").read_text().strip(), selected_page="08 Run assessment",
                   settings=settings, locations_df=locations_dataframe([Location("PORT", "Port")]),
                   activities_df=activities_dataframe([activity]), learning_df=learning_dataframe({1: 1.0}),
                   hstp_df=hstp_dataframe([]), safe_to_safe_groups_df=safe_to_safe_groups_dataframe([]),
                   weather_data={} if p0 else {"PORT": frame}, weather_qa={} if p0 else {"PORT": weather_qa(frame)},
                   weather_configs={}, weather_files={}, results=None, assessment_run=None, sequence=None,
                   detailed_result=None, p0_summary=None, aligned_weather=None, run_fingerprint=None,
                   run_mode=None, last_run_at=None, run_history=[], detail_cache={}, export_cache={})
    for key, value in initial.items():
        app.session_state[key] = value
    return app.run()


def button(app, label):
    return next(item for item in app.button if item.label == label)


def visit(app, page):
    app.session_state.selected_page = page
    app.run()
    assert not app.exception, [item.message for item in app.exception]


def test_run_pages_selection_and_on_demand_exports():
    app = small_app()
    button(app, "Run full assessment").click().run()
    assert not app.exception
    original = app.session_state.assessment_run
    assert original.results[0].successful
    for page in ["09 Campaign summary", "10 Annual hindcast", "11 Planning estimate",
                 "12 Monthly statistics", "13 Detailed-results summary", "14 QA and downtime breakdown"]:
        visit(app, page)
    visit(app, "03 Campaign settings")
    next(item for item in app.selectbox if item.label == "Detailed results basis").set_value("P0 (no weather)")
    button(app, "Apply campaign settings").click().run()
    assert not app.exception
    assert app.session_state.assessment_run is original
    visit(app, "15 Reports and export")
    assert app.session_state.export_cache == {}
    button(app, "Generate report").click().run()
    assert not app.exception
    assert not app.error
    assert len(app.session_state.export_cache) == 1


def test_p0_without_weather_and_empty_hindcast_pages():
    app = small_app(p0=True)
    for page in ["13 Detailed-results summary", "14 QA and downtime breakdown", "09 Campaign summary",
                 "10 Annual hindcast", "11 Planning estimate", "12 Monthly statistics", "15 Reports and export"]:
        visit(app, page)
    button(app, "Generate report").click().run()
    assert not app.error
    assert app.session_state.assessment_run.p0.duration_hours == 1.25


def test_no_successful_scenarios_do_not_crash_results_pages():
    app = small_app(bad_weather=True)
    button(app, "Run quick assessment").click().run()
    assert not app.exception
    assert not app.session_state.assessment_run.results[0].successful
    for page in ["09 Campaign summary", "10 Annual hindcast", "11 Planning estimate", "12 Monthly statistics"]:
        visit(app, page)


def test_bundled_project_startup():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    assert not app.exception, [item.message for item in app.exception]
    assert len(app.session_state.activities_df) == 45
    visit(app, "07 Generated sequence")
    assert not app.error
