from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable

import numpy as np
import pandas as pd

from .models import CampaignSettings, HsTpBin, SequenceItem, SimulationResult
from .policies import finite_number, timestep_minutes
from .weather import validate_weather_frame

FACTOR_NAMES = [
    "Wind 10 m",
    "Wind 100 m",
    "Hs",
    "Tp",
    "Current speed",
    "Daylight / allowed time",
]
DIRECT_DOWNTIME = "Direct exceedance"
WINDOW_DOWNTIME = "Window pre-check"
DATA_LIMITATION = "Unable to assess - End of available weather data"


def _main_factor(causes: list[str]) -> str:
    """Return the exact blocking weather criterion combination.

    The combination is the downtime *cause*. Whether it was observed at the
    current timestamp or discovered in the required future window is retained
    separately as the downtime mechanism.
    """
    clean = list(dict.fromkeys(cause for cause in causes if cause))
    if not clean:
        return "Unclassified weather downtime"
    return " + ".join(clean)


def _display_cause(downtime_type: str, main_factor: str) -> str:
    # Cause and mechanism are deliberately separated in reporting.
    return main_factor


def _time_minutes(value: str) -> int:
    hours, minutes = [int(piece) for piece in str(value).split(":")[:2]]
    return hours * 60 + minutes


def _time_allowed(timestamps: pd.DatetimeIndex, start: str, end: str, timezone: str = "UTC") -> np.ndarray:
    start_min = _time_minutes(start)
    end_min = _time_minutes(end)
    if start_min == end_min:
        return np.ones(len(timestamps), dtype=bool)
    timestamps = timestamps.tz_localize("UTC").tz_convert(timezone)
    current = timestamps.hour.to_numpy() * 60 + timestamps.minute.to_numpy()
    if start_min < end_min:
        return (current >= start_min) & (current < end_min)
    return (current >= start_min) | (current < end_min)


def _curve_assessment(
    hs: np.ndarray,
    tp: np.ndarray,
    curve_name: str,
    bins: list[HsTpBin],
) -> dict[str, np.ndarray | str | bool]:
    """Evaluate a combined Hs-Tp operating envelope.

    The primary failure is attributed to Hs when Tp is inside a valid curve bin
    and Hs exceeds the allowable value. It is attributed to Tp when Tp is
    outside the curve domain (or falls in a gap between configured bins).
    """
    n = len(hs)
    no_failure = np.zeros(n, dtype=bool)
    no_limit = np.full(n, np.nan, dtype=float)
    if not curve_name or str(curve_name).strip().lower() in {"", "none", "nan"}:
        return {
            "active": False,
            "name": "",
            "hs_failure": no_failure,
            "tp_failure": no_failure.copy(),
            "hs_limit": no_limit,
            "tp_min": np.nan,
            "tp_max": np.nan,
        }

    rows = sorted(
        (item for item in bins if item.curve == curve_name),
        key=lambda item: (item.tp_from, item.tp_to),
    )
    if not rows:
        return {
            "active": True,
            "name": str(curve_name),
            "hs_failure": no_failure,
            "tp_failure": np.ones(n, dtype=bool),
            "hs_limit": no_limit,
            "tp_min": np.nan,
            "tp_max": np.nan,
        }

    hs_limit = np.full(n, np.nan, dtype=float)
    matched = np.zeros(n, dtype=bool)
    for row in rows:
        mask = (
            (tp >= float(row.tp_from))
            & (tp <= float(row.tp_to))
            & ~matched
        )
        hs_limit[mask] = float(row.hs_max)
        matched |= mask

    tp_failure = ~matched
    hs_failure = matched & (hs > hs_limit)
    return {
        "active": True,
        "name": str(curve_name),
        "hs_failure": hs_failure,
        "tp_failure": tp_failure,
        "hs_limit": hs_limit,
        "tp_min": float(min(row.tp_from for row in rows)),
        "tp_max": float(max(row.tp_to for row in rows)),
    }


def _next_bad_indexes(good: np.ndarray) -> np.ndarray:
    n = len(good)
    output = np.empty(n, dtype=np.int32)
    next_bad = n
    for index in range(n - 1, -1, -1):
        if not good[index]:
            next_bad = index
        output[index] = next_bad
    return output


def _limit_failure(values: np.ndarray, limit: float) -> np.ndarray:
    return np.zeros(len(values), dtype=bool) if float(limit) <= 0 else values > float(limit)


def _effective_hs_limit(standalone_limit: float, curve_limit: np.ndarray) -> np.ndarray:
    output = curve_limit.copy()
    if float(standalone_limit) > 0:
        standalone = np.full(len(curve_limit), float(standalone_limit), dtype=float)
        output = np.where(np.isnan(output), standalone, np.minimum(output, standalone))
    return output


