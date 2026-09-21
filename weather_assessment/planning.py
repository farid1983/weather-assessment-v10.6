from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from .models import CampaignSettings, SimulationResult
from .statistics import successful_results
from .policies import engineering_percentile


def planning_start(settings: CampaignSettings) -> datetime:
    """Return the nominal/planning campaign start date."""
    return datetime(settings.nominal_year, settings.start_month, settings.start_day)


def _percentile(values: np.ndarray, percentile: float, *, higher_is_better: bool = False) -> float:
    """Engineering assurance percentile.

    Adverse metrics use the ordinary upper-tail percentile. Beneficial metrics
    use the lower-tail exceedance convention, so P90 is the value achieved or
    exceeded in 90% of simulations (ordinary P10).
    """
    return engineering_percentile(values, percentile, higher_is_better=higher_is_better)





def is_p0_basis(settings: CampaignSettings) -> bool:
    """Return True when the detailed-results selection is deterministic P0."""
    basis = str(settings.detailed_results_basis or "").strip().lower()
    if basis in {"p0", "p0 (no weather)", "p0 - no weather", "deterministic p0"}:
        return True
    # Backward compatibility with v0.10.5 files where users obtained P0 by
    # setting one of the percentile slots to zero.
    if "percentile 1" in basis and settings.percentiles and float(settings.percentiles[0]) == 0.0:
        return True
    if "percentile 2" in basis and len(settings.percentiles) >= 2 and float(settings.percentiles[1]) == 0.0:
        return True
    if "percentile 3" in basis and len(settings.percentiles) >= 3 and float(settings.percentiles[2]) == 0.0:
        return True
    return False

def detailed_results_percentile(settings: CampaignSettings) -> float:
    """Return the percentile used for the selected detailed representative trace."""
    basis = str(settings.detailed_results_basis or "").strip().lower()
    if "percentile 2" in basis and len(settings.percentiles) >= 2:
        return float(settings.percentiles[1])
    if "percentile 3" in basis and len(settings.percentiles) >= 3:
        return float(settings.percentiles[2])
    return float(settings.percentiles[0])


def detailed_results_basis_display(settings: CampaignSettings) -> str:
    """Human-readable detailed-results selection for the UI and reports."""
    if is_p0_basis(settings):
        return "P0 (no weather)"
    if settings.detailed_results_basis == "Specific hindcast year" and settings.year_of_interest is not None:
        return f"Hindcast year {int(settings.year_of_interest)}"
    percentile = detailed_results_percentile(settings)
    basis = str(settings.detailed_results_basis or "")
    if "percentile 2" in basis.lower():
        index = 2
    elif "percentile 3" in basis.lower():
        index = 3
    else:
        index = 1
    return f"Percentile {index} representative hindcast year (P{percentile:g})"


def detailed_results_label(settings: CampaignSettings) -> str:
    """Short label used in selected-detail sheet names and export filenames."""
    if is_p0_basis(settings):
        return "P0"
    if settings.detailed_results_basis == "Specific hindcast year" and settings.year_of_interest is not None:
        return str(int(settings.year_of_interest))
    return f"P{detailed_results_percentile(settings):g}"


def selected_detailed_result(
    results: Iterable[SimulationResult],
    settings: CampaignSettings,
    detailed_result: SimulationResult | None = None,
) -> tuple[SimulationResult | None, str, float | None, bool]:
    """Resolve the single detailed scenario selected on Campaign settings.

    Returns ``(result, label, statistical_target_hours, is_percentile)``.
    For a specifically selected hindcast year the statistical target is ``None``.
    """
    label = detailed_results_label(settings)
    valid = list(results)
    if is_p0_basis(settings):
        # P0 has no hindcast representative. If a deterministic P0 result was
        # supplied by the caller, preserve it; otherwise return no weather result.
        return detailed_result, label, None, False
    if settings.detailed_results_basis == "Specific hindcast year" and settings.year_of_interest is not None:
        year = int(settings.year_of_interest)
        if detailed_result is not None and detailed_result.successful and int(detailed_result.start_year) == year:
            return detailed_result, label, None, False
        selected = next((item for item in valid if int(item.start_year) == year and item.successful), None)
        return selected, label, None, False

    percentile = detailed_results_percentile(settings)
    representative, target = representative_result(valid, percentile)
    if detailed_result is not None and representative is not None and int(detailed_result.start_year) == int(representative.start_year):
        representative = detailed_result
    return representative, label, target, True

