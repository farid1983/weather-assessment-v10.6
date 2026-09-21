from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from weather_assessment.defaults import default_activities, default_settings
from weather_assessment.export import _column_format, _specific_month_statistics
from weather_assessment.input_workbook import _as_time
from weather_assessment.models import Activity, Location, SafeToSafeGroup, SimulationResult
from weather_assessment.planning import planning_monthly_dataframe
from weather_assessment.sequence import build_sequence
from weather_assessment.simulator import simulate_year
from weather_assessment.validation import validate_inputs
from weather_assessment.weather import prepare_weather, weather_fingerprint


def weather(periods=48, freq="h"):
    return pd.DataFrame({
        "timestamp": pd.date_range("1990-01-01", periods=periods, freq=freq),
        **{name: 0.0 for name in ("wind10", "wind100", "hs", "tp", "current")},
    })


def project():
    settings = default_settings()
    settings.total_positions = settings.positions_per_cycle = 1
    activity = default_activities()[0]
    activity.activity_type = 2
    activity.milestone = True
    activity.duration_hours = activity.weather_window_hours = 1.0
    activity.location_id = "A"
    return settings, [activity]


@pytest.mark.parametrize("field", ["duration_hours", "weather_window_hours", "wind10_limit"])
@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_nonfinite_activity_values_are_rejected(field, value):
    settings, activities = project()
    setattr(activities[0], field, value)
    assert validate_inputs(settings, activities, [], {1: 1.0})


def test_group_assessment_location_is_required_weather():
    settings, activities = project()
    second = Activity.from_dict({**activities[0].to_dict(), "activity_id": 2, "milestone": False})
    activities.append(second)
    for activity in activities:
        activity.safe_to_safe_group = "G"
    groups = [SafeToSafeGroup("G", assessment_location="B")]
    errors = validate_inputs(settings, activities, [], {1: 1.0},
                             [Location("A", "A"), Location("B", "B")], {"A"}, groups)
    assert any("B" in error and "Weather" in error for error in errors)
    with pytest.raises(ValueError, match="assessment location"):
        simulate_year({"A": weather()}, build_sequence(settings, activities, {1: 1.0}, groups), [], settings, 1990)


def test_downsampling_does_not_silently_discard_an_exceedance():
    frame = weather(5, "30min")
    frame.loc[1, "wind10"] = 100.0
    with pytest.raises(ValueError, match="resolution|downsampl"):
        prepare_weather(frame, 1.0)


def test_duplicate_weather_requires_resolution():
    frame = weather()
    frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        prepare_weather(frame, 1.0)


@pytest.mark.parametrize("value", [-999.0, float("nan"), float("inf")])
def test_invalid_weather_values_are_rejected(value):
    frame = weather()
    frame.loc[1, "hs"] = value
    with pytest.raises(ValueError, match="weather|Weather"):
        prepare_weather(frame, 1.0)


def test_fingerprint_covers_every_weather_row():
    frame = weather(4000)
    changed = frame.copy()
    changed.loc[1, "hs"] = 100.0
    assert weather_fingerprint(frame) != weather_fingerprint(changed)


def test_excel_formats_use_units_instead_of_value_magnitude():
    formats = {name: name for name in ("center", "datetime", "percent", "percent100", "integer", "number", "text")}
    assert _column_format(None, pd.Series([0.5, 1.0]), "% of campaign time", formats) == "percent100"
    assert _column_format(None, pd.Series([0.005, 0.01]), "Downtime [%]", formats) == "percent"
    assert _column_format(None, pd.Series([1.25, 2.75]), "P50 positions", formats) == "number"


def crossing_scenarios():
    """Two coherent scenarios finish ten positions in different months."""
    results = []
    for year, days in [(1990, 10), (1991, 50)]:
        start = datetime(year, 1, 1)
        first = days == 10
        records = [{"Calendar year": 2026, "Month": 1, "positions_completed": 10 if first else 0,
                    "working_hours": 240.0, "downtime_hours": 0.0 if first else 504.0}]
        if not first:
            records.append({"Calendar year": 2026, "Month": 2, "positions_completed": 10,
                            "working_hours": 0.0, "downtime_hours": 456.0})
        results.append(SimulationResult(
            year, True, "Completed", start, start + timedelta(days=days), days * 24., 240., (days - 10) * 24.,
            position_completion_elapsed_hours={pos: days * 24. for pos in range(1, 11)},
            planning_monthly_records=records,
        ))
    return results


