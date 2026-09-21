from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from .models import CampaignSettings, SimulationResult
from .policies import engineering_percentile


def successful_results(results: Iterable[SimulationResult]) -> list[SimulationResult]:
    return [result for result in results if result.successful and result.duration_hours is not None]


def annual_dataframe(results: list[SimulationResult]) -> pd.DataFrame:
    return pd.DataFrame([result.annual_row() for result in results])


def campaign_summary_dataframe(
    results: list[SimulationResult],
    settings: CampaignSettings,
    p0_duration_hours: float,
) -> pd.DataFrame:
    valid = successful_results(results)
    if not valid:
        return pd.DataFrame()
    durations = np.array([result.duration_hours for result in valid], dtype=float)
    best = min(valid, key=lambda result: result.duration_hours or float("inf"))
    worst = max(valid, key=lambda result: result.duration_hours or -1)
    rows = [{
        "Scenario": "P0 (no weather)",
        "Hindcast year": None,
        "Duration [days]": p0_duration_hours / 24.0,
        "Duration [hours]": p0_duration_hours,
        "Nominal start": datetime(settings.nominal_year, settings.start_month, settings.start_day),
        "Nominal finish": datetime(settings.nominal_year, settings.start_month, settings.start_day) + timedelta(hours=p0_duration_hours),
    }]
    rows.append({
        "Scenario": "Best hindcast year", "Hindcast year": best.start_year,
        "Duration [days]": best.duration_hours / 24.0, "Duration [hours]": best.duration_hours,
        "Nominal start": best.campaign_start, "Nominal finish": best.campaign_finish,
    })
    for percentile in settings.percentiles:
        duration = engineering_percentile(durations, percentile)
        start = datetime(settings.nominal_year, settings.start_month, settings.start_day)
        rows.append({
            "Scenario": f"P{percentile:g}", "Hindcast year": None,
            "Duration [days]": duration / 24.0, "Duration [hours]": duration,
            "Nominal start": start, "Nominal finish": start + timedelta(hours=duration),
        })
    rows.append({
        "Scenario": "Worst hindcast year", "Hindcast year": worst.start_year,
        "Duration [days]": worst.duration_hours / 24.0, "Duration [hours]": worst.duration_hours,
        "Nominal start": worst.campaign_start, "Nominal finish": worst.campaign_finish,
    })
    return pd.DataFrame(rows)


def position_percentile_dataframe(
    results: list[SimulationResult],
    settings: CampaignSettings,
    p0_position_hours: dict[int, float],
) -> pd.DataFrame:
    valid = successful_results(results)
    rows: list[dict] = []
    for position in range(1, settings.total_positions + 1):
        values = np.array([
            result.position_completion_elapsed_hours[position]
            for result in valid
            if position in result.position_completion_elapsed_hours
        ], dtype=float)
        row = {"Position": position, "P0 [days]": p0_position_hours.get(position, np.nan) / 24.0}
        if len(values):
            row["Best [days]"] = float(values.min() / 24.0)
            for percentile in settings.percentiles:
                row[f"P{percentile:g} [days]"] = float(np.percentile(values, percentile, method="linear") / 24.0)
            row["Worst [days]"] = float(values.max() / 24.0)
        rows.append(row)
    return pd.DataFrame(rows)


def milestone_dates_dataframe(results: list[SimulationResult], total_positions: int) -> pd.DataFrame:
    rows = []
    for result in results:
        row: dict = {"Hindcast start year": result.start_year, "Successful": result.successful}
        for position in range(1, total_positions + 1):
            row[f"Position {position}"] = result.position_completion_dates.get(position)
        rows.append(row)
    return pd.DataFrame(rows)


def selected_year_monthly_dataframe(result: SimulationResult | None) -> pd.DataFrame:
    if result is None:
        return pd.DataFrame()
    return pd.DataFrame(result.monthly_records)


def _engineering_percentile(values: np.ndarray, percentile: float, *, higher_is_better: bool) -> float:
    """Return an engineering P-value using an assurance/exceedance convention.

    For adverse metrics such as duration or downtime, P90 is the ordinary
    90th percentile (a high/worse value). For beneficial metrics such as
    positions completed or workable hours, P90 is the value achieved or
    exceeded in 90% of simulations, i.e. the ordinary 10th percentile.
    """
    return engineering_percentile(values, percentile, higher_is_better=higher_is_better)


