from __future__ import annotations

import pandas as pd
import numpy as np

from weather_assessment.defaults import default_activities, default_hstp_bins, default_learning_curve, default_settings
from weather_assessment.sequence import build_sequence, no_weather_summary
from weather_assessment.simulator import simulate_year


def perfect_weather(start="1990-01-01", end="1992-12-31 23:00") -> pd.DataFrame:
    timestamps = pd.date_range(start, end, freq="1h")
    return pd.DataFrame({
        "timestamp": timestamps,
        "wind10": 0.0,
        "wind100": 0.0,
        "hs": 0.0,
        "tp": 0.0,
        "current": 0.0,
    })


def test_default_sequence_and_p0_duration():
    settings = default_settings()
    sequence = build_sequence(settings, default_activities(), default_learning_curve())
    assert len(sequence) == 380
    p0 = no_weather_summary(sequence, settings)
    assert p0["duration_hours"] == 1500
    assert len(p0["position_elapsed_hours"]) == 60


def test_perfect_weather_matches_no_weather_duration():
    settings = default_settings()
    settings.total_positions = 6
    sequence = build_sequence(settings, default_activities(), default_learning_curve())
    expected = no_weather_summary(sequence, settings)["duration_hours"]
    result = simulate_year(perfect_weather(), sequence, default_hstp_bins(), settings, 1990)
    assert result.successful
    assert result.duration_hours == expected
    assert result.downtime_hours == 0
    assert len(result.position_completion_dates) == 6


def test_weather_limit_equality_is_workable():
    settings = default_settings()
    settings.total_positions = 1
    activities = default_activities()
    for activity in activities:
        activity.wind10_limit = 10.0
        activity.wind100_limit = 10.0
        activity.hs_limit = 2.0
        activity.tp_limit = 8.0
        activity.current_limit = 1.0
    weather = perfect_weather()
    weather["wind10"] = 10.0
    weather["wind100"] = 10.0
    weather["hs"] = 2.0
    weather["tp"] = 8.0
    weather["current"] = 1.0
    sequence = build_sequence(settings, activities, default_learning_curve())
    result = simulate_year(weather, sequence, default_hstp_bins(), settings, 1990)
    assert result.successful
    assert result.downtime_hours == 0


def test_weather_loader_parses_full_iso_year_with_dayfirst(tmp_path):
    from weather_assessment.weather import load_weather_csv

    data = b"Timestamp,Wind10,Wind100,Hs,Tp,Current\n1990-01-12 00:00,1,1,1,1,1\n1990-01-13 00:00,1,1,1,1,1\n"
    frame = load_weather_csv(
        data, 0, ",",
        {"timestamp": "Timestamp", "wind10": "Wind10", "wind100": "Wind100", "hs": "Hs", "tp": "Tp", "current": "Current"},
        dayfirst=True,
    )
    assert len(frame) == 2
    assert frame.iloc[1]["timestamp"].day == 13


def test_monthly_percentile_direction_matches_engineering_assurance():
    """P90 is worse: high for downtime, low for productive outputs."""
    from datetime import datetime

    import numpy as np

    from weather_assessment.models import SimulationResult
    from weather_assessment.statistics import monthly_percentile_dataframe

    settings = default_settings()
    settings.percentiles = (50.0, 75.0, 90.0)
    results = []
    for i in range(1, 11):
        # Positions and workable hours increase with i; downtime also increases.
        # This intentionally makes the expected percentile direction obvious.
        results.append(SimulationResult(
            start_year=1989 + i,
            successful=True,
            message="",
            campaign_start=datetime(1989 + i, 1, 1),
            campaign_finish=datetime(1989 + i, 1, 2),
            duration_hours=24.0,
            working_hours=float(i),
            downtime_hours=float(10 - i),
            monthly_records=[{
                "Year": 1989 + i,
                "Month": 1,
                "Month name": "January",
                "working_hours": float(i),
                "downtime_hours": float(10 - i),
                "positions_completed": float(i),
            }],
        ))

    monthly = monthly_percentile_dataframe(results, settings)
    january = monthly.loc[monthly["Month"] == 1].iloc[0]

    # Beneficial metrics use exceedance/assurance percentiles: P90 = ordinary P10.
    assert np.isclose(january["positions_completed P50"], 5.5)
    assert np.isclose(january["positions_completed P75"], 3.25)
    assert np.isclose(january["positions_completed P90"], 1.9)
    assert january["positions_completed P90"] < january["positions_completed P75"] < january["positions_completed P50"]

    # Workable hours are also beneficial and must decrease toward P90.
    assert january["workable_hours_per_day P90"] < january["workable_hours_per_day P75"] < january["workable_hours_per_day P50"]

    # Downtime is adverse and keeps the ordinary upper-tail percentile direction.
    assert january["downtime_pct P90"] > january["downtime_pct P75"] > january["downtime_pct P50"]


