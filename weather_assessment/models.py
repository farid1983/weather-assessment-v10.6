from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from .policies import parse_bool


@dataclass(slots=True)
class CampaignSettings:
    project_name: str = "Offshore installation campaign"
    nominal_year: int = 2026
    start_month: int = 1
    start_day: int = 1
    positions_per_cycle: int = 6
    total_positions: int = 60
    percentiles: tuple[float, float, float] = (50.0, 75.0, 90.0)
    timestep_hours: float = 1.0
    detailed_results_basis: str = "Percentile 1 representative hindcast year"
    year_of_interest: Optional[int] = None
    hindcast_start_year: Optional[int] = None
    hindcast_end_year: Optional[int] = None
    default_safe_to_safe_method: str = "MOST_STRINGENT"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["percentiles"] = list(self.percentiles)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampaignSettings":
        values = dict(data)
        values["percentiles"] = tuple(float(x) for x in values.get("percentiles", (50, 75, 90)))
        basis = str(values.get("detailed_results_basis", "Percentile 1 representative hindcast year") or "Percentile 1 representative hindcast year").strip()
        if basis.lower() == "p50 representative hindcast year":
            basis = "Percentile 1 representative hindcast year"
        values["detailed_results_basis"] = basis
        method = str(values.get("default_safe_to_safe_method", "MOST_STRINGENT") or "MOST_STRINGENT").strip().upper()
        values["default_safe_to_safe_method"] = method
        return cls(**values)


@dataclass(slots=True)
class Location:
    location_id: str
    name: str
    location_type: str = "Offshore"
    timezone: str = "UTC"
    weather_filename: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Location":
        return cls(
            location_id=str(data.get("location_id", "")).strip(),
            name=str(data.get("name", "")).strip(),
            location_type=str(data.get("location_type", "Other") or "Other"),
            timezone=str(data.get("timezone", "UTC") or "UTC"),
            weather_filename=str(data.get("weather_filename", "") or ""),
            notes=str(data.get("notes", "") or ""),
        )


@dataclass(slots=True)
class SafeToSafeGroup:
    group_id: str
    description: str = ""
    assessment_method: str = "MOST_STRINGENT"
    assessment_location: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SafeToSafeGroup":
        method = str(data.get("assessment_method", "MOST_STRINGENT") or "MOST_STRINGENT").strip().upper()
        return cls(
            group_id=str(data.get("group_id", "") or "").strip(),
            description=str(data.get("description", "") or "").strip(),
            assessment_method=method,
            assessment_location=str(data.get("assessment_location", "") or "").strip(),
            notes=str(data.get("notes", "") or "").strip(),
        )


@dataclass(slots=True)
class Activity:
    activity_id: int
    activity_type: int
    no_learning_curve: bool
    milestone: bool
    description: str
    location_id: str
    duration_hours: float
    weather_window_hours: float
    wind10_limit: float
    wind100_limit: float
    hs_limit: float
    tp_limit: float
    current_limit: float
    time_start: str = "00:00"
    time_end: str = "00:00"
    hstp_curve: str = "None"
    remarks: str = ""
    safe_to_safe_group: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Activity":
        group_value = data.get("safe_to_safe_group", "")
        safe_group = "" if pd.isna(group_value) else str(group_value or "").strip()
        return cls(
            activity_id=int(data["activity_id"]),
            activity_type=int(data["activity_type"]),
            no_learning_curve=parse_bool(data.get("no_learning_curve", False)),
            milestone=parse_bool(data.get("milestone", False)),
            description=str(data.get("description", "")),
            location_id=str(data.get("location_id", "OFFSHORE") or "OFFSHORE"),
            duration_hours=float(data.get("duration_hours", 0)),
            weather_window_hours=float(data.get("weather_window_hours", 0)),
            wind10_limit=float(data.get("wind10_limit", 0)),
            wind100_limit=float(data.get("wind100_limit", 0)),
            hs_limit=float(data.get("hs_limit", 0)),
            tp_limit=float(data.get("tp_limit", 0)),
            current_limit=float(data.get("current_limit", 0)),
            time_start=str(data.get("time_start", "00:00")),
            time_end=str(data.get("time_end", "00:00")),
            hstp_curve=str(data.get("hstp_curve", "None") or "None"),
            remarks=str(data.get("remarks", "") or ""),
            safe_to_safe_group=safe_group,
        )


@dataclass(slots=True)
class HsTpBin:
    curve: str
    tp_from: float
    tp_to: float
    hs_max: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SequenceItem:
    sequence_no: int
    cycle: int
    position: Optional[int]
    activity_id: int
    activity_type: int
    learning_multiplier: float
    milestone: bool
    description: str
    location_id: str
    duration_hours: float
    weather_window_hours: float
    wind10_limit: float
    wind100_limit: float
    hs_limit: float
    tp_limit: float
    current_limit: float
    time_start: str
    time_end: str
    hstp_curve: str
    remarks: str = ""
    safe_to_safe_group: str = ""
    group_role: str = "Standalone"
    group_method: str = ""
    group_assessment_location: str = ""
    timezone: str = "UTC"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SimulationResult:
    start_year: int
    successful: bool
    message: str
    campaign_start: datetime
    campaign_finish: Optional[datetime]
    duration_hours: Optional[float]
    working_hours: float
    downtime_hours: float
    position_completion_dates: dict[int, datetime] = field(default_factory=dict)
    position_completion_elapsed_hours: dict[int, float] = field(default_factory=dict)
    downtime_by_cause: dict[str, float] = field(default_factory=dict)
    downtime_by_main_factor: dict[str, float] = field(default_factory=dict)
    downtime_by_type_factor: dict[str, dict[str, float]] = field(default_factory=dict)
    downtime_by_activity: dict[str, float] = field(default_factory=dict)
    working_by_location: dict[str, float] = field(default_factory=dict)
    downtime_by_location: dict[str, float] = field(default_factory=dict)
    downtime_by_location_cause: dict[str, dict[str, float]] = field(default_factory=dict)
    downtime_by_group: dict[str, float] = field(default_factory=dict)
    monthly_records: list[dict[str, Any]] = field(default_factory=list)
    planning_monthly_records: list[dict[str, Any]] = field(default_factory=list)
    trace: Optional[pd.DataFrame] = None
    exact_p0_hours: float = 0.0
    timestep_adjustment_hours: float = 0.0
    data_coverage_limited: bool = False
    downtime_by_activity_id: dict[int, float] = field(default_factory=dict)
    activity_descriptions: dict[int, str] = field(default_factory=dict)

    def annual_row(self) -> dict[str, Any]:
        return {
            "Hindcast start year": self.start_year,
            "Successful": self.successful,
            "Campaign start": self.campaign_start,
            "Campaign finish": self.campaign_finish,
            "Duration [days]": None if self.duration_hours is None else self.duration_hours / 24.0,
            "Duration [hours]": self.duration_hours,
            "Exact P0 [hours]": self.exact_p0_hours,
            "Working time [hours]": self.working_hours,
            "Timestep adjustment [hours]": self.timestep_adjustment_hours,
            "Downtime [hours]": self.downtime_hours,
            "Completed positions": len(self.position_completion_dates),
            "Data coverage limited": self.data_coverage_limited,
            "Message": self.message,
        }
