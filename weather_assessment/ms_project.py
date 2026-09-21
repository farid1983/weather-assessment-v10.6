from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Iterable
from xml.etree import ElementTree as ET

import pandas as pd

from .models import CampaignSettings, SequenceItem, SimulationResult
from .planning import planning_start

MSPDI_NS = "http://schemas.microsoft.com/project"
ET.register_namespace("", MSPDI_NS)

# Local Microsoft Project task custom fields.
# Native Duration is the baseline productive duration. Number2 carries weather downtime.
PLAN_DURATION_FIELD_ID = "188743767"  # legacy Task Number1, retained for API compatibility
DOWNTIME_FIELD_ID = "188743768"       # Task Number2
LOCATION_FIELD_ID = "188743731"       # Task Text1
POSITION_FIELD_ID = "188743734"       # Task Text2
ACTIVITY_ID_FIELD_ID = "188743737"    # Task Text3
SAFE_GROUP_FIELD_ID = "188743740"     # Task Text4


def _q(tag: str) -> str:
    return f"{{{MSPDI_NS}}}{tag}"


def _sub(parent: ET.Element, tag: str, value: object | None = None) -> ET.Element:
    element = ET.SubElement(parent, _q(tag))
    if value is not None:
        element.text = str(value)
    return element


def _iso_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat(timespec="seconds")


def _duration_xml(hours: float) -> str:
    total_seconds = max(0, int(round(float(hours) * 3600.0)))
    hours_whole, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"PT{hours_whole}H{minutes}M{seconds}S"