def test_planning_estimate_maps_historical_results_to_future_year():
    from datetime import datetime, timedelta

    import numpy as np

    from weather_assessment.models import SimulationResult
    from weather_assessment.planning import (
        planning_monthly_dataframe,
        planning_position_dataframe,
        planning_summary_dataframe,
        representative_result,
    )

    settings = default_settings()
    settings.nominal_year = 2026
    settings.start_month = 5
    settings.start_day = 1
    settings.total_positions = 2
    settings.percentiles = (50.0, 75.0, 90.0)

    results = []
    durations = [100.0, 200.0, 300.0, 400.0]
    positions_by_year = [10.0, 8.0, 6.0, 4.0]
    for idx, duration in enumerate(durations):
        year = 2000 + idx
        start = datetime(year, 5, 1)
        results.append(SimulationResult(
            start_year=year,
            successful=True,
            message="Completed",
            campaign_start=start,
            campaign_finish=start + timedelta(hours=duration),
            duration_hours=duration,
            working_hours=duration * 0.7,
            downtime_hours=duration * 0.3,
            position_completion_dates={
                1: start + timedelta(hours=duration * 0.4),
                2: start + timedelta(hours=duration),
            },
            position_completion_elapsed_hours={1: duration * 0.4, 2: duration},
            monthly_records=[{
                "Calendar year": year,
                "Month": 5,
                "Month name": "May",
                "working_hours": 70.0,
                "downtime_hours": 30.0,
                "positions_completed": positions_by_year[idx],
                "downtime_pct": 0.3,
                "workable_hours_per_day": 16.8,
            }],
        ))

    summary = planning_summary_dataframe(results, settings)
    p50 = summary.loc[summary["Scenario"] == "P50"].iloc[0]
    assert np.isclose(p50["Duration [days]"], 250.0 / 24.0)
    assert p50["Planned start"].year == 2026
    assert p50["Estimated finish"].year == 2026

    positions = planning_position_dataframe(results, settings)
    assert positions.loc[positions["Position"] == 2, "P90 completion date"].iloc[0].year == 2026

    representative, target = representative_result(results, 90.0)
    assert np.isclose(target, 370.0)
    assert representative.start_year == 2003

    monthly = planning_monthly_dataframe(results, settings)
    may = monthly.loc[monthly["Month name"] == "May 2026"].iloc[0]
    # Productive output follows the assurance convention: P90 <= P75 <= P50.
    assert may["positions_completed P90"] <= may["positions_completed P75"] <= may["positions_completed P50"]
    assert may["cumulative_positions P90"] <= may["cumulative_positions P75"] <= may["cumulative_positions P50"]


def test_downtime_causes_are_mutually_exclusive_for_percentages():
    from weather_assessment.statistics import downtime_breakdown_dataframe

    settings = default_settings()
    settings.total_positions = 1
    activities = default_activities()
    for activity in activities:
        activity.wind10_limit = 10.0
        activity.wind100_limit = 10.0
        activity.hs_limit = 2.0
        activity.tp_limit = 8.0
        activity.current_limit = 1.0

    weather = perfect_weather()
    weather.loc[0, "wind10"] = 20.0
    weather.loc[0, "hs"] = 4.0
    sequence = build_sequence(settings, activities, default_learning_curve())
    result = simulate_year(weather, sequence, default_hstp_bins(), settings, 1990)

    assert result.successful
    assert result.downtime_hours == 1.0
    assert result.downtime_by_cause == {"Wind 10 m + Hs": 1.0}

    cause, _ = downtime_breakdown_dataframe(result)
    assert cause["% of total downtime"].sum() == 100.0
    assert cause.iloc[0]["Downtime cause"] == "Wind 10 m + Hs"


def test_multilocation_activity_uses_assigned_weather():
    from weather_assessment.defaults import default_locations
    from weather_assessment.models import Activity
    from weather_assessment.sequence import build_sequence
    from weather_assessment.simulator import simulate_year

    settings = default_settings()
    settings.total_positions = 1
    settings.positions_per_cycle = 1
    activities = [
        Activity(1, 2, True, True, "Offshore lift", "OFFSHORE", 2, 2, 10, 100, 100, 100, 100),
    ]
    sequence = build_sequence(settings, activities, {1: 1.0})
    port = perfect_weather("1990-01-01", "1990-01-05")
    offshore = port.copy()
    offshore.loc[:2, "wind10"] = 20.0
    result = simulate_year({"PORT": port, "OFFSHORE": offshore}, sequence, [], settings, 1990)
    assert result.successful
    assert result.downtime_hours == 3.0
    assert result.downtime_by_location["OFFSHORE"] == 3.0
    assert result.working_by_location["OFFSHORE"] == 2.0


