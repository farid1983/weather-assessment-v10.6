"""Application boundary: validated input snapshots, runs and detail resolution.

Public accessors return copies. Presentation code cannot mutate a completed run
by editing the draft project or a previously returned result.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Callable

import pandas as pd

from .models import CampaignSettings, Activity, Location, HsTpBin, SafeToSafeGroup, SequenceItem, SimulationResult
from .analytics import AssessmentAnalytics, build_analytics
from .planning import is_p0_basis, selected_detailed_result
from .project import serialize_project, deserialize_project
from .sequence import build_sequence, p0_simulation_result
from .simulator import run_hindcast, simulate_year
from .validation import required_weather_locations, validate_inputs
from .weather import align_weather_locations, multi_weather_fingerprint, common_weather_coverage

PRESENTATION_SETTINGS = {"project_name", "percentiles", "detailed_results_basis", "year_of_interest"}


def simulation_settings(settings: CampaignSettings) -> dict:
    return {key: value for key, value in settings.to_dict().items() if key not in PRESENTATION_SETTINGS}


def stable_fingerprint(payload: dict) -> str:
    return sha256(json.dumps(payload, sort_keys=True, default=str, allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AssessmentRun:
    project_json: str
    weather_fingerprint: str
    _sequence: tuple[SequenceItem, ...]
    _results: tuple[SimulationResult, ...]
    _p0: SimulationResult
    _weather: dict[str, pd.DataFrame]
    _analytics_cache: dict[tuple[float, ...], AssessmentAnalytics] = field(default_factory=dict, compare=False, repr=False)

    @property
    def coverage(self):
        return common_weather_coverage(self._weather)

    @property
    def sequence(self) -> list[SequenceItem]:
        return deepcopy(list(self._sequence))

    @property
    def results(self) -> list[SimulationResult]:
        return deepcopy(list(self._results))

    @property
    def p0(self) -> SimulationResult:
        return deepcopy(self._p0)

    @property
    def p0_summary(self):
        settings, *_ = deserialize_project(self.project_json)
        return {
            "duration_hours": self._p0.duration_hours,
            "duration_days": self._p0.duration_hours / 24.0,
            "average_hours_per_position": self._p0.duration_hours / settings.total_positions,
            "position_elapsed_hours": dict(self._p0.position_completion_elapsed_hours),
        }

    def _report_settings(self, selected_settings: CampaignSettings) -> CampaignSettings:
        settings, locations, activities, bins, learning, groups, _ = deserialize_project(self.project_json)
        if simulation_settings(settings) != simulation_settings(selected_settings):
            raise ValueError("Calculation settings have changed. Run a new assessment before reporting.")
        for name in PRESENTATION_SETTINGS:
            setattr(settings, name, deepcopy(getattr(selected_settings, name)))
        errors = validate_inputs(settings, activities, bins, learning, locations, safe_to_safe_groups=groups)
        if errors:
            raise ValueError("\n".join(errors))
        return settings

    def detail(self, selected_settings: CampaignSettings) -> SimulationResult | None:
        settings = self._report_settings(selected_settings)
        if is_p0_basis(settings):
            return self.p0
        selected, _, _, _ = selected_detailed_result(self._results, settings)
        if selected is None:
            return None
        if selected.trace is not None and not selected.trace.empty:
            return deepcopy(selected)
        _, _, _, bins, _, _, _ = deserialize_project(self.project_json)
        detailed = simulate_year(self._weather, list(self._sequence), bins, settings, selected.start_year, include_trace=True)
        if not detailed.successful or any(
            abs(float(getattr(detailed, name)) - float(getattr(selected, name))) > 1e-7
            for name in ("duration_hours", "working_hours", "downtime_hours")
        ):
            raise ValueError("Detailed replay does not reconcile with the stored assessment.")
        return detailed

    def analytics(self, selected_settings: CampaignSettings) -> AssessmentAnalytics:
        settings = self._report_settings(selected_settings)
        key = tuple(settings.percentiles)
        if key not in self._analytics_cache:
            self._analytics_cache[key] = build_analytics(list(self._results), settings, self.p0_summary)
        return self._analytics_cache[key]

    def report_context(self, selected_settings):
        settings, locations, activities, bins, learning, groups, configs = deserialize_project(self.project_json)
        settings = self._report_settings(selected_settings)
        return dict(settings=settings, locations=locations, activities=activities, bins=bins,
                    learning_curve=learning, safe_to_safe_groups=groups, sequence=self.sequence,
                    results=self.results, p0_summary=self.p0_summary,
                    analysis=self.analytics(selected_settings),
                    weather_filenames={key: value.get("filename", "") for key, value in configs.items()})


def run_assessment(settings: CampaignSettings, locations: list[Location], activities: list[Activity],
                   bins: list[HsTpBin], learning: dict[int, float], groups: list[SafeToSafeGroup],
                   weather: dict[str, pd.DataFrame], *, weather_configs: dict | None = None,
                   full: bool = False, p0_only: bool = False,
                   progress: Callable[[int, int, int], None] | None = None) -> AssessmentRun:
    errors = validate_inputs(settings, activities, bins, learning, locations,
                             None if p0_only else set(weather), groups)
    if errors:
        raise ValueError("\n".join(errors))
    # Snapshot before execution; no references to the editable draft are retained.
    document = serialize_project(settings, locations, activities, bins, learning, groups,
                                 weather_configs=weather_configs)
    settings, locations, activities, bins, learning, groups, _ = deserialize_project(document)
    sequence = build_sequence(settings, activities, learning, groups, locations)
    p0 = p0_simulation_result(sequence, settings)
    aligned = {} if p0_only else align_weather_locations(
        weather, required_weather_locations(activities, groups), settings.timestep_hours)
    results = [] if p0_only else run_hindcast(aligned, sequence, bins, settings, progress=progress)
    run = AssessmentRun(document, multi_weather_fingerprint(aligned), tuple(sequence), tuple(results), p0, aligned)
    if full and not is_p0_basis(settings):
        detail = run.detail(settings)
        if detail is not None:
            results = [detail if result.start_year == detail.start_year else result for result in results]
            run = AssessmentRun(document, run.weather_fingerprint, tuple(sequence), tuple(results), p0, aligned)
    return run