def _build_criteria(
    *,
    location_id: str,
    timestamps: pd.DatetimeIndex,
    wind10: np.ndarray,
    wind100: np.ndarray,
    hs: np.ndarray,
    tp: np.ndarray,
    current: np.ndarray,
    wind10_limit: float,
    wind100_limit: float,
    hs_limit: float,
    tp_limit: float,
    current_limit: float,
    time_failure: np.ndarray,
    curve: dict[str, np.ndarray | str | bool],
) -> dict[str, object]:
    wind10_failure = _limit_failure(wind10, wind10_limit)
    wind100_failure = _limit_failure(wind100, wind100_limit)
    hs_direct = _limit_failure(hs, hs_limit)
    tp_direct = _limit_failure(tp, tp_limit)
    current_failure = _limit_failure(current, current_limit)
    hs_curve = np.asarray(curve["hs_failure"], dtype=bool)
    tp_curve = np.asarray(curve["tp_failure"], dtype=bool)

    factor_arrays = {
        "Wind 10 m": wind10_failure,
        "Wind 100 m": wind100_failure,
        "Hs": hs_direct | hs_curve,
        "Tp": tp_direct | tp_curve,
        "Current speed": current_failure,
        "Daylight / allowed time": np.asarray(time_failure, dtype=bool),
    }
    bad = np.logical_or.reduce(list(factor_arrays.values()))
    good = ~bad
    return {
        "location_id": location_id,
        "factors": factor_arrays,
        "good": good,
        "next_bad": _next_bad_indexes(good),
        "source_flags": {
            "Hs standalone": hs_direct,
            "Hs curve": hs_curve,
            "Tp standalone": tp_direct,
            "Tp curve": tp_curve,
        },
        "actuals": {
            "Wind 10 m": wind10,
            "Wind 100 m": wind100,
            "Hs": hs,
            "Tp": tp,
            "Current speed": current,
        },
        "limits": {
            "Wind 10 m": float(wind10_limit) if float(wind10_limit) > 0 else np.nan,
            "Wind 100 m": float(wind100_limit) if float(wind100_limit) > 0 else np.nan,
            "Hs": _effective_hs_limit(hs_limit, np.asarray(curve["hs_limit"], dtype=float)),
            "Tp": float(tp_limit) if float(tp_limit) > 0 else np.nan,
            "Current speed": float(current_limit) if float(current_limit) > 0 else np.nan,
            "Tp curve minimum": curve["tp_min"],
            "Tp curve maximum": curve["tp_max"],
            "Allowed time": "Configured activity time window",
        },
        "curve_name": str(curve["name"] or ""),
        "timestamps": timestamps,
    }


def _failure_details(criteria: dict[str, object], index: int) -> dict[str, object]:
    factors_map = criteria["factors"]
    factors = [name for name in FACTOR_NAMES if bool(factors_map[name][index])]
    main = _main_factor(factors)
    sources = criteria["source_flags"]

    bases: list[str] = []
    for factor in factors:
        if factor == "Hs":
            standalone = bool(sources["Hs standalone"][index])
            curve = bool(sources["Hs curve"][index])
            bases.append(
                "Standalone limit + Hs-Tp curve" if standalone and curve
                else "Hs-Tp curve" if curve
                else "Standalone limit"
            )
        elif factor == "Tp":
            standalone = bool(sources["Tp standalone"][index])
            curve = bool(sources["Tp curve"][index])
            bases.append(
                "Standalone limit + Hs-Tp curve range" if standalone and curve
                else "Hs-Tp curve range" if curve
                else "Standalone limit"
            )
        elif factor == "Daylight / allowed time":
            bases.append("Allowed activity time window")
        else:
            bases.append("Standalone limit")
    bases = list(dict.fromkeys(bases))
    assessment_basis = bases[0] if len(bases) == 1 else "Multiple assessment bases" if bases else ""

    actual_text = ""
    limit_text = ""
    if len(factors) == 1:
        factor = factors[0]
        actuals = criteria["actuals"]
        limits = criteria["limits"]
        if factor in actuals:
            actual = float(actuals[factor][index])
            actual_text = f"{actual:.3f}"
        if factor == "Hs":
            limit = float(limits["Hs"][index])
            limit_text = f"{limit:.3f}" if np.isfinite(limit) else ""
        elif factor == "Tp" and bool(sources["Tp curve"][index]) and not bool(sources["Tp standalone"][index]):
            low = limits["Tp curve minimum"]
            high = limits["Tp curve maximum"]
            if np.isfinite(float(low)) and np.isfinite(float(high)):
                limit_text = f"{float(low):.3f} to {float(high):.3f}"
            else:
                limit_text = "Configured Hs-Tp curve range"
        elif factor in limits and not isinstance(limits[factor], np.ndarray):
            limit = limits[factor]
            if isinstance(limit, (int, float, np.floating)) and np.isfinite(float(limit)):
                limit_text = f"{float(limit):.3f}"
            elif limit:
                limit_text = str(limit)
        elif factor == "Daylight / allowed time":
            limit_text = str(limits["Allowed time"])
    elif factors:
        actual_parts = []
        for factor in factors:
            if factor in criteria["actuals"]:
                actual_parts.append(f"{factor}={float(criteria['actuals'][factor][index]):.3f}")
        actual_text = ", ".join(actual_parts)
        limit_text = "Multiple limits"

    return {
        "factors": factors,
        "main_factor": main,
        "assessment_basis": assessment_basis,
        "blocking_actual": actual_text,
        "blocking_limit": limit_text,
    }