def test_excel_monthly_progress_consumes_shared_statistics():
    settings = default_settings()
    settings.total_positions = 10
    results = crossing_scenarios()
    canonical = planning_monthly_dataframe(results, settings)
    exported = _specific_month_statistics(results, settings)
    assert canonical.iloc[0]["cumulative_positions P50"] == 5.0
    assert exported.iloc[0]["Cumulative positions - P50"] == 5.0
    # Hours are percentiles of scenario monthly hours, not rate * percentile duration.
    assert exported.iloc[0]["Downtime hours - P50"] == 252.0
    assert exported.iloc[1]["Cumulative positions - P90"] == 10.0


def test_non_utc_location_allowed_window_is_evaluated_in_local_time():
    from weather_assessment.assessment import run_assessment
    settings, activities = project()
    activities[0].time_start = "08:00"
    activities[0].time_end = "09:00"
    run = run_assessment(settings, [Location("A", "A", timezone="Asia/Taipei")], activities,
                         [], {1: 1.0}, [], {"A": weather()})
    # 00:00 UTC is 08:00 Taipei. There must be no eight-hour UTC-clock wait.
    assert run.results[0].downtime_hours == 0.0
    assert run.results[0].duration_hours == 1.0


@pytest.mark.parametrize("value", ["25:99", "24:00", "01:60"])
def test_invalid_workbook_times_are_not_wrapped(value):
    with pytest.raises(ValueError):
        _as_time(value)


def test_string_boolean_false_is_false():
    _, activities = project()
    parsed = Activity.from_dict({**activities[0].to_dict(), "milestone": "false", "no_learning_curve": "false"})
    assert parsed.milestone is False
    assert parsed.no_learning_curve is False


@pytest.mark.parametrize("percentiles", [(50, 50, 90), (50,), (50, 75, np.nan)])
def test_invalid_percentile_configuration_is_rejected(percentiles):
    settings, activities = project()
    settings.percentiles = percentiles
    assert validate_inputs(settings, activities, [], {1: 1.0})


def test_csv_source_timezone_and_explicit_offsets():
    from weather_assessment.weather import load_weather_csv
    data = b"time,w10,w100,hs,tp,c\n1990-01-01 08:00,0,0,0,0,0\n1990-01-01T01:00:00Z,0,0,0,0,0\n"
    frame = load_weather_csv(data, 0, ",", dict(zip(
        ["timestamp", "wind10", "wind100", "hs", "tp", "current"],
        ["time", "w10", "w100", "hs", "tp", "c"])), source_timezone="Asia/Taipei")
    assert frame["timestamp"].tolist() == [pd.Timestamp("1990-01-01 00:00"), pd.Timestamp("1990-01-01 01:00")]


def test_distinct_activities_with_same_description_remain_separate():
    from weather_assessment.statistics import downtime_breakdown_dataframe, downtime_detail_frames
    settings, activities = project()
    first = activities[0]
    first.description = "Lift"
    first.wind10_limit = 10
    second = Activity.from_dict({**first.to_dict(), "activity_id": 2, "milestone": False})
    frame = weather()
    frame.loc[[0, 2], "wind10"] = 100
    result = simulate_year({"A": frame}, build_sequence(settings, [first, second], {1: 1}), [], settings, 1990, include_trace=True)
    _, summary = downtime_breakdown_dataframe(result)
    _, detail, _ = downtime_detail_frames(result)
    assert result.downtime_by_activity_id == {1: 1., 2: 1.}
    assert set(summary["Activity"]) == set(detail["Activity"]) == {"1: Lift", "2: Lift"}
    assert detail["Total WDT [h]"].sum() == result.downtime_hours