def _normal_position(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(float(value))


def _normal_int(value: object) -> int:
    return int(float(value))


def _sequence_key(item: SequenceItem) -> tuple[int, int | None, int]:
    return int(item.cycle), _normal_position(item.position), int(item.activity_id)


def _trace_key(row: pd.Series) -> tuple[int, int | None, int]:
    return (
        _normal_int(row["Cycle"]),
        _normal_position(row.get("Position")),
        _normal_int(row["Activity ID"]),
    )


@dataclass(slots=True)
class ProjectActivityTask:
    cycle: int
    sequence_no: int
    position: int | None
    activity_id: int
    name: str
    location: str
    safe_group: str
    milestone: bool
    planned_hours: float
    exact_planned_hours: float
    downtime_hours: float
    elapsed_hours: float
    historical_start: datetime
    historical_finish: datetime
    planning_start: datetime
    planning_finish: datetime


@dataclass(slots=True)
class ProjectCycleTask:
    cycle: int
    positions: list[int]
    activities: list[ProjectActivityTask]
    planned_hours: float
    downtime_hours: float
    elapsed_hours: float
    planning_start: datetime
    planning_finish: datetime


def build_cycle_task_model(
    settings: CampaignSettings,
    sequence: Iterable[SequenceItem],
    result: SimulationResult,
) -> list[ProjectCycleTask]:
    """Aggregate a representative simulation trace into cycle/activity tasks.

    The model contains one summary row per campaign cycle and one child row per
    generated sequence item. Weather waiting is not emitted as a separate task;
    it is rolled into the child activity's ``downtime_hours`` field.
    """
    if not result.successful:
        raise ValueError("Microsoft Project XML requires a completed representative simulation.")
    if result.trace is None or result.trace.empty:
        raise ValueError("Microsoft Project XML requires the representative-year detailed trace.")

    required = {"Timestamp", "End timestamp", "Duration [h]", "Status", "Cycle", "Activity ID"}
    missing = sorted(required - set(result.trace.columns))
    if missing:
        raise ValueError("Representative trace is missing required columns: " + ", ".join(missing))

    trace = result.trace.copy()
    trace["Timestamp"] = pd.to_datetime(trace["Timestamp"])
    trace["End timestamp"] = pd.to_datetime(trace["End timestamp"])
    grouped: dict[tuple[int, int | None, int], pd.DataFrame] = {
        key: group.sort_values("Timestamp")
        for key, group in trace.groupby(
            trace.apply(_trace_key, axis=1), sort=False
        )
    }

    nominal_start = planning_start(settings)
    historical_campaign_start = pd.Timestamp(result.campaign_start).to_pydatetime()
    cycle_map: dict[int, list[ProjectActivityTask]] = {}

    for item in sorted(sequence, key=lambda value: int(value.sequence_no)):
        key = _sequence_key(item)
        rows = grouped.get(key)
        if rows is None or rows.empty:
            raise ValueError(
                f"Representative trace has no rows for cycle {item.cycle}, "
                f"position {item.position}, activity {item.activity_id}."
            )
        start_hist = pd.Timestamp(rows["Timestamp"].min()).to_pydatetime()
        finish_hist = pd.Timestamp(rows["End timestamp"].max()).to_pydatetime()
        working = float(rows.loc[rows["Status"].astype(str).str.casefold() == "working", "Duration [h]"].sum())
        downtime = float(rows.loc[rows["Status"].astype(str).str.casefold() != "working", "Duration [h]"].sum())
        elapsed = (finish_hist - start_hist).total_seconds() / 3600.0
        start_plan = nominal_start + (start_hist - historical_campaign_start)
        finish_plan = nominal_start + (finish_hist - historical_campaign_start)

        task = ProjectActivityTask(
            cycle=int(item.cycle),
            sequence_no=int(item.sequence_no),
            position=_normal_position(item.position),
            activity_id=int(item.activity_id),
            name=str(item.description),
            location=str(item.location_id or ""),
            safe_group=str(item.safe_to_safe_group or ""),
            milestone=bool(item.milestone),
            planned_hours=float(item.duration_hours),
            exact_planned_hours=float(item.duration_hours),
            downtime_hours=downtime,
            elapsed_hours=elapsed,
            historical_start=start_hist,
            historical_finish=finish_hist,
            planning_start=start_plan,
            planning_finish=finish_plan,
        )
        cycle_map.setdefault(task.cycle, []).append(task)

    cycles: list[ProjectCycleTask] = []
    for cycle_no in sorted(cycle_map):
        activities = sorted(cycle_map[cycle_no], key=lambda item: item.sequence_no)
        positions = sorted({item.position for item in activities if item.position is not None})
        start = min(item.planning_start for item in activities)
        finish = max(item.planning_finish for item in activities)
        cycles.append(ProjectCycleTask(
            cycle=cycle_no,
            positions=positions,
            activities=activities,
            planned_hours=sum(item.planned_hours for item in activities),
            downtime_hours=sum(item.downtime_hours for item in activities),
            elapsed_hours=(finish - start).total_seconds() / 3600.0,
            planning_start=start,
            planning_finish=finish,
        ))
    return cycles


def project_task_list_dataframe(
    settings: CampaignSettings,
    sequence: Iterable[SequenceItem],
    result: SimulationResult,
) -> pd.DataFrame:
    """Return a review table matching the cycle-grouped XML task structure."""
    rows: list[dict[str, object]] = []
    for cycle in build_cycle_task_model(settings, sequence, result):
        if len(cycle.positions) == 1:
            position_label = f"Position {cycle.positions[0]}"
        elif cycle.positions:
            position_label = f"Positions {cycle.positions[0]}–{cycle.positions[-1]}"
        else:
            position_label = ""
        rows.append({
            "Outline level": 1,
            "WBS": str(cycle.cycle),
            "Task name": f"Cycle {cycle.cycle:02d}" + (f" — {position_label}" if position_label else ""),
            "Plan duration [days]": cycle.planned_hours / 24.0,
            "Downtime [days]": cycle.downtime_hours / 24.0,
            "Total duration [days]": cycle.elapsed_hours / 24.0,
            "Start": cycle.planning_start,
            "Finish": cycle.planning_finish,
            "Cycle": cycle.cycle,
            "Position": "",
            "Activity ID": "",
            "Location": "",
        })
        for index, activity in enumerate(cycle.activities, start=1):
            rows.append({
                "Outline level": 2,
                "WBS": f"{cycle.cycle}.{index}",
                "Task name": activity.name,
                "Plan duration [days]": activity.planned_hours / 24.0,
                "Downtime [days]": activity.downtime_hours / 24.0,
                "Total duration [days]": activity.elapsed_hours / 24.0,
                "Start": activity.planning_start,
                "Finish": activity.planning_finish,
                "Cycle": activity.cycle,
                "Position": activity.position if activity.position is not None else "",
                "Activity ID": activity.activity_id,
                "Location": activity.location,
            })
    return pd.DataFrame(rows)


def _add_custom_field_definition(parent: ET.Element, field_id: str, field_name: str, alias: str, cf_type: int) -> None:
    definition = _sub(parent, "ExtendedAttribute")
    _sub(definition, "FieldID", field_id)
    _sub(definition, "FieldName", field_name)
    _sub(definition, "CFType", cf_type)
    _sub(definition, "ElemType", 20)
    _sub(definition, "UserDef", 1)
    _sub(definition, "Alias", alias)
    if cf_type == 5:
        _sub(definition, "RollupType", 3)
        _sub(definition, "CalculationType", 1)


def _add_custom_value(task: ET.Element, field_id: str, value: object) -> None:
    attribute = _sub(task, "ExtendedAttribute")
    _sub(attribute, "FieldID", field_id)
    _sub(attribute, "Value", value)


def _add_calendar(root: ET.Element) -> None:
    calendars = _sub(root, "Calendars")
    calendar = _sub(calendars, "Calendar")
    _sub(calendar, "UID", 1)
    _sub(calendar, "Name", "24 Hours")
    _sub(calendar, "IsBaseCalendar", 1)
    _sub(calendar, "BaseCalendarUID", -1)
    week_days = _sub(calendar, "WeekDays")
    for day_type in range(1, 8):
        day = _sub(week_days, "WeekDay")
        _sub(day, "DayType", day_type)
        _sub(day, "DayWorking", 1)
        times = _sub(day, "WorkingTimes")
        working = _sub(times, "WorkingTime")
        _sub(working, "FromTime", "00:00:00")
        _sub(working, "ToTime", "23:59:59")


def _add_predecessor(task: ET.Element, predecessor_uid: int) -> None:
    link = _sub(task, "PredecessorLink")
    _sub(link, "PredecessorUID", predecessor_uid)
    _sub(link, "Type", 1)  # finish-to-start
    _sub(link, "CrossProject", 0)
    _sub(link, "LinkLag", 0)
    _sub(link, "LagFormat", 6)


def _add_task_core(
    tasks: ET.Element,
    *,
    uid: int,
    task_id: int,
    name: str,
    wbs: str,
    wbs_level: int,
    outline_level: int,
    start: datetime,
    finish: datetime,
    duration_hours: float,
    summary: bool,
    milestone: bool,
    notes: str,
    created: datetime,
    planned_days: float,
    downtime_days: float,
    location: str = "",
    position: str = "",
    activity_id: str = "",
    safe_group: str = "",
    predecessor_uid: int | None = None,
) -> ET.Element:
    task = _sub(tasks, "Task")
    _sub(task, "UID", uid)
    _sub(task, "ID", task_id)
    _sub(task, "Name", name)
    _sub(task, "Manual", 1)
    _sub(task, "Type", 1)
    _sub(task, "IsNull", 0)
    _sub(task, "CreateDate", _iso_datetime(created))
    _sub(task, "WBS", wbs)
    _sub(task, "WBSLevel", wbs_level)
    _sub(task, "OutlineNumber", wbs)
    _sub(task, "OutlineLevel", outline_level)
    _sub(task, "Priority", 500)
    _sub(task, "Start", _iso_datetime(start))
    _sub(task, "Finish", _iso_datetime(finish))
    _sub(task, "Duration", _duration_xml(duration_hours))
    _sub(task, "DurationFormat", 6)
    _sub(task, "Work", "PT0H0M0S")
    _sub(task, "ResumeValid", 0)
    _sub(task, "EffortDriven", 0)
    _sub(task, "Recurring", 0)
    _sub(task, "OverAllocated", 0)
    _sub(task, "Estimated", 0)
    _sub(task, "Milestone", 1 if milestone else 0)
    _sub(task, "Summary", 1 if summary else 0)
    _sub(task, "Critical", 1)
    _sub(task, "ConstraintType", 0)
    _sub(task, "CalendarUID", 1)
    _sub(task, "IgnoreResourceCalendar", 1)
    _sub(task, "Notes", notes)
    _sub(task, "ManualStart", _iso_datetime(start))
    _sub(task, "ManualFinish", _iso_datetime(finish))
    _sub(task, "ManualDuration", _duration_xml(duration_hours))
    if predecessor_uid is not None:
        _add_predecessor(task, predecessor_uid)
    _add_custom_value(task, DOWNTIME_FIELD_ID, f"{downtime_days:.6f}")
    _add_custom_value(task, LOCATION_FIELD_ID, location)
    _add_custom_value(task, POSITION_FIELD_ID, position)
    _add_custom_value(task, ACTIVITY_ID_FIELD_ID, activity_id)
    _add_custom_value(task, SAFE_GROUP_FIELD_ID, safe_group)
    return task


def build_ms_project_xml(
    settings: CampaignSettings,
    sequence: Iterable[SequenceItem],
    result: SimulationResult,
    *,
    app_version: str,
    percentile: float = 50.0,
    scenario_label: str | None = None,
) -> bytes:
    """Build a cycle-grouped preliminary Microsoft Project XML schedule.

    Native ``Duration`` is the exact learning-adjusted baseline productive
    duration. Custom ``Duration WDT [days]`` stores attributed weather/operational
    waiting. Manual Start/Finish retain the selected simulated schedule including
    timestep and weather effects.
    """
    cycles = build_cycle_task_model(settings, sequence, result)
    if not cycles:
        raise ValueError("No cycle tasks were available for Microsoft Project export.")

    now = datetime.now().replace(microsecond=0)
    start = cycles[0].planning_start
    finish = cycles[-1].planning_finish
    safe_project = "".join(ch if ch.isalnum() or ch in " _-." else "_" for ch in settings.project_name).strip() or "Weather Assessment"
    scenario = str(scenario_label or f"P{percentile:g}")
    is_p0 = scenario.upper() == "P0" or str(result.message).startswith("P0")
    is_percentile_scenario = scenario.upper().startswith("P") and not is_p0
    basis_note = (
        "P0 deterministic no-weather schedule" if is_p0 else
        (f"{scenario} representative hindcast year {result.start_year}"
         if is_percentile_scenario
         else f"selected hindcast year {result.start_year}")
    )

    root = ET.Element(_q("Project"))
    for tag, value in [
        ("SaveVersion", 14),
        ("Name", f"{safe_project}_{scenario}_Cycle_Grouped.xml"),
        ("Title", f"{safe_project} — {scenario} cycle-grouped preliminary schedule"),
        ("Subject", "Preliminary planning schedule with baseline Duration, Duration WDT and simulated Start/Finish"),
        ("Company", "Project review"),
        ("Author", f"Weather Assessment v{app_version}"),
        ("CreationDate", _iso_datetime(now)),
        ("LastSaved", _iso_datetime(now)),
        ("ScheduleFromStart", 1),
        ("StartDate", _iso_datetime(start)),
        ("FinishDate", _iso_datetime(finish)),
        ("FYStartDate", 1),
        ("CriticalSlackLimit", 0),
        ("CurrencyDigits", 2),
        ("CurrencySymbol", "$"),
        ("CurrencyCode", "USD"),
        ("CalendarUID", 1),
        ("DefaultStartTime", "00:00:00"),
        ("DefaultFinishTime", "23:59:59"),
        ("MinutesPerDay", 1440),
        ("MinutesPerWeek", 10080),
        ("DaysPerMonth", 30),
        ("DefaultTaskType", 1),
        ("DurationFormat", 6),
        ("WorkFormat", 2),
        ("NewTasksEffortDriven", 0),
        ("NewTasksEstimated", 0),
        ("SplitsInProgressTasks", 0),
    ]:
        _sub(root, tag, value)

    definitions = _sub(root, "ExtendedAttributes")
    _add_custom_field_definition(definitions, DOWNTIME_FIELD_ID, "Number2", "Duration WDT [days]", 5)
    _add_custom_field_definition(definitions, LOCATION_FIELD_ID, "Text1", "Location", 7)
    _add_custom_field_definition(definitions, POSITION_FIELD_ID, "Text2", "Position", 7)
    _add_custom_field_definition(definitions, ACTIVITY_ID_FIELD_ID, "Text3", "Activity ID", 7)
    _add_custom_field_definition(definitions, SAFE_GROUP_FIELD_ID, "Text4", "Safe-to-safe group", 7)

    _add_calendar(root)
    tasks = _sub(root, "Tasks")
    uid = 1
    task_id = 1
    previous_activity_uid: int | None = None

    for cycle in cycles:
        if cycle.positions:
            if len(cycle.positions) == 1:
                position_label = f"Position {cycle.positions[0]}"
            else:
                position_label = f"Positions {cycle.positions[0]}–{cycle.positions[-1]}"
            cycle_name = f"Cycle {cycle.cycle:02d} — {position_label}"
        else:
            cycle_name = f"Cycle {cycle.cycle:02d}"
        _add_task_core(
            tasks,
            uid=uid,
            task_id=task_id,
            name=cycle_name,
            wbs=str(cycle.cycle),
            wbs_level=1,
            outline_level=1,
            start=cycle.planning_start,
            finish=cycle.planning_finish,
            duration_hours=cycle.planned_hours,
            summary=True,
            milestone=False,
            notes=(
                f"{basis_note}; cycle {cycle.cycle}; "
                f"baseline duration {cycle.planned_hours / 24.0:.3f} days; "
                f"downtime {cycle.downtime_hours / 24.0:.3f} days; "
                f"elapsed duration {cycle.elapsed_hours / 24.0:.3f} days."
            ),
            created=now,
            planned_days=cycle.planned_hours / 24.0,
            downtime_days=cycle.downtime_hours / 24.0,
        )
        uid += 1
        task_id += 1

        for child_index, activity in enumerate(cycle.activities, start=1):
            current_uid = uid
            position_text = "" if activity.position is None else str(activity.position)
            notes = (
                f"Scenario: {scenario}; {basis_note}; "
                f"cycle: {activity.cycle}; activity ID: {activity.activity_id}; "
                f"location: {activity.location}; position: {position_text or 'n/a'}; "
                f"safe-to-safe group: {activity.safe_group or 'none'}; "
                f"baseline duration: {activity.exact_planned_hours:.3f} h; "
                f"weather/operational downtime: {activity.downtime_hours:.3f} h; "
                f"elapsed duration: {activity.elapsed_hours:.3f} h."
            )
            _add_task_core(
                tasks,
                uid=current_uid,
                task_id=task_id,
                name=activity.name,
                wbs=f"{cycle.cycle}.{child_index}",
                wbs_level=2,
                outline_level=2,
                start=activity.planning_start,
                finish=activity.planning_finish,
                duration_hours=activity.exact_planned_hours,
                summary=False,
                milestone=activity.milestone and activity.elapsed_hours <= 1e-9,
                notes=notes,
                created=now,
                planned_days=activity.planned_hours / 24.0,
                downtime_days=activity.downtime_hours / 24.0,
                location=activity.location,
                position=position_text,
                activity_id=str(activity.activity_id),
                safe_group=activity.safe_group,
                predecessor_uid=previous_activity_uid,
            )
            previous_activity_uid = current_uid
            uid += 1
            task_id += 1

    _sub(root, "Resources")
    _sub(root, "Assignments")
    ET.indent(root, space="  ")
    output = BytesIO()
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
    return output.getvalue()