def _weather_dict(
    weather: pd.DataFrame | dict[str, pd.DataFrame], sequence: list[SequenceItem]
) -> dict[str, pd.DataFrame]:
    if isinstance(weather, pd.DataFrame):
        locations = {item.location_id for item in sequence} or {"OFFSHORE"}
        return {location_id: weather for location_id in locations}
    return weather


def _criteria_cache(
    weather_by_location: dict[str, pd.DataFrame],
    sequence: list[SequenceItem],
    bins: list[HsTpBin],
) -> dict[tuple[str, int], dict[str, object]]:
    for frame in weather_by_location.values():
        validate_weather_frame(frame)
    for item in sequence:
        values = [item.duration_hours, item.weather_window_hours, item.wind10_limit,
                  item.wind100_limit, item.hs_limit, item.tp_limit, item.current_limit]
        if any(not finite_number(value) or value < 0 for value in values) or min(values[:2]) <= 0:
            raise ValueError(f"Activity {item.activity_id} contains invalid engineering values.")
    first = next(iter(weather_by_location.values()))
    timestamps = pd.DatetimeIndex(first["timestamp"])
    if any(not pd.DatetimeIndex(frame["timestamp"]).equals(timestamps) for frame in weather_by_location.values()):
        raise ValueError("Location weather datasets are not aligned to the same timestamp index.")
    unique: dict[tuple[str, int], SequenceItem] = {}
    for item in sequence:
        unique[(item.location_id, item.activity_id)] = item

    cache: dict[tuple[str, int], dict[str, object]] = {}
    for key, item in unique.items():
        location_id, _ = key
        if location_id not in weather_by_location:
            raise ValueError(f"Weather data is not loaded for activity location '{location_id}'.")
        frame = weather_by_location[location_id]
        if len(frame) != len(first) or not pd.DatetimeIndex(frame["timestamp"]).equals(timestamps):
            raise ValueError("Location weather datasets are not aligned to the same timestamp index.")
        wind10 = frame["wind10"].to_numpy(float)
        wind100 = frame["wind100"].to_numpy(float)
        hs = frame["hs"].to_numpy(float)
        tp = frame["tp"].to_numpy(float)
        current = frame["current"].to_numpy(float)
        curve = _curve_assessment(hs, tp, item.hstp_curve, bins)
        cache[key] = _build_criteria(
            location_id=location_id,
            timestamps=timestamps,
            wind10=wind10,
            wind100=wind100,
            hs=hs,
            tp=tp,
            current=current,
            wind10_limit=item.wind10_limit,
            wind100_limit=item.wind100_limit,
            hs_limit=item.hs_limit,
            tp_limit=item.tp_limit,
            current_limit=item.current_limit,
            time_failure=~_time_allowed(timestamps, item.time_start, item.time_end, item.timezone),
            curve=curve,
        )
    return cache


def _start_index(timestamps: pd.DatetimeIndex, start: datetime) -> int | None:
    index = int(timestamps.searchsorted(pd.Timestamp(start), side="left"))
    return index if index < len(timestamps) else None


def _steps(value_hours: float, step_hours: float) -> int:
    return int(math.ceil(float(value_hours) / step_hours - 1e-12))


def _group_members(sequence: list[SequenceItem], start_index: int) -> list[SequenceItem]:
    first = sequence[start_index]
    if not first.safe_to_safe_group or first.group_role not in {"Start", "Single"}:
        return []
    members: list[SequenceItem] = []
    for item in sequence[start_index:]:
        if (
            item.safe_to_safe_group != first.safe_to_safe_group
            or item.cycle != first.cycle
            or item.position != first.position
        ):
            break
        members.append(item)
        if item.group_role == "End":
            break
    return members


def _lowest_positive(values: list[tuple[float, SequenceItem]]) -> tuple[float | None, SequenceItem | None]:
    valid = [(float(value), item) for value, item in values if float(value) > 0]
    return min(valid, key=lambda pair: pair[0]) if valid else (None, None)


def _combine_curve_assessments(
    hs: np.ndarray,
    tp: np.ndarray,
    members: list[SequenceItem],
    bins: list[HsTpBin],
) -> dict[str, np.ndarray | str | bool]:
    n = len(hs)
    hs_failure = np.zeros(n, dtype=bool)
    tp_failure = np.zeros(n, dtype=bool)
    hs_limit = np.full(n, np.nan, dtype=float)
    ranges: list[tuple[float, float]] = []
    names: list[str] = []
    active = False
    for member in members:
        assessment = _curve_assessment(hs, tp, member.hstp_curve, bins)
        if not assessment["active"]:
            continue
        active = True
        names.append(str(assessment["name"]))
        hs_failure |= np.asarray(assessment["hs_failure"], dtype=bool)
        tp_failure |= np.asarray(assessment["tp_failure"], dtype=bool)
        member_limit = np.asarray(assessment["hs_limit"], dtype=float)
        hs_limit = np.where(
            np.isnan(hs_limit),
            member_limit,
            np.where(np.isnan(member_limit), hs_limit, np.minimum(hs_limit, member_limit)),
        )
        low = float(assessment["tp_min"])
        high = float(assessment["tp_max"])
        if np.isfinite(low) and np.isfinite(high):
            ranges.append((low, high))
    return {
        "active": active,
        "name": ", ".join(dict.fromkeys(names)),
        "hs_failure": hs_failure,
        "tp_failure": tp_failure,
        "hs_limit": hs_limit,
        "tp_min": max((low for low, _ in ranges), default=np.nan),
        "tp_max": min((high for _, high in ranges), default=np.nan),
    }