def representative_result(
    results: Iterable[SimulationResult],
    percentile: float,
) -> tuple[SimulationResult | None, float | None]:
    """Return the historical result nearest to the duration percentile target."""
    valid = successful_results(results)
    if not valid:
        return None, None
    durations = np.asarray([result.duration_hours for result in valid], dtype=float)
    target = engineering_percentile(durations, percentile)
    selected = min(
        valid,
        key=lambda result: (abs(float(result.duration_hours) - target), result.start_year),
    )
    return selected, target


def representative_scenarios_dataframe(
    results: list[SimulationResult],
    settings: CampaignSettings,
) -> pd.DataFrame:
    start = planning_start(settings)
    rows: list[dict] = []
    for percentile in settings.percentiles:
        result, target = representative_result(results, percentile)
        if result is None or target is None:
            continue
        rows.append({
            "Planning scenario": f"P{percentile:g}",
            "Statistical duration [days]": target / 24.0,
            "Estimated finish": start + timedelta(hours=target),
            "Representative hindcast year": result.start_year,
            "Representative duration [days]": float(result.duration_hours) / 24.0,
            "Difference from target [days]": abs(float(result.duration_hours) - target) / 24.0,
        })
    return pd.DataFrame(rows)


def planning_summary_dataframe(
    results: list[SimulationResult],
    settings: CampaignSettings,
    p0_duration_hours: float | None = None,
) -> pd.DataFrame:
    valid = successful_results(results)
    if not valid:
        return pd.DataFrame()
    start = planning_start(settings)
    durations = np.asarray([result.duration_hours for result in valid], dtype=float)
    best = min(valid, key=lambda result: float(result.duration_hours))
    worst = max(valid, key=lambda result: float(result.duration_hours))

    rows: list[dict] = []
    if p0_duration_hours is not None:
        rows.append({
            "Scenario": "P0 (no weather)",
            "Representative weather year": None,
            "Duration [days]": p0_duration_hours / 24.0,
            "Planned start": start,
            "Estimated finish": start + timedelta(hours=p0_duration_hours),
            "Basis": "No-weather deterministic sequence",
        })

    rows.append({
        "Scenario": "Best historical scenario",
        "Representative weather year": best.start_year,
        "Duration [days]": float(best.duration_hours) / 24.0,
        "Planned start": start,
        "Estimated finish": start + timedelta(hours=float(best.duration_hours)),
        "Basis": f"Actual weather sequence from {best.start_year}",
    })

    for percentile in settings.percentiles:
        duration = engineering_percentile(durations, percentile)
        representative, _ = representative_result(valid, percentile)
        rows.append({
            "Scenario": f"P{percentile:g}",
            "Representative weather year": representative.start_year if representative else None,
            "Duration [days]": duration / 24.0,
            "Planned start": start,
            "Estimated finish": start + timedelta(hours=duration),
            "Basis": "Percentile across all successful historical start-year simulations",
        })

    rows.append({
        "Scenario": "Worst historical scenario",
        "Representative weather year": worst.start_year,
        "Duration [days]": float(worst.duration_hours) / 24.0,
        "Planned start": start,
        "Estimated finish": start + timedelta(hours=float(worst.duration_hours)),
        "Basis": f"Actual weather sequence from {worst.start_year}",
    })
    return pd.DataFrame(rows)


def planning_coverage_dataframe(results: list[SimulationResult]) -> pd.DataFrame:
    return pd.DataFrame({
        "Historical start year": [result.start_year for result in results],
        "Included in planning statistics": [bool(result.successful and result.duration_hours is not None) for result in results],
        "Message": [result.message for result in results],
    })


