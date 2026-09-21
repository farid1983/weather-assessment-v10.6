from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from hashlib import sha256

import numpy as np
import pandas as pd
from .policies import timestep_minutes

REQUIRED_COLUMNS = ["timestamp", "wind10", "wind100", "hs", "tp", "current"]


@dataclass(slots=True)
class WeatherQA:
    row_count: int
    start: pd.Timestamp
    end: pd.Timestamp
    inferred_step_hours: float
    missing_values: dict[str, int]
    duplicate_timestamps: int
    irregular_intervals: int
    available_years: list[int]

    def to_dict(self) -> dict:
        return {
            "Rows": self.row_count,
            "Start": self.start,
            "End": self.end,
            "Inferred step [h]": self.inferred_step_hours,
            "Duplicate timestamps": self.duplicate_timestamps,
            "Irregular intervals": self.irregular_intervals,
            "Available years": f"{min(self.available_years)}–{max(self.available_years)}" if self.available_years else "None",
        }


def preview_csv(data: bytes, skip_rows: int = 0, delimiter: str | None = None, nrows: int = 20) -> pd.DataFrame:
    kwargs = {"skiprows": skip_rows, "nrows": nrows}
    if delimiter and delimiter != "Auto":
        kwargs["sep"] = delimiter
    else:
        kwargs.update({"sep": None, "engine": "python"})
    return pd.read_csv(BytesIO(data), **kwargs)


def auto_preview(data: bytes) -> tuple[pd.DataFrame, int]:
    candidates: list[tuple[int, pd.DataFrame, float]] = []
    for skip in (0, 6, 5, 1, 2, 3, 4, 7, 8):
        try:
            frame = preview_csv(data, skip_rows=skip, nrows=30)
        except Exception:
            continue
        if frame.shape[1] < 6:
            continue
        score = float(frame.notna().sum().sum()) + frame.shape[1] * 10
        for column in frame.columns:
            parsed = pd.to_datetime(frame[column], errors="coerce", dayfirst=True, format="mixed")
            score += parsed.notna().sum() * 3
        candidates.append((skip, frame, score))
    if not candidates:
        raise ValueError("The file could not be read as a delimited weather CSV.")
    skip, frame, _ = max(candidates, key=lambda x: x[2])
    return frame, skip


def load_weather_csv(
    data: bytes,
    skip_rows: int,
    delimiter: str | None,
    column_map: dict[str, str],
    dayfirst: bool = True,
    date_format: str | None = None,
    source_timezone: str = "UTC",
) -> pd.DataFrame:
    kwargs: dict = {"skiprows": skip_rows}
    if delimiter and delimiter != "Auto":
        kwargs["sep"] = delimiter
    else:
        kwargs.update({"sep": None, "engine": "python"})
    raw = pd.read_csv(BytesIO(data), **kwargs)
    missing = [source for source in column_map.values() if source not in raw.columns]
    if missing:
        raise ValueError(f"Mapped columns were not found: {missing}")

    standard = pd.DataFrame()
    timestamp_source = column_map["timestamp"]
    if date_format:
        parsed_timestamp = pd.to_datetime(
            raw[timestamp_source], errors="coerce", dayfirst=dayfirst, format=date_format, utc=True
        )
    else:
        # ISO year-first dates are unambiguous, regardless of a locale checkbox.
        source = raw[timestamp_source].astype(str)
        iso = source.str.match(r"^\d{4}-\d{2}-\d{2}(?:[ T]|$)")
        parsed_timestamp = pd.to_datetime(
            raw[timestamp_source], errors="coerce", dayfirst=dayfirst, format="mixed", utc=True
        )
        if iso.any():
            parsed_timestamp.loc[iso] = pd.to_datetime(source.loc[iso], errors="coerce", format="ISO8601", utc=True)
    if parsed_timestamp.isna().any():
        raise ValueError("Weather contains invalid timestamps. Correct the timestamp mapping or date format.")
    if source_timezone != "UTC":
        # Explicit offsets take precedence. Only naive source timestamps need localization.
        source = raw[timestamp_source].astype(str)
        naive = ~source.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})\s*$", case=False, regex=True)
        if naive.any():
            local = pd.to_datetime(source.loc[naive], errors="raise", dayfirst=dayfirst, format=date_format or "mixed")
            if not date_format:
                iso_local = source.loc[naive].str.match(r"^\d{4}-\d{2}-\d{2}(?:[ T]|$)")
                local.loc[iso_local] = pd.to_datetime(source.loc[naive].loc[iso_local], format="ISO8601")
            parsed_timestamp.loc[naive] = local.dt.tz_localize(source_timezone, ambiguous="raise", nonexistent="raise").dt.tz_convert("UTC")
    standard["timestamp"] = parsed_timestamp.dt.tz_convert(None)
    for target in REQUIRED_COLUMNS[1:]:
        standard[target] = pd.to_numeric(raw[column_map[target]], errors="coerce")
    return standard.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def weather_qa(frame: pd.DataFrame) -> WeatherQA:
    if frame.empty:
        raise ValueError("Weather data is empty after parsing.")
    times = pd.DatetimeIndex(frame["timestamp"])
    duplicate_count = int(times.duplicated().sum())
    unique_times = times.drop_duplicates().sort_values()
    deltas = unique_times.to_series().diff().dropna().dt.total_seconds() / 3600.0
    inferred = float(deltas.median()) if len(deltas) else 0.0
    irregular = int((~np.isclose(deltas.to_numpy(), inferred, rtol=0, atol=1e-8)).sum()) if len(deltas) else 0
    return WeatherQA(
        row_count=len(frame),
        start=times.min(),
        end=times.max(),
        inferred_step_hours=inferred,
        missing_values={column: int(frame[column].isna().sum()) for column in REQUIRED_COLUMNS[1:]},
        duplicate_timestamps=duplicate_count,
        irregular_intervals=irregular,
        available_years=sorted(int(year) for year in times.year.unique()),
    )