def _group_criteria_cache(
    weather_by_location: dict[str, pd.DataFrame],
    sequence: list[SequenceItem],
    bins: list[HsTpBin],
    timestamps: pd.DatetimeIndex,
) -> dict[str, dict[str, object]]:
    """Build consolidated MOST_STRINGENT criteria once per safe-to-safe group."""
    output: dict[str, dict[str, object]] = {}
    index = 0
    while index < len(sequence):
        item = sequence[index]
        if not item.safe_to_safe_group or item.group_role != "Start":
            index += 1
            continue
        members = _group_members(sequence, index)
        index += max(1, len(members))
        if not members or str(item.group_method or "MOST_STRINGENT").upper() != "MOST_STRINGENT":
            continue
        group_id = item.safe_to_safe_group
        if group_id in output:
            continue

        location_id = item.group_assessment_location.strip()
        if not location_id:
            locations = {member.location_id for member in members}
            location_id = next(iter(locations)) if len(locations) == 1 else ""
        if not location_id or location_id not in weather_by_location:
            raise ValueError(f"Group '{group_id}' assessment location is not configured or weather is missing.")

        frame = weather_by_location[location_id]
        wind10 = frame["wind10"].to_numpy(float)
        wind100 = frame["wind100"].to_numpy(float)
        hs = frame["hs"].to_numpy(float)
        tp = frame["tp"].to_numpy(float)
        current = frame["current"].to_numpy(float)

        wind10_limit, wind10_owner = _lowest_positive([(m.wind10_limit, m) for m in members])
        wind100_limit, wind100_owner = _lowest_positive([(m.wind100_limit, m) for m in members])
        hs_limit, hs_owner = _lowest_positive([(m.hs_limit, m) for m in members])
        tp_limit, tp_owner = _lowest_positive([(m.tp_limit, m) for m in members])
        current_limit, current_owner = _lowest_positive([(m.current_limit, m) for m in members])
        curve = _combine_curve_assessments(hs, tp, members, bins)
        criteria = _build_criteria(
            location_id=location_id,
            timestamps=timestamps,
            wind10=wind10,
            wind100=wind100,
            hs=hs,
            tp=tp,
            current=current,
            wind10_limit=wind10_limit or 0.0,
            wind100_limit=wind100_limit or 0.0,
            hs_limit=hs_limit or 0.0,
            tp_limit=tp_limit or 0.0,
            current_limit=current_limit or 0.0,
            time_failure=np.logical_or.reduce([
                ~_time_allowed(timestamps, member.time_start, member.time_end, member.timezone)
                for member in members
            ]),
            curve=curve,
        )
        criteria["owners"] = {
            "Wind 10 m": wind10_owner,
            "Wind 100 m": wind100_owner,
            "Hs": hs_owner,
            "Tp": tp_owner,
            "Current speed": current_owner,
            "Daylight / allowed time": next(
                (member for member in members if member.time_start != member.time_end),
                members[0],
            ),
        }
        criteria["members"] = members
        output[group_id] = criteria
    return output


