from __future__ import annotations

from datetime import timedelta

import math
import pandas as pd

from .models import Activity, CampaignSettings, Location, SafeToSafeGroup, SequenceItem, SimulationResult


def build_sequence(
    settings: CampaignSettings,
    activities: list[Activity],
    learning_curve: dict[int, float],
    safe_to_safe_groups: list[SafeToSafeGroup] | None = None,
    locations: list[Location] | None = None,
) -> list[SequenceItem]:
    ordered = sorted(activities, key=lambda x: x.activity_id)
    group_lookup = {item.group_id: item for item in (safe_to_safe_groups or [])}
    by_type = {activity_type: [a for a in ordered if a.activity_type == activity_type] for activity_type in (1, 2, 3)}
    total_cycles = math.ceil(settings.total_positions / settings.positions_per_cycle)
    sequence: list[SequenceItem] = []
    sequence_no = 1

    for cycle in range(1, total_cycles + 1):
        first_position = (cycle - 1) * settings.positions_per_cycle + 1
        remaining = settings.total_positions - first_position + 1
        positions_this_cycle = min(settings.positions_per_cycle, max(0, remaining))
        multiplier = float(learning_curve.get(cycle, 1.0) or 1.0)

        for activity in by_type[1]:
            applied = 1.0 if activity.no_learning_curve else multiplier
            sequence.append(_make_item(sequence_no, cycle, None, activity, applied, group_lookup, settings.default_safe_to_safe_method))
            sequence_no += 1

        for offset in range(positions_this_cycle):
            position = first_position + offset
            for activity in by_type[2]:
                applied = 1.0 if activity.no_learning_curve else multiplier
                sequence.append(_make_item(sequence_no, cycle, position, activity, applied, group_lookup, settings.default_safe_to_safe_method))
                sequence_no += 1

        for activity in by_type[3]:
            applied = 1.0 if activity.no_learning_curve else multiplier
            sequence.append(_make_item(sequence_no, cycle, None, activity, applied, group_lookup, settings.default_safe_to_safe_method))
            sequence_no += 1

    timezones = {location.location_id: location.timezone for location in (locations or [])}
    for item in sequence:
        item.timezone = timezones.get(item.location_id, "UTC")
    _annotate_group_roles(sequence)
    return sequence


def _annotate_group_roles(sequence: list[SequenceItem]) -> None:
    """Mark consecutive safe-to-safe blocks in each generated sequence instance.

    A group is intentionally limited to one generated cycle/position instance.
    The input validator ensures that members of a group use one activity type and
    are consecutive in the base activity register.
    """
    index = 0
    while index < len(sequence):
        item = sequence[index]
        group_id = item.safe_to_safe_group.strip()
        if not group_id:
            item.group_role = "Standalone"
            index += 1
            continue

        end = index + 1
        while end < len(sequence):
            candidate = sequence[end]
            if (
                candidate.safe_to_safe_group.strip() != group_id
                or candidate.cycle != item.cycle
                or candidate.position != item.position
            ):
                break
            end += 1

        size = end - index
        if size == 1:
            sequence[index].group_role = "Single"
        else:
            sequence[index].group_role = "Start"
            for member_index in range(index + 1, end - 1):
                sequence[member_index].group_role = "Continue"
            sequence[end - 1].group_role = "End"
        index = end


def _make_item(
    sequence_no: int,
    cycle: int,
    position: int | None,
    activity: Activity,
    multiplier: float,
    group_lookup: dict[str, SafeToSafeGroup],
    default_group_method: str,
) -> SequenceItem:
    duration = float(activity.duration_hours * multiplier)
    group = group_lookup.get(activity.safe_to_safe_group)
    method = (group.assessment_method if group is not None else default_group_method) if activity.safe_to_safe_group else ""
    assessment_location = group.assessment_location if group is not None else ""
    return SequenceItem(
        sequence_no=sequence_no,
        cycle=cycle,
        position=position,
        activity_id=activity.activity_id,
        activity_type=activity.activity_type,
        learning_multiplier=multiplier,
        milestone=activity.milestone,
        description=activity.description,
        location_id=activity.location_id,
        duration_hours=duration,
        weather_window_hours=activity.weather_window_hours,
        wind10_limit=activity.wind10_limit,
        wind100_limit=activity.wind100_limit,
        hs_limit=activity.hs_limit,
        tp_limit=activity.tp_limit,
        current_limit=activity.current_limit,
        time_start=activity.time_start,
        time_end=activity.time_end,
        hstp_curve=activity.hstp_curve,
        remarks=activity.remarks,
        safe_to_safe_group=activity.safe_to_safe_group,
        group_method=str(method or "MOST_STRINGENT").upper() if activity.safe_to_safe_group else "",
        group_assessment_location=assessment_location,
    )


