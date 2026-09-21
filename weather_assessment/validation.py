from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import Activity, CampaignSettings, HsTpBin, Location, SafeToSafeGroup
from .policies import GROUP_METHODS, finite_number, timestep_minutes


def required_weather_locations(activities, groups=None) -> set[str]:
    """All activity locations plus independent MOST_STRINGENT assessment sites."""
    used_groups = {a.safe_to_safe_group for a in activities if a.safe_to_safe_group}
    return {a.location_id for a in activities if a.location_id} | {
        g.assessment_location for g in (groups or [])
        if g.group_id in used_groups and g.assessment_method == "MOST_STRINGENT" and g.assessment_location
    }


def _minutes(value: str) -> int:
    text = str(value).strip()
    parsed = datetime.strptime(text, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def validate_inputs(
    settings: CampaignSettings,
    activities: list[Activity],
    hstp_bins: list[HsTpBin],
    learning_curve: dict[int, float],
    locations: list[Location] | None = None,
    loaded_weather_locations: set[str] | None = None,
    safe_to_safe_groups: list[SafeToSafeGroup] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not finite_number(settings.total_positions) or settings.total_positions <= 0 or int(settings.total_positions) != settings.total_positions:
        errors.append("Total positions must be greater than zero.")
    if not finite_number(settings.positions_per_cycle) or settings.positions_per_cycle <= 0 or int(settings.positions_per_cycle) != settings.positions_per_cycle:
        errors.append("Positions per cycle must be greater than zero.")
    try:
        timestep_minutes(settings.timestep_hours)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        datetime(settings.nominal_year, settings.start_month, settings.start_day)
    except (ValueError, TypeError) as exc:
        errors.append(f"Campaign start date is invalid: {exc}")
    if len(settings.percentiles) != 3 or len(set(settings.percentiles)) != 3:
        errors.append("Configure exactly three distinct percentiles.")
    for percentile in settings.percentiles:
        if not finite_number(percentile) or percentile < 0 or percentile > 100:
            errors.append(f"Percentile {percentile} must be finite and within 0–100.")
    if settings.default_safe_to_safe_method not in GROUP_METHODS:
        errors.append("Invalid default safe-to-safe assessment method.")
    if settings.hindcast_start_year is not None and settings.hindcast_end_year is not None and settings.hindcast_start_year > settings.hindcast_end_year:
        errors.append("Hindcast start year must not exceed the end year.")

    if not activities:
        errors.append("At least one activity is required.")
        return errors

    ids = [a.activity_id for a in activities]
    if ids != list(range(1, len(ids) + 1)):
        errors.append("Activity IDs must be sequential and sorted: 1, 2, 3, ...")
    if any(a.activity_type not in (1, 2, 3) for a in activities):
        errors.append("Every activity type must be 1, 2, or 3.")
    milestones = [a for a in activities if a.milestone]
    if len(milestones) != 1:
        errors.append("Exactly one activity must be marked as the position-complete milestone.")
    elif milestones[0].activity_type != 2:
        errors.append("The position-complete milestone must be assigned to a Type 2 activity.")

    location_ids: set[str] | None = None
    if locations is not None:
        for location in locations:
            try:
                ZoneInfo(location.timezone)
            except (ValueError, ZoneInfoNotFoundError):
                errors.append(f"Location '{location.location_id}': invalid timezone {location.timezone!r}.")
        clean_ids = [item.location_id.strip() for item in locations if item.location_id.strip()]
        if len(clean_ids) != len(set(clean_ids)):
            errors.append("Location IDs must be unique.")
        if not clean_ids:
            errors.append("At least one work location is required.")
        location_ids = set(clean_ids)

    curves = {item.curve for item in hstp_bins}
    for activity in activities:
        if not activity.location_id.strip():
            errors.append(f"Activity {activity.activity_id}: work location is required.")
        elif location_ids is not None and activity.location_id not in location_ids:
            errors.append(f"Activity {activity.activity_id}: location '{activity.location_id}' is not defined.")
        if not finite_number(activity.duration_hours) or activity.duration_hours <= 0:
            errors.append(f"Activity {activity.activity_id}: duration must be greater than zero.")
        if not finite_number(activity.weather_window_hours) or activity.weather_window_hours <= 0:
            errors.append(f"Activity {activity.activity_id}: weather window must be greater than zero.")
        limits = [activity.wind10_limit, activity.wind100_limit, activity.hs_limit, activity.tp_limit, activity.current_limit]
        if any(not finite_number(value) or value < 0 for value in limits):
            errors.append(f"Activity {activity.activity_id}: weather limits must be finite and nonnegative.")
        try:
            start = _minutes(activity.time_start)
            end = _minutes(activity.time_end)
        except ValueError:
            errors.append(f"Activity {activity.activity_id}: time window must use HH:MM format.")
            continue
        if start != end:
            available_minutes = end - start if start < end else 1440 - start + end
            if available_minutes / 60.0 + 1e-9 < activity.weather_window_hours:
                errors.append(
                    f"Activity {activity.activity_id}: weather window is longer than the available time-of-day window."
                )
        curve = activity.hstp_curve.strip()
        if curve != "None" and curve not in curves:
            errors.append(f"Activity {activity.activity_id}: Hs–Tp curve '{curve}' does not exist.")

    # Safe-to-safe groups are commitment blocks. They must remain consecutive
    # after the base sequence is expanded, so all members use the same activity
    # type and occupy one uninterrupted block within that type.
    grouped: dict[str, list[Activity]] = {}
    for activity in activities:
        group_id = activity.safe_to_safe_group.strip()
        if group_id:
            grouped.setdefault(group_id, []).append(activity)
    ordered_by_type = {
        activity_type: [activity for activity in activities if activity.activity_type == activity_type]
        for activity_type in (1, 2, 3)
    }
    for group_id, members in sorted(grouped.items()):
        if len(members) < 2:
            errors.append(f"Safe-to-safe group '{group_id}' must contain at least two activities.")
            continue
        types = {item.activity_type for item in members}
        if len(types) != 1:
            errors.append(f"Safe-to-safe group '{group_id}' must use one activity type so its members stay consecutive.")
            continue
        activity_type = next(iter(types))
        sequence_for_type = ordered_by_type[activity_type]
        indexes = [sequence_for_type.index(item) for item in members]
        if indexes != list(range(min(indexes), max(indexes) + 1)):
            errors.append(f"Safe-to-safe group '{group_id}' activities must be consecutive within Type {activity_type}.")

    group_settings = {item.group_id: item for item in (safe_to_safe_groups or []) if item.group_id}
    if len(group_settings) != len(safe_to_safe_groups or []):
        errors.append("Safe-to-safe group IDs must be nonempty and unique.")
    for group_id, members in sorted(grouped.items()):
        config = group_settings.get(group_id)
        method = (config.assessment_method if config is not None else settings.default_safe_to_safe_method).upper()
        if method not in {"MOST_STRINGENT", "TIME_PHASED"}:
            errors.append(f"Safe-to-safe group '{group_id}' has an invalid assessment method.")
            continue
        if method == "MOST_STRINGENT":
            locations_in_group = {item.location_id for item in members}
            assessment_location = config.assessment_location.strip() if config is not None else ""
            if len(locations_in_group) > 1 and not assessment_location:
                errors.append(f"Safe-to-safe group '{group_id}' uses multiple activity locations. Select an assessment location for MOST_STRINGENT mode.")
            if assessment_location and location_ids is not None and assessment_location not in location_ids:
                errors.append(f"Safe-to-safe group '{group_id}' assessment location '{assessment_location}' is not defined.")
    unused_group_settings = sorted(set(group_settings) - set(grouped))
    if unused_group_settings:
        errors.append("Safe-to-safe group settings are defined but not used by activities: " + ", ".join(unused_group_settings))

    if loaded_weather_locations is not None:
        used = required_weather_locations(activities, safe_to_safe_groups)
        missing_weather = sorted(used - loaded_weather_locations)
        if missing_weather:
            errors.append("Weather CSV not loaded for used location(s): " + ", ".join(missing_weather))

    for name in sorted(curves):
        rows = sorted([x for x in hstp_bins if x.curve == name], key=lambda x: x.tp_from)
        for row in rows:
            if any(not finite_number(value) for value in (row.tp_from, row.tp_to, row.hs_max)):
                errors.append(f"{name}: Hs–Tp values must be finite.")
                continue
            if row.tp_from < 0:
                errors.append(f"{name}: Tp cannot be negative.")
            if row.tp_to <= row.tp_from:
                errors.append(f"{name}: Tp 'to' must be greater than Tp 'from'.")
            if row.hs_max < 0:
                errors.append(f"{name}: Hs limit cannot be negative.")
        for previous, current in zip(rows, rows[1:]):
            if current.tp_from < previous.tp_to - 1e-9:
                errors.append(f"{name}: Tp ranges overlap near {current.tp_from:g} s.")

    if any(not finite_number(value) or value <= 0 for value in learning_curve.values()):
        errors.append("All learning-curve multipliers must be greater than zero.")
    if any(not finite_number(cycle) or cycle < 1 or int(cycle) != cycle for cycle in learning_curve):
        errors.append("Learning-curve cycle numbers must be positive integers.")
    return errors
