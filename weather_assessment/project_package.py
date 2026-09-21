from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile
from typing import Any

from .models import Activity, CampaignSettings, HsTpBin, Location, SafeToSafeGroup
from .project import project_payload


def build_project_package(
    settings: CampaignSettings,
    locations: list[Location],
    activities: list[Activity],
    bins: list[HsTpBin],
    learning_curve: dict[int, float],
    safe_to_safe_groups: list[SafeToSafeGroup] | None,
    weather_configs: dict[str, dict[str, Any]],
    weather_files: dict[str, bytes],
    app_version: str,
    include_weather: bool = True,
) -> bytes:
    output = BytesIO()
    payload = project_payload(
        settings, locations, activities, bins, learning_curve, safe_to_safe_groups, app_version, weather_configs
    )
    manifest: dict[str, Any] = {"weather_files": {}}
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        if include_weather:
            for location_id, content in weather_files.items():
                filename = weather_configs.get(location_id, {}).get("filename") or f"{location_id}.csv"
                safe_name = "".join(ch for ch in str(filename) if ch.isalnum() or ch in "._-") or f"{location_id}.csv"
                path = f"weather/{location_id}/{safe_name}"
                archive.writestr(path, content)
                manifest["weather_files"][location_id] = path
        archive.writestr("project.json", json.dumps(payload, indent=2, default=str))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return output.getvalue()


def load_project_package(
    data: bytes,
) -> tuple[str, dict[str, bytes]]:
    try:
        with ZipFile(BytesIO(data)) as archive:
            project_text = archive.read("project.json").decode("utf-8")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            weather_files: dict[str, bytes] = {}
            for location_id, path in manifest.get("weather_files", {}).items():
                weather_files[str(location_id)] = archive.read(path)
            return project_text, weather_files
    except (BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("The uploaded project package is not valid.") from exc