def _check_group_window(
    start_index: int,
    members: list[SequenceItem],
    cache: dict[tuple[str, int], dict[str, object]],
    group_cache: dict[str, dict[str, object]],
    timestamps: pd.DatetimeIndex,
    step_hours: float,
) -> dict[str, object]:
    """Check a complete safe-to-safe group using its configured method."""
    if not members:
        return {
            "ok": False,
            "data_limited": False,
            "blocker": None,
            "details": {"factors": ["Invalid safe-to-safe group"], "main_factor": "Invalid safe-to-safe group", "assessment_basis": "", "blocking_actual": "", "blocking_limit": ""},
            "blocker_index": start_index,
            "location_id": "",
        }

    method = str(members[0].group_method or "MOST_STRINGENT").upper()
    n = len(timestamps)
    if method == "TIME_PHASED":
        offset_steps = 0
        for member in members:
            duration_steps = _steps(member.duration_hours, step_hours)
            window_steps = max(1, _steps(member.weather_window_hours, step_hours))
            required_steps = max(duration_steps, window_steps)
            member_start = start_index + offset_steps
            member_end = member_start + required_steps
            if member_end > n:
                return {"ok": False, "data_limited": True, "blocker": member, "details": {}, "blocker_index": None, "location_id": member.location_id}
            criteria = cache[(member.location_id, member.activity_id)]
            bad_index = int(criteria["next_bad"][member_start])
            if bad_index < member_end:
                return {
                    "ok": False,
                    "data_limited": False,
                    "blocker": member,
                    "details": _failure_details(criteria, bad_index),
                    "blocker_index": bad_index,
                    "location_id": member.location_id,
                }
            offset_steps += duration_steps
        return {"ok": True, "data_limited": False, "blocker": None, "details": {}, "blocker_index": None, "location_id": ""}

    group_id = members[0].safe_to_safe_group
    consolidated = group_cache.get(group_id, {})
    if consolidated.get("error"):
        return {
            "ok": False,
            "data_limited": False,
            "blocker": members[0],
            "details": {"factors": [str(consolidated["error"])], "main_factor": str(consolidated["error"]), "assessment_basis": "Configuration", "blocking_actual": "", "blocking_limit": ""},
            "blocker_index": start_index,
            "location_id": members[0].group_assessment_location,
        }
    if not consolidated:
        return {
            "ok": False,
            "data_limited": False,
            "blocker": members[0],
            "details": {"factors": ["Safe-to-safe group criteria are unavailable"], "main_factor": "Safe-to-safe group criteria are unavailable", "assessment_basis": "Configuration", "blocking_actual": "", "blocking_limit": ""},
            "blocker_index": start_index,
            "location_id": members[0].group_assessment_location,
        }

    total_duration_steps = sum(_steps(member.duration_hours, step_hours) for member in members)
    largest_window_steps = max([1] + [_steps(member.weather_window_hours, step_hours) for member in members])
    required_steps = max(total_duration_steps, largest_window_steps)
    end_index = start_index + required_steps
    if end_index > n:
        return {"ok": False, "data_limited": True, "blocker": members[0], "details": {}, "blocker_index": None, "location_id": str(consolidated["location_id"])}

    bad_index = int(consolidated["next_bad"][start_index])
    if bad_index >= end_index:
        return {"ok": True, "data_limited": False, "blocker": None, "details": {}, "blocker_index": None, "location_id": str(consolidated["location_id"])}

    details = _failure_details(consolidated, bad_index)
    owners = consolidated.get("owners", {})
    blocker = next((owners.get(name) for name in details["factors"] if owners.get(name) is not None), members[0])
    return {
        "ok": False,
        "data_limited": False,
        "blocker": blocker,
        "details": details,
        "blocker_index": bad_index,
        "location_id": str(consolidated["location_id"]),
    }


