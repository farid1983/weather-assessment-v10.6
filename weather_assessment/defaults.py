from __future__ import annotations

import pandas as pd

from .models import Activity, CampaignSettings, HsTpBin, Location, SafeToSafeGroup


def default_settings() -> CampaignSettings:
    return CampaignSettings()


def default_locations() -> list[Location]:
    return [
        Location("PORT", "Base port", "Port", "UTC", "", "Upload the port hindcast CSV."),
        Location("TRANSIT", "Transit route", "Transit", "UTC", "", "Upload the route hindcast CSV."),
        Location("OFFSHORE", "Offshore site", "Offshore", "UTC", "", "Upload the offshore hindcast CSV."),
    ]


def default_activities() -> list[Activity]:
    # Built-in example activity sequence. All criteria must be reviewed for the project.
    rows = [
        (1, 1, True, False, "Ready for loadout in port", "PORT", 3, 3, 18, 100, 100, 100, 100, "00:00", "00:00", "None", ""),
        (2, 1, False, False, "Loading 6 MPs in port", "PORT", 18, 4, 15, 100, 100, 100, 100, "00:00", "00:00", "None", ""),
        (3, 1, False, False, "Loading 6 TPs in port", "PORT", 18, 4, 16, 100, 100, 100, 100, "00:00", "00:00", "None", ""),
        (4, 1, True, False, "Prepare to sail", "PORT", 1, 1, 20, 100, 100, 100, 100, "00:00", "00:00", "None", ""),
        (5, 1, True, False, "Sail out of port", "PORT", 1, 2, 16, 100, 100, 100, 100, "00:00", "00:00", "None", ""),
        (6, 1, True, False, "Transit to offshore site", "TRANSIT", 10, 15, 16, 100, 2, 10, 100, "00:00", "00:00", "None", ""),
        (7, 2, True, False, "Vessel move to location", "OFFSHORE", 1, 2, 15, 100, 1.8, 100, 100, "00:00", "00:00", "None", ""),
        (8, 2, False, False, "Preparation works for MP installation", "OFFSHORE", 1, 2, 14, 100, 1.8, 100, 100, "00:00", "00:00", "None", ""),
        (9, 2, False, False, "Lift and install MP", "OFFSHORE", 6, 8, 100, 15, 1.8, 10, 100, "00:00", "00:00", "None", ""),
        (10, 2, False, True, "Lift and install TP", "OFFSHORE", 3, 5, 13, 100, 1.5, 9, 100, "00:00", "00:00", "None", ""),
        (11, 2, False, False, "Final works on TP", "OFFSHORE", 4, 5, 14, 100, 2, 100, 100, "00:00", "00:00", "None", ""),
        (12, 3, True, False, "Transit back to port", "TRANSIT", 8, 10, 16, 100, 2, 100, 100, "00:00", "00:00", "None", ""),
        (13, 3, True, False, "Arrival to port", "PORT", 1, 1, 16, 100, 100, 100, 100, "00:00", "00:00", "None", ""),
    ]
    return [Activity(*row) for row in rows]



def default_safe_to_safe_groups() -> list[SafeToSafeGroup]:
    return []


def default_learning_curve(max_cycles: int = 20) -> dict[int, float]:
    return {cycle: 1.0 for cycle in range(1, max_cycles + 1)}


def default_hstp_bins() -> list[HsTpBin]:
    curves: dict[str, list[tuple[float, float, float]]] = {
        "Curve1": [
            (0, 5, 2.75), (5, 6, 2.5), (6, 7, 2.25), (7, 8, 2.0),
            (8, 9, 1.75), (9, 10, 1.5), (10, 11, 1.75), (11, 12, 2.0),
            (12, 13, 2.25), (13, 14, 2.5), (14, 16, 2.75),
        ],
        "Curve2": [(0, 6, 2.5), (6, 7, 2.0), (7, 8, 1.75), (8, 10, 1.5), (10, 11, 1.75), (11, 12, 2.0), (12, 15, 2.5)],
        "Curve3": [(0, 3, 1.6), (3, 4, 1.5), (4, 5, 1.25), (5, 6, 1.0), (6, 7, 0.75), (7, 8, 0.5), (8, 9, 0.75), (9, 10, 1.0), (10, 11, 1.25), (11, 12, 1.5), (12, 14, 1.6)],
        "Curve4": [(0, 5, 3.0), (5, 6, 2.75), (6, 7, 2.5), (7, 8, 2.25), (8, 15, 2.0)],
        "Curve5": [(0, 5, 2.0), (5, 6, 2.25), (6, 7, 2.5), (7, 8, 2.75), (8, 15, 3.0)],
        "Curve6": [(0, 5, 1.5), (5, 6, 1.6), (6, 7, 1.75), (7, 8, 2.0), (8, 9, 2.25), (9, 10, 2.5), (10, 11, 2.25), (11, 12, 2.0), (12, 13, 1.75), (13, 14, 1.6), (14, 16, 1.5)],
    }
    return [HsTpBin(name, *values) for name, rows in curves.items() for values in rows]


def locations_dataframe(locations: list[Location] | None = None) -> pd.DataFrame:
    locations = default_locations() if locations is None else locations
    return pd.DataFrame([item.to_dict() for item in locations], columns=[
        "location_id", "name", "location_type", "timezone", "weather_filename", "notes"
    ])


def activities_dataframe(activities: list[Activity] | None = None) -> pd.DataFrame:
    activities = default_activities() if activities is None else activities
    columns = [
        "activity_id", "activity_type", "no_learning_curve", "milestone", "description", "location_id",
        "duration_hours", "weather_window_hours", "safe_to_safe_group", "wind10_limit", "wind100_limit",
        "hs_limit", "tp_limit", "current_limit", "time_start", "time_end", "hstp_curve", "remarks",
    ]
    return pd.DataFrame([activity.to_dict() for activity in activities], columns=columns)


def hstp_dataframe(bins: list[HsTpBin] | None = None) -> pd.DataFrame:
    bins = default_hstp_bins() if bins is None else bins
    return pd.DataFrame([item.to_dict() for item in bins], columns=["curve", "tp_from", "tp_to", "hs_max"])


def learning_dataframe(curve: dict[int, float] | None = None) -> pd.DataFrame:
    curve = default_learning_curve() if curve is None else curve
    return pd.DataFrame({"cycle": list(curve), "multiplier": list(curve.values())})


def safe_to_safe_groups_dataframe(groups: list[SafeToSafeGroup] | None = None) -> pd.DataFrame:
    groups = default_safe_to_safe_groups() if groups is None else groups
    return pd.DataFrame([item.to_dict() for item in groups], columns=[
        "group_id", "description", "assessment_method", "assessment_location", "notes"
    ])