def planning_position_dataframe(
    results: list[SimulationResult],
    settings: CampaignSettings,
    p0_position_hours: dict[int, float] | None = None,
) -> pd.DataFrame:
    valid = successful_results(results)
    start = planning_start(settings)
    rows: list[dict] = []
    for position in range(1, settings.total_positions + 1):
        values = np.asarray([
            result.position_completion_elapsed_hours[position]
            for result in valid
            if position in result.position_completion_elapsed_hours
        ], dtype=float)
        row: dict = {"Position": position}
        if p0_position_hours and position in p0_position_hours:
            hours = float(p0_position_hours[position])
            row["P0 elapsed [days]"] = hours / 24.0
            row["P0 completion date"] = start + timedelta(hours=hours)
        if len(values):
            row["Best elapsed [days]"] = float(values.min()) / 24.0
            row["Best completion date"] = start + timedelta(hours=float(values.min()))
            for percentile in settings.percentiles:
                hours = engineering_percentile(values, percentile)
                row[f"P{percentile:g} elapsed [days]"] = hours / 24.0
                row[f"P{percentile:g} completion date"] = start + timedelta(hours=hours)
            row["Worst elapsed [days]"] = float(values.max()) / 24.0
            row["Worst completion date"] = start + timedelta(hours=float(values.max()))
        rows.append(row)
    return pd.DataFrame(rows)


def _period_from_offset(start: datetime, offset: int) -> pd.Period:
    return pd.Period(start, freq="M") + int(offset)


def _month_offset(result: SimulationResult, row: dict) -> int:
    year = int(row.get("Calendar year", row.get("Year", result.start_year)))
    month = int(row["Month"])
    return (year - result.campaign_start.year) * 12 + (month - result.campaign_start.month)


def _month_end(period: pd.Period) -> datetime:
    last_day = monthrange(period.year, period.month)[1]
    return datetime(period.year, period.month, last_day, 23, 59, 59, 999999)


def planning_monthly_dataframe(
    results: list[SimulationResult],
    settings: CampaignSettings,
) -> pd.DataFrame:
    """Map each historical simulation onto the planning calendar.

    All simulations use the same month/day start. Therefore monthly records can
    be shifted by campaign-month offset without inventing future weather. The
    table reports incremental and cumulative positions, downtime, and workable
    hours for the planned calendar months.
    """
    valid = successful_results(results)
    if not valid:
        return pd.DataFrame()

    start = planning_start(settings)
    max_duration = max(float(result.duration_hours) for result in valid)
    final_date = start + timedelta(hours=max_duration)
    start_period = pd.Period(start, freq="M")
    end_period = pd.Period(final_date, freq="M")
    periods = list(pd.period_range(start_period, end_period, freq="M"))

    scenario_months: dict[int, dict[pd.Period, dict[str, float]]] = {}
    scenario_cumulative: dict[int, dict[pd.Period, float]] = {}

    for result in valid:
        mapped: dict[pd.Period, dict[str, float]] = {}
        records = result.planning_monthly_records or result.monthly_records
        for record in records:
            if result.planning_monthly_records:
                period = pd.Period(
                    year=int(record.get("Calendar year", settings.nominal_year)),
                    month=int(record["Month"]),
                    freq="M",
                )
            else:
                offset = _month_offset(result, record)
                period = _period_from_offset(start, offset)
            bucket = mapped.setdefault(period, {
                "working_hours": 0.0,
                "downtime_hours": 0.0,
                "positions_completed": 0.0,
            })
            bucket["working_hours"] += float(record.get("working_hours", 0.0))
            bucket["downtime_hours"] += float(record.get("downtime_hours", 0.0))
            bucket["positions_completed"] += float(record.get("positions_completed", 0.0))
        scenario_months[result.start_year] = mapped

        mapped_completion_dates = [
            start + timedelta(hours=float(hours))
            for hours in result.position_completion_elapsed_hours.values()
        ]
        scenario_cumulative[result.start_year] = {
            period: float(sum(date <= _month_end(period) for date in mapped_completion_dates))
            for period in periods
        }

    rows: list[dict] = []
    for period in periods:
        incremental_values: list[float] = []
        cumulative_values: list[float] = []
        downtime_values: list[float] = []
        workable_values: list[float] = []
        downtime_hours_values: list[float] = []
        working_hours_values: list[float] = []
        active_count = 0

        for result in valid:
            record = scenario_months[result.start_year].get(period)
            incremental_values.append(float(record["positions_completed"]) if record else 0.0)
            cumulative_values.append(scenario_cumulative[result.start_year][period])
            downtime_hours_values.append(float(record["downtime_hours"]) if record else 0.0)
            working_hours_values.append(float(record["working_hours"]) if record else 0.0)
            if record:
                active = float(record["working_hours"] + record["downtime_hours"])
                if active > 0:
                    active_count += 1
                    downtime_values.append(float(record["downtime_hours"] / active))
                    workable_values.append(float(24.0 * record["working_hours"] / active))

        row: dict = {
            "Planning month": period.to_timestamp(),
            "Month": period.month,
            "Month name": period.strftime("%B %Y"),
            "Active scenarios": active_count,
            "positions_completed mean": float(np.mean(incremental_values)),
            "cumulative_positions mean": float(np.mean(cumulative_values)),
            "downtime_pct mean": float(np.mean(downtime_values)) if downtime_values else np.nan,
            "workable_hours_per_day mean": float(np.mean(workable_values)) if workable_values else np.nan,
            "downtime_hours mean": float(np.mean(downtime_hours_values)),
            "working_hours mean": float(np.mean(working_hours_values)),
        }

        incremental = np.asarray(incremental_values, dtype=float)
        cumulative = np.asarray(cumulative_values, dtype=float)
        downtime = np.asarray(downtime_values, dtype=float)
        workable = np.asarray(workable_values, dtype=float)

        for percentile in settings.percentiles:
            row[f"downtime_hours P{percentile:g}"] = _percentile(np.asarray(downtime_hours_values), percentile)
            row[f"working_hours P{percentile:g}"] = _percentile(np.asarray(working_hours_values), percentile, higher_is_better=True)
            row[f"positions_completed P{percentile:g}"] = _percentile(incremental, percentile, higher_is_better=True)
            row[f"cumulative_positions P{percentile:g}"] = _percentile(cumulative, percentile, higher_is_better=True)
            row[f"downtime_pct P{percentile:g}"] = (
                _percentile(downtime, percentile, higher_is_better=False) if len(downtime) else np.nan
            )
            row[f"workable_hours_per_day P{percentile:g}"] = (
                _percentile(workable, percentile, higher_is_better=True) if len(workable) else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)


