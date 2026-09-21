from __future__ import annotations

import json
from typing import Any

from .models import Activity, CampaignSettings, HsTpBin, Location, SafeToSafeGroup


def project_payload(
    settings: CampaignSettings,
    locations: list[Location],
    activities: list[Activity],
    bins: list[HsTpBin],
    learning_curve: dict[int, float],
    safe_to_safe_groups: list[SafeToSafeGroup] | None = None,
    app_version: str | None = None,
    weather_configs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "format_version": 4,
        "app_version": app_version,
        "settings": settings.to_dict(),
        "locations": [item.to_dict() for item in locations],
        "activities": [item.to_dict() for item in activities],
        "hstp_bins": [item.to_dict() for item in bins],
        "learning_curve": {str(key): value for key, value in learning_curve.items()},
        "safe_to_safe_groups": [item.to_dict() for item in (safe_to_safe_groups or [])],
        "weather_configs": weather_configs or {},
    }


def serialize_project(
    settings: CampaignSettings,
    locations: list[Location],
    activities: list[Activity],
    bins: list[HsTpBin],
    learning_curve: dict[int, float],
    safe_to_safe_groups: list[SafeToSafeGroup] | None = None,
    app_version: str | None = None,
    weather_configs: dict[str, dict[str, Any]] | None = None,
) -> str:
    return json.dumps(
        project_payload(settings, locations, activities, bins, learning_curve, safe_to_safe_groups, app_version, weather_configs),
        indent=2,
        default=str,
    )


def deserialize_project(
    text: str,
) -> tuple[CampaignSettings, list[Location], list[Activity], list[HsTpBin], dict[int, float], list[SafeToSafeGroup], dict[str, dict[str, Any]]]:
    payload: dict[str, Any] = json.loads(text)
    version = payload.get("format_version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version not in {1, 2, 3, 4}:
        raise ValueError(f"Unsupported project format version: {version!r}.")
    settings = CampaignSettings.from_dict(payload["settings"])
    activities = [Activity.from_dict(item) for item in payload["activities"]]
    bins = [HsTpBin(**item) for item in payload.get("hstp_bins", [])]
    learning = {int(key): float(value) for key, value in payload.get("learning_curve", {}).items()}
    groups = [SafeToSafeGroup.from_dict(item) for item in payload.get("safe_to_safe_groups", [])]
    if payload.get("locations"):
        locations = [Location.from_dict(item) for item in payload["locations"]]
    else:
        unique = sorted({item.location_id for item in activities} or {"OFFSHORE"})
        locations = [Location(location_id=item, name=item.title()) for item in unique]
    weather_configs = payload.get("weather_configs", {}) or {}
    return settings, locations, activities, bins, learning, groups, weather_configs