def test_safe_to_safe_group_waits_for_complete_future_window():
    from weather_assessment.models import Activity, SafeToSafeGroup

    settings = default_settings()
    settings.total_positions = 1
    settings.positions_per_cycle = 1
    activities = [
        Activity(1, 2, True, False, "Tower preparation part 1", "OFFSHORE", 1, 1, 100, 100, 100, 100, 100, safe_to_safe_group="G1"),
        Activity(2, 2, True, False, "Tower preparation part 2 and rigging", "OFFSHORE", 1, 1, 100, 100, 100, 100, 100, safe_to_safe_group="G1"),
        Activity(3, 2, True, True, "Tower lifting safe to safe", "OFFSHORE", 1, 1, 10, 100, 100, 100, 100, safe_to_safe_group="G1"),
    ]
    sequence = build_sequence(settings, activities, {1: 1.0}, [SafeToSafeGroup("G1", assessment_method="TIME_PHASED", assessment_location="OFFSHORE")])
    assert [item.group_role for item in sequence] == ["Start", "Continue", "End"]

    weather = perfect_weather("1990-01-01", "1990-01-02")
    # At a proposed 00:00 group start, Activity 3 would occur at 02:00 and fail.
    # At a 01:00 start, Activity 3 occurs at 03:00 and the full group is workable.
    weather.loc[weather["timestamp"] == pd.Timestamp("1990-01-01 02:00"), "wind10"] = 20.0
    result = simulate_year(weather, sequence, [], settings, 1990, include_trace=True)

    assert result.successful
    assert result.downtime_hours == 1.0
    assert result.working_hours == 3.0
    assert result.duration_hours == 4.0
    assert result.downtime_by_group == {"G1": 1.0}
    assert result.trace is not None
    first = result.trace.iloc[0]
    assert first["Status"] == "Downtime"
    assert first["Safe-to-safe group"] == "G1"
    assert first["Blocking activity"] == "Tower lifting safe to safe"
    assert first["Blocking location"] == "OFFSHORE"
    assert first["Blocking timestamp"] == pd.Timestamp("1990-01-01 02:00")
    assert first["Blocking Wind 10 m"] == 20.0
    working = result.trace[result.trace["Status"] == "Working"]
    assert working["Timestamp"].tolist() == list(pd.date_range("1990-01-01 01:00", periods=3, freq="1h"))


def test_safe_to_safe_most_stringent_applies_lowest_limit_for_full_group_duration():
    from weather_assessment.models import Activity, SafeToSafeGroup

    settings = default_settings()
    settings.total_positions = 1
    settings.positions_per_cycle = 1
    activities = [
        Activity(1, 2, True, False, "Preparation", "OFFSHORE", 1, 1, 100, 100, 100, 100, 100, safe_to_safe_group="G1"),
        Activity(2, 2, True, False, "Rigging", "OFFSHORE", 1, 1, 100, 100, 100, 100, 100, safe_to_safe_group="G1"),
        Activity(3, 2, True, True, "Lift safe to safe", "OFFSHORE", 1, 1, 10, 100, 100, 100, 100, safe_to_safe_group="G1"),
    ]
    sequence = build_sequence(settings, activities, {1: 1.0}, [SafeToSafeGroup("G1", assessment_method="MOST_STRINGENT", assessment_location="OFFSHORE")])
    weather = perfect_weather("1990-01-01", "1990-01-02")
    weather.loc[weather["timestamp"] == pd.Timestamp("1990-01-01 02:00"), "wind10"] = 20.0
    result = simulate_year(weather, sequence, [], settings, 1990, include_trace=True)

    assert result.successful
    assert result.downtime_hours == 3.0
    assert result.duration_hours == 6.0
    first = result.trace.iloc[0]
    assert first["Group method"] == "MOST_STRINGENT"
    assert first["Blocking activity"] == "Lift safe to safe"
    assert first["Downtime category"] == "Wind 10 m"
    assert first["Downtime type"] == "Window pre-check"
    assert first["Duration [h]"] == 2.0
    direct = result.trace[result.trace["Downtime type"] == "Direct exceedance"].iloc[0]
    assert direct["Main factor"] == "Wind 10 m"
    assert direct["Duration [h]"] == 1.0


def test_safe_to_safe_group_validation_requires_consecutive_same_type_members():
    from weather_assessment.models import Activity
    from weather_assessment.validation import validate_inputs

    settings = default_settings()
    settings.total_positions = 1
    settings.positions_per_cycle = 1
    activities = [
        Activity(1, 2, True, False, "A", "OFFSHORE", 1, 1, 100, 100, 100, 100, 100, safe_to_safe_group="G1"),
        Activity(2, 2, True, False, "B", "OFFSHORE", 1, 1, 100, 100, 100, 100, 100),
        Activity(3, 2, True, True, "C", "OFFSHORE", 1, 1, 100, 100, 100, 100, 100, safe_to_safe_group="G1"),
    ]
    errors = validate_inputs(settings, activities, [], {1: 1.0})
    assert any("must be consecutive" in error for error in errors)


