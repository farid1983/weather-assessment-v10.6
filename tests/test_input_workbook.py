from __future__ import annotations

from weather_assessment.defaults import (
    default_activities,
    default_hstp_bins,
    default_learning_curve,
    default_locations,
    default_settings,
)
from weather_assessment.input_workbook import build_project_input_workbook, load_project_input_workbook
from weather_assessment.validation import validate_inputs
from weather_assessment.models import SafeToSafeGroup


def test_project_input_workbook_round_trip():
    original_settings = default_settings()
    original_locations = default_locations()
    original_activities = default_activities()
    original_activities[7].safe_to_safe_group = "G1"
    original_activities[8].safe_to_safe_group = "G1"
    original_bins = default_hstp_bins()
    original_learning = default_learning_curve()
    original_groups = [SafeToSafeGroup("G1", "Test group", "MOST_STRINGENT", "OFFSHORE", "")]

    data = build_project_input_workbook(
        original_settings,
        original_locations,
        original_activities,
        original_bins,
        original_learning,
        original_groups,
        app_version="0.10.5",
    )
    settings, locations, activities, bins, learning, groups = load_project_input_workbook(data)

    assert settings.project_name == original_settings.project_name
    assert settings.percentiles == original_settings.percentiles
    assert settings.detailed_results_basis == "Percentile 1 representative hindcast year"
    assert settings.year_of_interest is None
    assert len(locations) == len(original_locations)
    assert {item.location_id for item in locations} == {"PORT", "TRANSIT", "OFFSHORE"}
    assert len(activities) == len(original_activities)
    assert activities[9].milestone is True
    assert activities[9].location_id == "OFFSHORE"
    assert activities[7].safe_to_safe_group == "G1"
    assert activities[8].safe_to_safe_group == "G1"
    assert len(bins) == len(original_bins)
    assert learning == original_learning
    assert groups[0].assessment_method == "MOST_STRINGENT"
    assert groups[0].assessment_location == "OFFSHORE"
    assert validate_inputs(settings, activities, bins, learning, locations, safe_to_safe_groups=groups) == []


def test_excel_numeric_time_is_converted_to_hhmm():
    from weather_assessment.input_workbook import _as_time

    assert _as_time(0) == "00:00"
    assert _as_time(0.5) == "12:00"
    assert _as_time(0.75) == "18:00"
    assert _as_time("6:30") == "06:30"