def remapped_milestones_dataframe(
    result: SimulationResult,
    settings: CampaignSettings,
) -> pd.DataFrame:
    start = planning_start(settings)
    rows = []
    for position, hours in sorted(result.position_completion_elapsed_hours.items()):
        rows.append({
            "Position": position,
            "Elapsed [days]": float(hours) / 24.0,
            "Planned completion date": start + timedelta(hours=float(hours)),
            "Source completion date": result.position_completion_dates.get(position),
        })
    return pd.DataFrame(rows)


def remapped_monthly_dataframe(
    result: SimulationResult,
    settings: CampaignSettings,
) -> pd.DataFrame:
    start = planning_start(settings)
    rows: list[dict] = []
    cumulative = 0.0
    records = result.planning_monthly_records or result.monthly_records
    for record in records:
        if result.planning_monthly_records:
            period = pd.Period(
                year=int(record.get("Calendar year", settings.nominal_year)),
                month=int(record["Month"]),
                freq="M",
            )
            source_year = result.start_year
            source_month = None
        else:
            offset = _month_offset(result, record)
            period = _period_from_offset(start, offset)
            source_year = int(record.get("Calendar year", record.get("Year", result.start_year)))
            source_month = int(record["Month"])
        positions = float(record.get("positions_completed", 0.0))
        cumulative += positions
        rows.append({
            "Planning month": period.to_timestamp(),
            "Month name": period.strftime("%B %Y"),
            "positions_completed": positions,
            "cumulative_positions": cumulative,
            "working_hours": float(record.get("working_hours", 0.0)),
            "downtime_hours": float(record.get("downtime_hours", 0.0)),
            "downtime_pct": float(record.get("downtime_pct", np.nan)),
            "workable_hours_per_day": float(record.get("workable_hours_per_day", np.nan)),
            "Source weather start year": source_year,
            "Source month": source_month,
        })
    return pd.DataFrame(rows)
