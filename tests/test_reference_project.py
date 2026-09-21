"""Release reference values protect engineering behavior during restructuring."""
from pathlib import Path

import pytest

from weather_assessment.assessment import run_assessment
from weather_assessment.input_workbook import load_project_input_workbook
from weather_assessment.planning import representative_result
from weather_assessment.statistics import successful_results
from weather_assessment.weather import load_weather_csv


def test_rev2k3_published_reference_and_reconciliation():
    root = Path(__file__).resolve().parents[1]
    settings, locations, activities, bins, learning, groups = load_project_input_workbook(
        (root / "Review_examples/YHO_FEM2_Project_Input_MultiLocation_Rev.2K_3.xlsx").read_bytes())
    frame = load_weather_csv(
        (root / "FM2_WF_weathe_reconciled_Rev.0.csv").read_bytes(), 0, ",",
        dict(zip(["timestamp", "wind10", "wind100", "hs", "tp", "current"],
                 ["Timestamp", "Wind10", "Wind100", "Hs", "Tp", "Current"])),
        False, "%Y-%m-%d %H:%M:%S")
    run = run_assessment(settings, locations, activities, bins, learning, groups,
                         {loc.location_id: frame for loc in locations}, full=True)
    results = run.results
    valid = successful_results(results)
    representative, target = representative_result(results, 50)
    assert run.p0.duration_hours == pytest.approx(2747.9)
    assert (len(valid), len(results)) == (44, 45)
    assert representative.start_year == 1984
    assert target / 24 == pytest.approx(169.198, abs=0.001)
    for result in valid:
        assert result.duration_hours == pytest.approx(result.working_hours + result.downtime_hours)
        assert result.working_hours == pytest.approx(result.exact_p0_hours + result.timestep_adjustment_hours)
        assert sum(result.downtime_by_cause.values()) == pytest.approx(result.downtime_hours)
        assert sum(row["working_hours"] + row["downtime_hours"] for row in result.planning_monthly_records) == pytest.approx(result.duration_hours)
    detail = run.detail(settings)
    if detail is not None and detail.trace is not None:
        assert detail.trace["Duration [h]"].sum() == pytest.approx(detail.duration_hours)