def validate_weather_frame(frame: pd.DataFrame) -> None:
    if frame.empty or any(column not in frame for column in REQUIRED_COLUMNS):
        raise ValueError("Weather must contain timestamps and all five weather variables.")
    times = pd.DatetimeIndex(frame["timestamp"])
    if times.hasnans:
        raise ValueError("Weather contains invalid timestamps.")
    if times.tz is not None:
        raise ValueError("Weather timestamps must be normalized to naive UTC before simulation.")
    if times.has_duplicates:
        raise ValueError("Duplicate weather timestamps must be resolved before simulation.")
    values = frame[REQUIRED_COLUMNS[1:]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Weather values must be finite, nonnegative magnitudes; repair missing values and sentinels.")


def prepare_weather(frame: pd.DataFrame, timestep_hours: float) -> pd.DataFrame:
    freq_minutes = timestep_minutes(timestep_hours)
    validate_weather_frame(frame)
    clean = frame.copy().sort_values("timestamp")
    clean = clean.set_index("timestamp")
    target_index = pd.date_range(clean.index.min(), clean.index.max(), freq=f"{freq_minutes}min")
    source_deltas = clean.index.to_series().diff().dropna().dt.total_seconds() / 60.0
    if len(source_deltas) and (source_deltas < freq_minutes - 1e-8).any():
        raise ValueError("Weather resolution is finer than the simulation timestep. Select a finer timestep; lossy downsampling is not supported.")
    if not clean.index.isin(target_index).all():
        raise ValueError("Weather timestamps do not align with the requested simulation grid.")
    source_step_minutes = float(source_deltas.median()) if len(source_deltas) else float(freq_minutes)
    combined = clean.reindex(clean.index.union(target_index)).sort_index()
    fill_limit = max(0, int(round(source_step_minutes / freq_minutes)) - 1)
    if fill_limit > 0:
        combined = combined.ffill(limit=fill_limit)
    clean = combined.reindex(target_index)
    if clean[REQUIRED_COLUMNS[1:]].isna().any().any():
        missing_rows = int(clean[REQUIRED_COLUMNS[1:]].isna().any(axis=1).sum())
        raise ValueError(
            f"The resampled weather series contains {missing_rows:,} missing time steps. "
            "Repair the source gaps or restrict the hindcast range before simulation."
        )
    clean.index.name = "timestamp"
    return clean.reset_index()[REQUIRED_COLUMNS]


def align_weather_locations(
    weather_by_location: dict[str, pd.DataFrame],
    used_location_ids: set[str] | list[str],
    timestep_hours: float,
) -> dict[str, pd.DataFrame]:
    """Prepare and align all used location datasets to one common campaign clock.

    Only the common timestamp coverage is retained. The same historical timestamp is
    therefore used at every location, preserving the year-to-year weather relationship.
    """
    used = sorted({str(item) for item in used_location_ids})
    if not used:
        raise ValueError("At least one weather location is required.")
    missing = [location_id for location_id in used if location_id not in weather_by_location]
    if missing:
        raise ValueError("Weather data is missing for location(s): " + ", ".join(sorted(missing)))
    prepared = {location_id: prepare_weather(weather_by_location[location_id], timestep_hours) for location_id in used}
    starts = [pd.Timestamp(frame["timestamp"].min()) for frame in prepared.values()]
    ends = [pd.Timestamp(frame["timestamp"].max()) for frame in prepared.values()]
    common_start = max(starts)
    common_end = min(ends)
    if common_start >= common_end:
        raise ValueError("The used locations do not have overlapping weather coverage.")
    freq_minutes = timestep_minutes(timestep_hours)
    common_index = pd.date_range(common_start, common_end, freq=f"{freq_minutes}min")
    aligned: dict[str, pd.DataFrame] = {}
    for location_id, frame in prepared.items():
        indexed = frame.set_index("timestamp").reindex(common_index)
        if indexed[REQUIRED_COLUMNS[1:]].isna().any().any():
            missing_steps = int(indexed[REQUIRED_COLUMNS[1:]].isna().any(axis=1).sum())
            raise ValueError(
                f"Location '{location_id}' has {missing_steps:,} missing steps inside the common weather period."
            )
        indexed.index.name = "timestamp"
        aligned[location_id] = indexed.reset_index()[REQUIRED_COLUMNS]
    return aligned


def common_weather_coverage(weather_by_location: dict[str, pd.DataFrame]) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    if not weather_by_location:
        return None
    starts = [pd.Timestamp(frame["timestamp"].min()) for frame in weather_by_location.values() if not frame.empty]
    ends = [pd.Timestamp(frame["timestamp"].max()) for frame in weather_by_location.values() if not frame.empty]
    if not starts or not ends:
        return None
    return max(starts), min(ends)


def weather_fingerprint(frame: pd.DataFrame) -> str:
    hashed = pd.util.hash_pandas_object(frame, index=True).to_numpy(dtype=np.uint64)
    digest = sha256(str(tuple(frame.columns)).encode("utf-8"))
    digest.update(hashed.tobytes())
    return digest.hexdigest()


def multi_weather_fingerprint(weather_by_location: dict[str, pd.DataFrame]) -> str:
    pieces = [f"{key}:{weather_fingerprint(value)}" for key, value in sorted(weather_by_location.items())]
    return "|".join(pieces)
