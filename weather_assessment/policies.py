"""Shared input and numerical contracts used by adapters and calculations."""
from __future__ import annotations

import math
import numpy as np

SUPPORTED_TIMESTEPS = (1.0, 0.5, 0.25)
GROUP_METHODS = ("MOST_STRINGENT", "TIME_PHASED")


def finite_number(value: object) -> bool:
    return isinstance(value, (int, float, np.number)) and not isinstance(value, (bool, np.bool_)) and math.isfinite(float(value))


def timestep_minutes(hours: float) -> int:
    if not finite_number(hours) or hours not in SUPPORTED_TIMESTEPS:
        raise ValueError("Simulation time step must be 1, 0.5, or 0.25 hours.")
    return int(round(hours * 60))


def parse_bool(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value is None or value == "":
        return False
    text = str(value).strip().lower()
    if text in {"1", "1.0", "true", "yes", "y", "checked", "x"}:
        return True
    if text in {"0", "0.0", "false", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def engineering_percentile(values, percentile: float, *, higher_is_better: bool = False) -> float:
    """Upper-tail adverse metrics; lower-tail assurance for beneficial metrics."""
    quantile = 100.0 - percentile if higher_is_better else percentile
    return float(np.percentile(values, quantile, method="linear"))