def simulate_year(
    weather: pd.DataFrame | dict[str, pd.DataFrame],
    sequence: list[SequenceItem],
    bins: list[HsTpBin],
    settings: CampaignSettings,
    start_year: int,
    include_trace: bool = False,
    cache: dict[tuple[str, int], dict[str, object]] | None = None,
    group_cache: dict[str, dict[str, object]] | None = None,
) -> SimulationResult:
    weather_by_location = _weather_dict(weather, sequence)
    first_weather = next(iter(weather_by_location.values()))
    step = settings.timestep_hours
    timestep_minutes(step)
    timestamps = pd.DatetimeIndex(first_weather["timestamp"])
    if len(timestamps) > 1 and not np.all((timestamps[1:] - timestamps[:-1]) == pd.Timedelta(hours=step)):
        raise ValueError("Weather grid does not match the simulation timestep; prepare and align weather first.")
    try:
        campaign_start = datetime(start_year, settings.start_month, settings.start_day)
    except ValueError as exc:
        return SimulationResult(start_year, False, str(exc), datetime(start_year, 1, 1), None, None, 0, 0)
    index = _start_index(timestamps, campaign_start)
    if index is None:
        return SimulationResult(start_year, False, "Campaign start is after the weather record.", campaign_start, None, None, 0, 0)
    if timestamps[index] != pd.Timestamp(campaign_start):
        return SimulationResult(start_year, False, "Campaign start timestamp is not available in the common weather record.", campaign_start, None, None, 0, 0)

    cache = cache or _criteria_cache(weather_by_location, sequence, bins)
    group_cache = group_cache or _group_criteria_cache(weather_by_location, sequence, bins, timestamps)
    exact_p0_hours = float(sum(item.duration_hours for item in sequence))
    work_hours = 0.0
    downtime_hours = 0.0
    downtime_by_cause: defaultdict[str, float] = defaultdict(float)
    downtime_by_main_factor: defaultdict[str, float] = defaultdict(float)
    downtime_by_type_factor: defaultdict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    downtime_by_activity: defaultdict[str, float] = defaultdict(float)
    downtime_by_activity_id: defaultdict[int, float] = defaultdict(float)
    working_by_location: defaultdict[str, float] = defaultdict(float)
    downtime_by_location: defaultdict[str, float] = defaultdict(float)
    downtime_by_location_cause: defaultdict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    downtime_by_group: defaultdict[str, float] = defaultdict(float)
    monthly: defaultdict[tuple[int, int], dict[str, float]] = defaultdict(
        lambda: {"working_hours": 0.0, "downtime_hours": 0.0, "positions_completed": 0.0}
    )
    planning_monthly: defaultdict[tuple[int, int], dict[str, float]] = defaultdict(
        lambda: {"working_hours": 0.0, "downtime_hours": 0.0, "positions_completed": 0.0}
    )
    planning_campaign_start = datetime(settings.nominal_year, settings.start_month, settings.start_day)
    completion_dates: dict[int, datetime] = {}
    completion_elapsed: dict[int, float] = {}
    trace_rows: list[dict] = []
    weather_arrays = {
        location_id: frame[["wind10", "wind100", "hs", "tp", "current"]].to_numpy(float)
        for location_id, frame in weather_by_location.items()
    }
    remaining_steps = 0
    data_coverage_limited = False

    def record_step(
        step_index: int,
        item: SequenceItem,
        status: str,
        *,
        downtime_type: str = "",
        details: dict[str, object] | None = None,
        group_id: str = "",
        blocker: SequenceItem | None = None,
        blocker_index: int | None = None,
        blocker_location: str = "",
    ) -> None:
        nonlocal work_hours, downtime_hours
        ts = timestamps[step_index]
        key = (int(ts.year), int(ts.month))
        elapsed_hours = (ts.to_pydatetime() - campaign_start).total_seconds() / 3600.0
        planning_ts = planning_campaign_start + timedelta(hours=elapsed_hours)
        planning_key = (planning_ts.year, planning_ts.month)
        details = details or {"factors": [], "main_factor": "", "assessment_basis": "", "blocking_actual": "", "blocking_limit": ""}
        main_factor = str(details.get("main_factor", ""))
        display_cause = _display_cause(downtime_type, main_factor) if status == "Downtime" else ""

        if status == "Working":
            location_id = item.location_id
            work_hours += step
            working_by_location[location_id] += step
            monthly[key]["working_hours"] += step
            planning_monthly[planning_key]["working_hours"] += step
        else:
            location_id = blocker_location or (
                item.group_assessment_location
                if group_id and item.group_method == "MOST_STRINGENT" and item.group_assessment_location
                else item.location_id
            )
            downtime_hours += step
            downtime_by_location[location_id] += step
            monthly[key]["downtime_hours"] += step
            planning_monthly[planning_key]["downtime_hours"] += step
            downtime_by_activity[item.description] += step
            downtime_by_activity_id[item.activity_id] += step
            downtime_by_cause[display_cause] += step
            downtime_by_main_factor[main_factor] += step
            downtime_by_type_factor[downtime_type][main_factor] += step
            downtime_by_location_cause[location_id][display_cause] += step
            if group_id:
                downtime_by_group[group_id] += step

        if include_trace:
            location_id = item.location_id if status == "Working" else (
                blocker_location or (
                    item.group_assessment_location
                    if group_id and item.group_method == "MOST_STRINGENT" and item.group_assessment_location
                    else item.location_id
                )
            )
            values = weather_arrays[location_id][step_index]
            blocking_timestamp = timestamps[blocker_index] if blocker_index is not None and 0 <= blocker_index < len(timestamps) else None
            values_location = blocker_location or (blocker.location_id if blocker is not None else location_id)
            blocker_values = (
                weather_arrays[values_location][blocker_index]
                if blocker_index is not None and 0 <= blocker_index < len(timestamps) and values_location in weather_arrays
                else [np.nan, np.nan, np.nan, np.nan, np.nan]
            )
            offset = (
                (timestamps[blocker_index] - ts).total_seconds() / 3600.0
                if blocker_index is not None and 0 <= blocker_index < len(timestamps)
                else np.nan
            )
            row = {
                "Timestamp": ts,
                "End timestamp": ts + pd.Timedelta(hours=step),
                "Duration [h]": step,
                "Location": location_id,
                "Wind 10 m": values[0],
                "Wind 100 m": values[1],
                "Hs": values[2],
                "Tp": values[3],
                "Current speed": values[4],
                "Status": status,
                "Downtime type": downtime_type,
                "Main factor": main_factor,
                "Downtime category": display_cause,
                "Assessment basis": str(details.get("assessment_basis", "")),
                "Blocking criteria": ", ".join(str(value) for value in details.get("factors", [])),
                "Blocking actual": str(details.get("blocking_actual", "")),
                "Blocking limit": str(details.get("blocking_limit", "")),
                "Cycle": item.cycle,
                "Position": item.position,
                "Activity ID": item.activity_id,
                "Activity": item.description,
                "Remaining activity [h]": remaining_steps * step,
                "Safe-to-safe group": group_id or item.safe_to_safe_group,
                "Group role": item.group_role,
                "Group method": item.group_method if group_id else "",
                "Group assessment location": item.group_assessment_location if group_id else "",
                "Window check": "Safe-to-safe group" if group_id else "Single activity",
                "Blocking activity ID": blocker.activity_id if blocker is not None else None,
                "Blocking activity": blocker.description if blocker is not None else "",
                "Blocking location": values_location if blocker_index is not None else "",
                "Blocking timestamp": blocking_timestamp,
                "Blocking forecast offset [h]": offset,
                "Blocking Wind 10 m": blocker_values[0],
                "Blocking Wind 100 m": blocker_values[1],
                "Blocking Hs": blocker_values[2],
                "Blocking Tp": blocker_values[3],
                "Blocking Current speed": blocker_values[4],
            }
            identity_columns = [
                "Location", "Status", "Downtime type", "Main factor", "Downtime category",
                "Assessment basis", "Blocking criteria", "Blocking limit",
                "Cycle", "Position", "Activity ID", "Safe-to-safe group", "Group role",
                "Group method", "Group assessment location", "Window check",
                "Blocking activity ID", "Blocking location",
            ]
            # A window-related interval must retain the exact future blocker. Direct
            # exceedances can be compressed while preserving interval maxima below.
            if downtime_type == WINDOW_DOWNTIME:
                identity_columns += ["Blocking timestamp", "Blocking actual"]
            if trace_rows and trace_rows[-1]["End timestamp"] == row["Timestamp"] and all(
                trace_rows[-1].get(column) == row.get(column) for column in identity_columns
            ):
                previous = trace_rows[-1]
                previous["End timestamp"] = row["End timestamp"]
                previous["Duration [h]"] += step
                for column in [
                    "Wind 10 m", "Wind 100 m", "Hs", "Tp", "Current speed",
                    "Blocking Wind 10 m", "Blocking Wind 100 m", "Blocking Hs",
                    "Blocking Tp", "Blocking Current speed",
                ]:
                    current_value = row.get(column)
                    if pd.notna(current_value):
                        previous[column] = max(float(previous.get(column, current_value)), float(current_value))
                if downtime_type == DIRECT_DOWNTIME:
                    factor_columns = {
                        "Wind 10 m": "Blocking Wind 10 m",
                        "Wind 100 m": "Blocking Wind 100 m",
                        "Hs": "Blocking Hs",
                        "Tp": "Blocking Tp",
                        "Current speed": "Blocking Current speed",
                    }
                    factors = [str(value) for value in details.get("factors", [])]
                    actual_parts = []
                    for factor in factors:
                        column = factor_columns.get(factor)
                        if column and pd.notna(previous.get(column)):
                            value = float(previous[column])
                            actual_parts.append(f"{factor}={value:.3f}" if len(factors) > 1 else f"{value:.3f}")
                    if actual_parts:
                        previous["Blocking actual"] = ", ".join(actual_parts)
            else:
                trace_rows.append(row)

    def complete_item(item: SequenceItem, completion_index: int) -> None:
        if item.milestone and item.position is not None:
            completion_time = (timestamps[completion_index - 1] + pd.Timedelta(hours=step)).to_pydatetime()
            completion_dates[item.position] = completion_time
            completion_elapsed[item.position] = (completion_time - campaign_start).total_seconds() / 3600.0
            monthly[(completion_time.year, completion_time.month)]["positions_completed"] += 1
            planning_completion = planning_campaign_start + timedelta(hours=completion_elapsed[item.position])
            planning_monthly[(planning_completion.year, planning_completion.month)]["positions_completed"] += 1

    activity_index = 0
    n = len(first_weather)
    while activity_index < len(sequence):
        item = sequence[activity_index]
        if index >= n:
            data_coverage_limited = True
            break

        if item.safe_to_safe_group and item.group_role == "Start":
            remaining_steps = _steps(item.duration_hours, step)
            members = _group_members(sequence, activity_index)
            check = _check_group_window(index, members, cache, group_cache, timestamps, step)
            if bool(check["data_limited"]):
                data_coverage_limited = True
                break
            if not bool(check["ok"]):
                blocker_index = check["blocker_index"]
                downtime_type = (
                    WINDOW_DOWNTIME
                    if blocker_index is not None and int(blocker_index) > index
                    else DIRECT_DOWNTIME
                )
                record_step(
                    index,
                    item,
                    "Downtime",
                    downtime_type=downtime_type,
                    details=check["details"],
                    group_id=item.safe_to_safe_group,
                    blocker=check["blocker"],
                    blocker_index=blocker_index,
                    blocker_location=str(check.get("location_id", "")),
                )
                index += 1
                continue

            for member in members:
                member_steps = _steps(member.duration_hours, step)
                remaining_steps = member_steps
                for step_index in range(index, index + member_steps):
                    record_step(step_index, member, "Working", group_id=member.safe_to_safe_group)
                    remaining_steps -= 1
                index += member_steps
                complete_item(member, index)
            remaining_steps = 0
            activity_index += len(members)
            continue

        if remaining_steps <= 0:
            remaining_steps = _steps(item.duration_hours, step)
        window_steps = max(1, _steps(item.weather_window_hours, step))
        criteria = cache[(item.location_id, item.activity_id)]
        good = criteria["good"]
        if not bool(good[index]):
            details = _failure_details(criteria, index)
            record_step(index, item, "Downtime", downtime_type=DIRECT_DOWNTIME, details=details, blocker=item, blocker_index=index)
            index += 1
            continue

        next_bad = int(criteria["next_bad"][index])
        run_length = next_bad - index if next_bad < n else n - index
        required = max(remaining_steps, window_steps)
        if run_length >= required:
            work_count = remaining_steps
            for step_index in range(index, index + work_count):
                record_step(step_index, item, "Working")
                remaining_steps -= 1
            index += work_count
            remaining_steps = 0
            complete_item(item, index)
            activity_index += 1
        elif run_length >= window_steps:
            work_count = min(run_length, remaining_steps)
            for step_index in range(index, index + work_count):
                record_step(step_index, item, "Working")
                remaining_steps -= 1
            index += work_count
        else:
            if next_bad >= n:
                data_coverage_limited = True
                break
            details = _failure_details(criteria, next_bad)
            for step_index in range(index, index + run_length):
                record_step(
                    step_index,
                    item,
                    "Downtime",
                    downtime_type=WINDOW_DOWNTIME,
                    details=details,
                    blocker=item,
                    blocker_index=next_bad,
                )
            index += run_length

    successful = activity_index >= len(sequence)
    if successful:
        finish = timestamps[index - 1] + pd.Timedelta(hours=step) if index > 0 else pd.Timestamp(campaign_start)
        duration = (finish.to_pydatetime() - campaign_start).total_seconds() / 3600.0
        message = "Completed"
    else:
        finish = None
        duration = None
        message = DATA_LIMITATION if data_coverage_limited else "Campaign did not complete."

    monthly_records = []
    for (year, month), values in sorted(monthly.items()):
        active = values["working_hours"] + values["downtime_hours"]
        monthly_records.append({
            "Calendar year": year,
            "Month": month,
            "Month name": pd.Timestamp(year=2000, month=month, day=1).month_name(),
            **values,
            "downtime_pct": values["downtime_hours"] / active if active else np.nan,
            "workable_hours_per_day": 24.0 * values["working_hours"] / active if active else np.nan,
        })

    planning_monthly_records = []
    for (year, month), values in sorted(planning_monthly.items()):
        active = values["working_hours"] + values["downtime_hours"]
        planning_monthly_records.append({
            "Calendar year": year,
            "Month": month,
            "Month name": pd.Timestamp(year=2000, month=month, day=1).month_name(),
            **values,
            "downtime_pct": values["downtime_hours"] / active if active else np.nan,
            "workable_hours_per_day": 24.0 * values["working_hours"] / active if active else np.nan,
        })

    trace = pd.DataFrame(trace_rows) if include_trace else None
    timestep_adjustment = max(0.0, work_hours - exact_p0_hours) if successful else 0.0
    return SimulationResult(
        start_year=start_year,
        successful=successful,
        message=message,
        campaign_start=campaign_start,
        campaign_finish=finish.to_pydatetime() if finish is not None else None,
        duration_hours=duration,
        working_hours=work_hours,
        downtime_hours=downtime_hours,
        position_completion_dates=completion_dates,
        position_completion_elapsed_hours=completion_elapsed,
        downtime_by_cause=dict(downtime_by_cause),
        downtime_by_main_factor=dict(downtime_by_main_factor),
        downtime_by_type_factor={key: dict(value) for key, value in downtime_by_type_factor.items()},
        downtime_by_activity=dict(downtime_by_activity),
        working_by_location=dict(working_by_location),
        downtime_by_location=dict(downtime_by_location),
        downtime_by_location_cause={key: dict(value) for key, value in downtime_by_location_cause.items()},
        downtime_by_group=dict(downtime_by_group),
        monthly_records=monthly_records,
        planning_monthly_records=planning_monthly_records,
        trace=trace,
        exact_p0_hours=exact_p0_hours,
        timestep_adjustment_hours=timestep_adjustment,
        data_coverage_limited=data_coverage_limited,
        downtime_by_activity_id=dict(downtime_by_activity_id),
        activity_descriptions={item.activity_id: item.description for item in sequence},
    )