def monthly_percentile_dataframe(results: list[SimulationResult], settings: CampaignSettings) -> pd.DataFrame:
    valid = successful_results(results)
    by_month: dict[int, dict[str, list[float]]] = {
        month: {"positions_completed": [], "downtime_pct": [], "workable_hours_per_day": []}
        for month in range(1, 13)
    }
    for result in valid:
        aggregate = defaultdict(lambda: {"working_hours": 0.0, "downtime_hours": 0.0, "positions_completed": 0.0})
        for row in result.monthly_records:
            month = int(row["Month"])
            aggregate[month]["working_hours"] += float(row["working_hours"])
            aggregate[month]["downtime_hours"] += float(row["downtime_hours"])
            aggregate[month]["positions_completed"] += float(row["positions_completed"])
        for month in range(1, 13):
            values = aggregate[month]
            active = values["working_hours"] + values["downtime_hours"]
            by_month[month]["positions_completed"].append(values["positions_completed"])
            by_month[month]["downtime_pct"].append(values["downtime_hours"] / active if active else 0.0)
            by_month[month]["workable_hours_per_day"].append(24 * values["working_hours"] / active if active else 0.0)

    rows = []
    for month in range(1, 13):
        row = {"Month": month, "Month name": pd.Timestamp(2000, month, 1).month_name()}
        for metric, values in by_month[month].items():
            array = np.asarray(values, dtype=float)
            row[f"{metric} mean"] = float(np.mean(array)) if len(array) else np.nan
            higher_is_better = metric in {"positions_completed", "workable_hours_per_day"}
            for percentile in settings.percentiles:
                row[f"{metric} P{percentile:g}"] = (
                    _engineering_percentile(array, percentile, higher_is_better=higher_is_better)
                    if len(array) else np.nan
                )
        rows.append(row)
    return pd.DataFrame(rows)



def downtime_main_factor_dataframe(result: SimulationResult | None) -> pd.DataFrame:
    """Consolidate downtime by exact weather cause and assessment mechanism."""
    if result is None:
        return pd.DataFrame()
    total_downtime = float(result.downtime_hours or 0.0)
    direct = result.downtime_by_type_factor.get("Direct exceedance", {})
    window = result.downtime_by_type_factor.get("Window pre-check", result.downtime_by_type_factor.get("Insufficient weather window", {}))
    factors = sorted(
        set(result.downtime_by_main_factor) | set(direct) | set(window),
        key=lambda factor: float(result.downtime_by_main_factor.get(factor, 0.0)),
        reverse=True,
    )
    rows = []
    for factor in factors:
        direct_hours = float(direct.get(factor, 0.0))
        window_hours = float(window.get(factor, 0.0))
        total = float(result.downtime_by_main_factor.get(factor, direct_hours + window_hours))
        rows.append({
            "Main factor": factor,
            "Direct downtime [h]": direct_hours,
            "Window pre-check [h]": window_hours,
            "Total downtime [h]": total,
            "% of total downtime": total / total_downtime * 100.0 if total_downtime else 0.0,
        })
    return pd.DataFrame(rows)