def sequence_dataframe(sequence: list[SequenceItem]) -> pd.DataFrame:
    return pd.DataFrame([item.to_dict() for item in sequence])


def no_weather_summary(sequence: list[SequenceItem], settings: CampaignSettings) -> dict:
    result = p0_simulation_result(sequence, settings)
    return {
        "duration_hours": result.duration_hours,
        "duration_days": result.duration_hours / 24.0,
        "average_hours_per_position": result.duration_hours / settings.total_positions,
        "position_elapsed_hours": dict(result.position_completion_elapsed_hours),
    }


def p0_trace_dataframe(sequence: list[SequenceItem], settings: CampaignSettings) -> pd.DataFrame:
    """Build the exact continuous deterministic P0 activity trace.

    P0 is intentionally independent of the weather-simulation timestep. Each
    activity starts at the exact finish of the preceding learning-adjusted
    activity and has zero weather downtime.
    """
    start = pd.Timestamp(settings.nominal_year, settings.start_month, settings.start_day)
    current = start
    total = float(sum(float(item.duration_hours) for item in sequence))
    elapsed = 0.0
    rows: list[dict] = []
    for item in sorted(sequence, key=lambda x: int(x.sequence_no)):
        duration = float(item.duration_hours)
        finish = current + pd.Timedelta(hours=duration)
        elapsed += duration
        rows.append({
            "Timestamp": current,
            "End timestamp": finish,
            "Duration [h]": duration,
            "Activity": item.description,
            "Location": item.location_id,
            "Status": "Working",
            "Cycle": int(item.cycle),
            "Position": item.position,
            "Activity ID": int(item.activity_id),
            "Learning multiplier": float(item.learning_multiplier),
            "Safe-to-safe group": item.safe_to_safe_group,
            "Group role": item.group_role,
            "Group method": item.group_method,
            "Weather window [h]": float(item.weather_window_hours),
            "Cumulative P0 [h]": elapsed,
            "Remaining campaign [h]": max(0.0, total - elapsed),
            "Downtime type": "",
            "Main factor": "",
            "Downtime category": "",
        })
        current = finish
    return pd.DataFrame(rows)


def p0_simulation_result(sequence: list[SequenceItem], settings: CampaignSettings) -> SimulationResult:
    """Return a SimulationResult-compatible deterministic P0 schedule."""
    trace = p0_trace_dataframe(sequence, settings)
    campaign_start = pd.Timestamp(settings.nominal_year, settings.start_month, settings.start_day).to_pydatetime()
    duration = float(trace["Duration [h]"].sum()) if not trace.empty else 0.0
    campaign_finish = campaign_start + timedelta(hours=duration)
    completion_dates: dict[int, object] = {}
    completion_elapsed: dict[int, float] = {}
    item_map = {(int(x.cycle), x.position, int(x.activity_id)): x for x in sequence}
    for _, row in trace.iterrows():
        position = row.get("Position")
        if position is None or pd.isna(position):
            continue
        pos = int(position)
        item = item_map.get((int(row["Cycle"]), pos, int(row["Activity ID"])))
        if item is not None and item.milestone:
            finish = pd.Timestamp(row["End timestamp"]).to_pydatetime()
            completion_dates[pos] = finish
            completion_elapsed[pos] = (finish - campaign_start).total_seconds() / 3600.0
    working_by_location: dict[str, float] = {}
    if not trace.empty:
        for location, group in trace.groupby("Location"):
            working_by_location[str(location)] = float(group["Duration [h]"].sum())
    return SimulationResult(
        start_year=settings.nominal_year, successful=True, message="P0 - no weather",
        campaign_start=campaign_start, campaign_finish=campaign_finish, duration_hours=duration,
        working_hours=duration, downtime_hours=0.0, position_completion_dates=completion_dates,
        position_completion_elapsed_hours=completion_elapsed, working_by_location=working_by_location,
        trace=trace, exact_p0_hours=duration, timestep_adjustment_hours=0.0,
    )