def test_p0_is_exact_and_independent_of_timestep():
    from weather_assessment.models import Activity
    from weather_assessment.sequence import no_weather_summary

    activity = Activity(1, 2, False, True, "Lift", "OFFSHORE", 3.5, 1.0, 100, 100, 100, 100, 100)
    values = []
    simulated = []
    for step in (0.25, 0.5):
        settings = default_settings()
        settings.total_positions = 1
        settings.positions_per_cycle = 1
        settings.timestep_hours = step
        sequence = build_sequence(settings, [activity], {1: 1.75})
        values.append(no_weather_summary(sequence, settings)["duration_hours"])
        from weather_assessment.weather import prepare_weather
        result = simulate_year(prepare_weather(perfect_weather("1990-01-01", "1990-01-03"), step), sequence, [], settings, 1990)
        assert result.successful
        simulated.append(result.working_hours)
        assert np.isclose(result.exact_p0_hours, 6.125)
    assert values == [6.125, 6.125]
    assert simulated == [6.25, 6.5]


def test_insufficient_window_identifies_future_wind_factor():
    from weather_assessment.models import Activity

    settings = default_settings()
    settings.total_positions = 1
    settings.positions_per_cycle = 1
    activities = [Activity(1, 2, True, True, "Lift", "OFFSHORE", 3, 3, 10, 100, 100, 100, 100)]
    sequence = build_sequence(settings, activities, {1: 1.0})
    weather = perfect_weather("1990-01-01", "1990-01-03")
    weather.loc[weather["timestamp"] == pd.Timestamp("1990-01-01 02:00"), "wind10"] = 20.0
    result = simulate_year(weather, sequence, [], settings, 1990, include_trace=True)
    assert result.successful
    assert result.downtime_by_cause["Wind 10 m"] == 3.0
    assert result.downtime_by_type_factor["Window pre-check"]["Wind 10 m"] == 2.0
    assert result.downtime_by_type_factor["Direct exceedance"]["Wind 10 m"] == 1.0
    assert result.downtime_by_main_factor == {"Wind 10 m": 3.0}


def test_hstp_curve_failure_is_attributed_to_hs():
    from weather_assessment.models import Activity, HsTpBin

    settings = default_settings()
    settings.total_positions = 1
    settings.positions_per_cycle = 1
    activities = [Activity(1, 2, True, True, "Curve lift", "OFFSHORE", 1, 1, 100, 100, 100, 100, 100, hstp_curve="C1")]
    sequence = build_sequence(settings, activities, {1: 1.0})
    weather = perfect_weather("1990-01-01", "1990-01-02")
    weather.loc[0, "hs"] = 2.0
    weather.loc[0, "tp"] = 10.0
    result = simulate_year(weather, sequence, [HsTpBin("C1", 0, 12, 1.0)], settings, 1990, include_trace=True)
    first = result.trace.iloc[0]
    assert first["Main factor"] == "Hs"
    assert first["Assessment basis"] == "Hs-Tp curve"
    assert "Combined Hs/Tp" not in result.downtime_by_cause


def test_hstp_curve_domain_failure_is_attributed_to_tp():
    from weather_assessment.models import Activity, HsTpBin

    settings = default_settings()
    settings.total_positions = 1
    settings.positions_per_cycle = 1
    activities = [Activity(1, 2, True, True, "Curve lift", "OFFSHORE", 1, 1, 100, 100, 100, 100, 100, hstp_curve="C1")]
    sequence = build_sequence(settings, activities, {1: 1.0})
    weather = perfect_weather("1990-01-01", "1990-01-02")
    weather.loc[0, "tp"] = 15.0
    result = simulate_year(weather, sequence, [HsTpBin("C1", 0, 12, 5.0)], settings, 1990, include_trace=True)
    first = result.trace.iloc[0]
    assert first["Main factor"] == "Tp"
    assert first["Assessment basis"] == "Hs-Tp curve range"


def test_end_of_weather_data_is_not_counted_as_weather_downtime():
    from weather_assessment.models import Activity

    settings = default_settings()
    settings.total_positions = 1
    settings.positions_per_cycle = 1
    activities = [Activity(1, 2, True, True, "Long task", "OFFSHORE", 4, 4, 100, 100, 100, 100, 100)]
    sequence = build_sequence(settings, activities, {1: 1.0})
    weather = perfect_weather("1990-01-01", "1990-01-01 01:00")
    result = simulate_year(weather, sequence, [], settings, 1990, include_trace=True)
    assert not result.successful
    assert result.data_coverage_limited
    assert result.downtime_hours == 0.0
    assert result.message == "Unable to assess - End of available weather data"