def downtime_breakdown_dataframe(result: SimulationResult | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if result is None:
        return pd.DataFrame(), pd.DataFrame()
    total_downtime = float(result.downtime_hours or 0.0)
    total_campaign = float(result.duration_hours or (result.working_hours + result.downtime_hours) or 0.0)
    cause = pd.DataFrame(
        sorted(result.downtime_by_cause.items(), key=lambda item: item[1], reverse=True),
        columns=["Downtime cause", "Hours"],
    )
    if not cause.empty:
        cause["% of total downtime"] = (
            cause["Hours"] / total_downtime * 100.0 if total_downtime > 0 else 0.0
        )
        cause["% of campaign time"] = (
            cause["Hours"] / total_campaign * 100.0 if total_campaign > 0 else 0.0
        )
    activity_values = (
        {f"{activity_id}: {result.activity_descriptions.get(activity_id, '')}": hours
         for activity_id, hours in result.downtime_by_activity_id.items()}
        if result.downtime_by_activity_id else result.downtime_by_activity
    )
    activity = pd.DataFrame(
        sorted(activity_values.items(), key=lambda item: item[1], reverse=True),
        columns=["Activity", "Downtime hours"],
    )
    if not activity.empty:
        activity["% of total downtime"] = (
            activity["Downtime hours"] / total_downtime * 100.0 if total_downtime > 0 else 0.0
        )
        activity["% of campaign time"] = (
            activity["Downtime hours"] / total_campaign * 100.0 if total_campaign > 0 else 0.0
        )
    return cause, activity


def downtime_detail_frames(result: SimulationResult | None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return additive cause/mechanism, activity summary and activity-cause matrix.

    Cause is the exact weather criterion / criterion combination. Mechanism is
    either Direct exceedance or Window pre-check. Every downtime hour is counted
    once, so cause totals and the activity-cause matrix reconcile to campaign WDT.
    """
    if result is None or result.trace is None or result.trace.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    trace = result.trace.copy()
    if "Status" not in trace.columns or "Duration [h]" not in trace.columns:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    dt = trace.loc[trace["Status"].astype(str).str.casefold() == "downtime"].copy()
    if dt.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    for column in ("Main factor", "Downtime type", "Activity"):
        if column not in dt:
            dt[column] = ""
    dt["Cause combination"] = dt["Main factor"].fillna("").astype(str).replace("", "Unclassified weather downtime")
    dt["Mechanism"] = dt.get("Downtime type", "").fillna("").astype(str)
    dt["Mechanism"] = dt["Mechanism"].replace({"Insufficient weather window": "Window pre-check"})
    dt["Activity"] = dt.get("Activity", "").fillna("").astype(str)
    if "Activity ID" in dt:
        dt["Activity"] = [f"{int(activity_id)}: {description}" if pd.notna(activity_id) else description
                          for activity_id, description in zip(dt["Activity ID"], dt["Activity"])]
    dt["Duration [h]"] = pd.to_numeric(dt["Duration [h]"], errors="coerce").fillna(0.0)

    mechanism = dt.pivot_table(index="Cause combination", columns="Mechanism", values="Duration [h]", aggfunc="sum", fill_value=0.0)
    for column in ["Direct exceedance", "Window pre-check"]:
        if column not in mechanism.columns:
            mechanism[column] = 0.0
    mechanism = mechanism[["Direct exceedance", "Window pre-check"]].reset_index()
    mechanism.columns = ["Cause combination", "Direct [h]", "Window pre-check [h]"]
    mechanism["Total [h]"] = mechanism["Direct [h]"] + mechanism["Window pre-check [h]"]
    total = float(mechanism["Total [h]"].sum())
    campaign = float(result.duration_hours or (result.working_hours + result.downtime_hours) or 0.0)
    mechanism["% WDT"] = mechanism["Total [h]"] / total * 100.0 if total > 0 else 0.0
    mechanism["% campaign"] = mechanism["Total [h]"] / campaign * 100.0 if campaign > 0 else 0.0
    mechanism = mechanism.sort_values("Total [h]", ascending=False).reset_index(drop=True)

    activity_mech = dt.pivot_table(index="Activity", columns="Mechanism", values="Duration [h]", aggfunc="sum", fill_value=0.0)
    for column in ["Direct exceedance", "Window pre-check"]:
        if column not in activity_mech.columns:
            activity_mech[column] = 0.0
    activity_mech["Total WDT [h]"] = activity_mech["Direct exceedance"] + activity_mech["Window pre-check"]
    cause_by_activity = dt.groupby(["Activity", "Cause combination"], dropna=False)["Duration [h]"].sum().reset_index()
    dominant = (cause_by_activity.sort_values(["Activity", "Duration [h]"], ascending=[True, False])
                .drop_duplicates("Activity").set_index("Activity")["Cause combination"])
    activity = activity_mech.reset_index().rename(columns={"Direct exceedance": "Direct [h]", "Window pre-check": "Window pre-check [h]"})
    activity["% total WDT"] = activity["Total WDT [h]"] / total * 100.0 if total > 0 else 0.0
    activity["Dominant cause"] = activity["Activity"].map(dominant).fillna("")
    activity = activity.sort_values("Total WDT [h]", ascending=False).reset_index(drop=True)
    activity.insert(0, "Rank", range(1, len(activity) + 1))

    matrix = dt.pivot_table(index="Activity", columns="Cause combination", values="Duration [h]", aggfunc="sum", fill_value=0.0)
    cause_order = mechanism["Cause combination"].tolist()
    matrix = matrix.reindex(columns=[c for c in cause_order if c in matrix.columns], fill_value=0.0)
    matrix["Total WDT [h]"] = matrix.sum(axis=1)
    matrix["% total WDT"] = matrix["Total WDT [h]"] / total * 100.0 if total > 0 else 0.0
    matrix = matrix.sort_values("Total WDT [h]", ascending=False).reset_index()
    return mechanism, activity, matrix
