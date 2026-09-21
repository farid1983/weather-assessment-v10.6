"""One set of derived assessment tables shared by the UI and report adapters."""
from dataclasses import dataclass

import pandas as pd

from .models import CampaignSettings, SimulationResult
from .planning import (
    planning_summary_dataframe, planning_position_dataframe, planning_monthly_dataframe,
    representative_scenarios_dataframe, planning_coverage_dataframe,
)
from .statistics import (
    campaign_summary_dataframe, position_percentile_dataframe, annual_dataframe,
    milestone_dates_dataframe,
)


@dataclass(frozen=True)
class AssessmentAnalytics:
    _tables: dict[str, pd.DataFrame]

    def table(self, name: str) -> pd.DataFrame:
        """Copies prevent chart formatting/filtering from changing shared results."""
        return self._tables[name].copy(deep=True)

    @property
    def duration_percentiles(self) -> dict[float, float]:
        frame = self._tables["campaign"]
        if frame.empty:
            return {}
        return {float(row["Scenario"][1:]): float(row["Duration [hours]"])
                for row in frame.to_dict("records")
                if row["Scenario"].startswith("P") and row["Scenario"] != "P0 (no weather)"}


def build_analytics(results: list[SimulationResult], settings: CampaignSettings, p0: dict) -> AssessmentAnalytics:
    return AssessmentAnalytics({
        "campaign": campaign_summary_dataframe(results, settings, p0["duration_hours"]),
        "positions": position_percentile_dataframe(results, settings, p0["position_elapsed_hours"]),
        "annual": annual_dataframe(results),
        "milestones": milestone_dates_dataframe(results, settings.total_positions),
        "planning_summary": planning_summary_dataframe(results, settings, p0["duration_hours"]),
        "planning_positions": planning_position_dataframe(results, settings, p0["position_elapsed_hours"]),
        "planning_monthly": planning_monthly_dataframe(results, settings),
        "representatives": representative_scenarios_dataframe(results, settings),
        "coverage": planning_coverage_dataframe(results),
    })