def available_start_years(
    weather: pd.DataFrame | dict[str, pd.DataFrame], settings: CampaignSettings
) -> list[int]:
    first = weather if isinstance(weather, pd.DataFrame) else next(iter(weather.values()))
    timestamps = pd.DatetimeIndex(first["timestamp"])
    years = sorted(set(int(year) for year in timestamps.year))
    timestamp_set = set(timestamps)
    candidates: list[int] = []
    for year in years:
        try:
            start = pd.Timestamp(datetime(year, settings.start_month, settings.start_day))
        except ValueError:
            continue
        if start in timestamp_set:
            candidates.append(year)
    if settings.hindcast_start_year is not None:
        candidates = [year for year in candidates if year >= settings.hindcast_start_year]
    if settings.hindcast_end_year is not None:
        candidates = [year for year in candidates if year <= settings.hindcast_end_year]
    return candidates


def run_hindcast(
    weather: pd.DataFrame | dict[str, pd.DataFrame],
    sequence: list[SequenceItem],
    bins: list[HsTpBin],
    settings: CampaignSettings,
    detailed_year: int | None = None,
    progress: Callable[[int, int, int], None] | None = None,
) -> list[SimulationResult]:
    weather_by_location = _weather_dict(weather, sequence)
    years = available_start_years(weather_by_location, settings)
    if not years:
        raise ValueError("No common hindcast year contains the requested campaign start month/day.")
    cache = _criteria_cache(weather_by_location, sequence, bins)
    first = next(iter(weather_by_location.values()))
    group_cache = _group_criteria_cache(
        weather_by_location, sequence, bins, pd.DatetimeIndex(first["timestamp"])
    )
    results: list[SimulationResult] = []
    for count, year in enumerate(years, start=1):
        result = simulate_year(
            weather=weather_by_location,
            sequence=sequence,
            bins=bins,
            settings=settings,
            start_year=year,
            include_trace=(year == detailed_year),
            cache=cache,
            group_cache=group_cache,
        )
        results.append(result)
        if progress:
            progress(count, len(years), year)
    return results
