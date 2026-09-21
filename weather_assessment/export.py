from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO

import numpy as np
import pandas as pd
from xlsxwriter.utility import xl_col_to_name

from .models import Activity, CampaignSettings, HsTpBin, Location, SafeToSafeGroup, SequenceItem, SimulationResult
from .analytics import AssessmentAnalytics, build_analytics
from .planning import detailed_results_basis_display, selected_detailed_result, is_p0_basis, planning_monthly_dataframe, planning_start, representative_result, remapped_monthly_dataframe
from .sequence import sequence_dataframe, p0_trace_dataframe, p0_simulation_result
from .statistics import downtime_breakdown_dataframe, downtime_detail_frames, successful_results

BASE_SHEET_NAMES = [
    "Assessment metadata",
    "IN_general",
    "IN_locations",
    "IN_safe to safe",
    "IN_HsTp curve",
    "IN_learning curve",
    "IN_sequence",
    "OUT_years coverage",
    "OUT_P0 run",
    "OUT_run",
    "OUT_overall",
    "OUT_overall MS",
    "OUT_overall monthly",
    "OUT_specific month",
    "OUT_overall annual",
    "OUT_planning summary",
    "OUT_planning MS",
    "OUT_overall DT",
]

NAVY = "#1F4E78"
BLUE = "#4472C4"
LIGHT_BLUE = "#D9EAF7"
GREEN = "#70AD47"
LIGHT_GREEN = "#E2F0D9"
ORANGE = "#ED7D31"
RED = "#C00000"
LIGHT_RED = "#FCE4D6"
GREY = "#A5A5A5"
DARK = "#1F1F1F"
BORDER = "#B4C6E7"


def _formats(workbook):
    common = {"font_name": "Calibri", "font_size": 11, "font_color": DARK}
    return {
        "title": workbook.add_format({**common, "bold": True, "font_size": 15, "font_color": "#FFFFFF", "bg_color": NAVY, "align": "left", "valign": "vcenter"}),
        "subtitle": workbook.add_format({**common, "italic": True, "font_size": 10, "bg_color": LIGHT_BLUE, "text_wrap": True, "valign": "vcenter"}),
        "section": workbook.add_format({**common, "bold": True, "font_color": "#FFFFFF", "bg_color": BLUE, "border": 1, "border_color": BORDER, "align": "left", "valign": "vcenter"}),
        "header": workbook.add_format({**common, "bold": True, "font_color": "#FFFFFF", "bg_color": BLUE, "border": 1, "border_color": BORDER, "align": "center", "valign": "vcenter", "text_wrap": True}),
        "subheader": workbook.add_format({**common, "bold": True, "bg_color": LIGHT_BLUE, "border": 1, "border_color": BORDER, "align": "center", "valign": "vcenter", "text_wrap": True}),
        "text": workbook.add_format({**common, "border": 1, "border_color": BORDER, "valign": "top", "text_wrap": True}),
        "center": workbook.add_format({**common, "border": 1, "border_color": BORDER, "align": "center", "valign": "vcenter"}),
        "number": workbook.add_format({**common, "border": 1, "border_color": BORDER, "num_format": "0.000", "valign": "top"}),
        "integer": workbook.add_format({**common, "border": 1, "border_color": BORDER, "num_format": "0", "valign": "top"}),
        "percent": workbook.add_format({**common, "border": 1, "border_color": BORDER, "num_format": "0.000%", "valign": "top"}),
        "percent100": workbook.add_format({**common, "border": 1, "border_color": BORDER, "num_format": '0.000"%"', "valign": "top"}),
        "date": workbook.add_format({**common, "border": 1, "border_color": BORDER, "num_format": "yyyy-mm-dd", "valign": "top"}),
        "datetime": workbook.add_format({**common, "border": 1, "border_color": BORDER, "num_format": "yyyy-mm-dd hh:mm", "valign": "top"}),
        "metadata_datetime": workbook.add_format({**common, "border": 1, "border_color": BORDER, "num_format": "dd-mmm-yyyy hh:mm", "valign": "top"}),
        "metadata_date": workbook.add_format({**common, "border": 1, "border_color": BORDER, "num_format": "dd-mmm-yyyy", "valign": "top"}),
        "datetime_small": workbook.add_format({**common, "font_size": 9, "border": 1, "border_color": BORDER, "num_format": "yyyy-mm-dd hh:mm", "valign": "vcenter", "align": "center"}),
        "working": workbook.add_format({**common, "bg_color": LIGHT_GREEN, "border": 1, "border_color": BORDER}),
        "downtime": workbook.add_format({**common, "bg_color": RED, "font_color": "#FFFFFF", "border": 1, "border_color": RED}),
        "warning": workbook.add_format({**common, "bg_color": "#FFF2CC", "border": 1, "border_color": BORDER}),
        "note": workbook.add_format({**common, "font_size": 9, "bg_color": "#F2F6FA", "border": 1, "border_color": BORDER, "text_wrap": True, "valign": "top"}),
    }


def _sheet_title(worksheet, title: str, subtitle: str, end_col: int, fmts) -> None:
    worksheet.merge_range(0, 0, 0, end_col, title, fmts["title"])
    worksheet.merge_range(1, 0, 1, end_col, subtitle, fmts["subtitle"])
    worksheet.set_row(0, 24)
    worksheet.set_row(1, 32)


def _column_format(workbook, series: pd.Series, name: str, fmts):
    lowered = str(name).lower()
    if pd.api.types.is_bool_dtype(series):
        return fmts["center"]
    if pd.api.types.is_datetime64_any_dtype(series):
        return fmts["datetime"]
    if pd.api.types.is_numeric_dtype(series):
        if "%" in lowered:
            fraction_columns = {"Downtime [%]", "DT [%]", "Workable time [% campaign]", "Downtime [% campaign]"}
            if name in fraction_columns:
                return fmts["percent"]
            return fmts["percent100"]
        if "_pct" in lowered:
            return fmts["percent"]
        if pd.api.types.is_integer_dtype(series):
            return fmts["integer"]
        return fmts["number"]
    return fmts["text"]


def _write_value(worksheet, row: int, col: int, value, fmt) -> None:
    if pd.isna(value):
        worksheet.write_blank(row, col, None, fmt)
    elif isinstance(value, pd.Timestamp):
        worksheet.write_datetime(row, col, value.to_pydatetime(), fmt)
    elif isinstance(value, datetime):
        worksheet.write_datetime(row, col, value, fmt)
    elif isinstance(value, (np.bool_, bool)):
        worksheet.write_boolean(row, col, bool(value), fmt)
    elif isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        worksheet.write_number(row, col, int(value), fmt)
    elif isinstance(value, (np.floating, float)):
        worksheet.write_number(row, col, float(value), fmt)
    else:
        worksheet.write(row, col, str(value), fmt)


def _write_dataframe(worksheet, frame: pd.DataFrame, start_row: int, start_col: int, workbook, fmts, *, autofilter: bool = False, format_overrides: dict[str, object] | None = None) -> tuple[int, int]:
    if frame is None:
        frame = pd.DataFrame()
    columns = list(frame.columns)
    if not columns:
        return start_row, start_col
    worksheet.write_row(start_row, start_col, columns, fmts["header"])
    format_overrides = format_overrides or {}
    for row_offset, row in enumerate(frame.itertuples(index=False, name=None), start=1):
        for col_offset, value in enumerate(row):
            series = frame.iloc[:, col_offset]
            fmt = format_overrides.get(columns[col_offset]) or _column_format(workbook, series, columns[col_offset], fmts)
            _write_value(worksheet, start_row + row_offset, start_col + col_offset, value, fmt)
    end_row = start_row + len(frame)
    end_col = start_col + len(columns) - 1
    if autofilter and len(frame):
        worksheet.autofilter(start_row, start_col, end_row, end_col)
    return end_row, end_col


def _write_setting_value_table(worksheet, rows: list[tuple[str, object]], start_row: int, workbook, fmts) -> tuple[int, int]:
    """Write Setting over A:B and Value over C:E to keep campaign rows compact."""
    worksheet.merge_range(start_row, 0, start_row, 1, "Setting", fmts["header"])
    worksheet.merge_range(start_row, 2, start_row, 4, "Value", fmts["header"])
    value_series = pd.Series([value for _, value in rows], dtype="object")
    for offset, (label, value) in enumerate(rows, start=1):
        row = start_row + offset
        worksheet.merge_range(row, 0, row, 1, label, fmts["text"])
        worksheet.merge_range(row, 2, row, 4, "", fmts["text"])
        fmt = _column_format(workbook, value_series, "Value", fmts)
        _write_value(worksheet, row, 2, value, fmt)
        worksheet.set_row(row, 18)
    return start_row + len(rows), 4


def _write_last_column_spanned(worksheet, frame: pd.DataFrame, start_row: int, workbook, fmts, *, span: int = 3) -> tuple[int, int]:
    """Write a dataframe with its final logical column merged across several physical columns."""
    if frame is None or frame.empty and not len(frame.columns):
        return start_row, 0
    columns = list(frame.columns)
    last_logical = len(columns) - 1
    last_start = last_logical
    last_end = last_start + span - 1
    for col, name in enumerate(columns[:-1]):
        worksheet.write(start_row, col, name, fmts["header"])
    worksheet.merge_range(start_row, last_start, start_row, last_end, columns[-1], fmts["header"])
    for row_offset, row_values in enumerate(frame.itertuples(index=False, name=None), start=1):
        target_row = start_row + row_offset
        for col, value in enumerate(row_values[:-1]):
            fmt = _column_format(workbook, frame.iloc[:, col], columns[col], fmts)
            _write_value(worksheet, target_row, col, value, fmt)
        worksheet.merge_range(target_row, last_start, target_row, last_end, "", fmts["text"])
        _write_value(worksheet, target_row, last_start, row_values[-1], fmts["text"])
        worksheet.set_row(target_row, 18)
    return start_row + len(frame), last_end


def _write_section(worksheet, row: int, title: str, end_col: int, fmts) -> None:
    worksheet.merge_range(row, 0, row, end_col, title, fmts["section"])
    worksheet.set_row(row, 20)


def _style_chart(chart, *, x_name: str = "", y_name: str = "", legend: str = "bottom") -> None:
    chart.set_chartarea({"border": {"none": True}, "fill": {"color": "#FFFFFF"}})
    chart.set_plotarea({"border": {"none": True}, "fill": {"color": "#FFFFFF"}})
    if legend == "none":
        chart.set_legend({"none": True})
    else:
        chart.set_legend({"position": legend, "font": {"name": "Calibri", "size": 9}, "border": {"none": True}})
    chart.set_x_axis({
        "name": x_name,
        "name_font": {"name": "Calibri", "size": 10, "bold": True},
        "num_font": {"name": "Calibri", "size": 8},
        "major_gridlines": {"visible": False},
        "line": {"color": "#7F7F7F", "width": 0.25},
    })
    chart.set_y_axis({
        "name": y_name,
        "name_font": {"name": "Calibri", "size": 10, "bold": True},
        "num_font": {"name": "Calibri", "size": 8},
        "major_gridlines": {"visible": False},
        "line": {"color": "#7F7F7F", "width": 0.25},
    })


def _scenario_downtime_frames(results: list[SimulationResult], settings: CampaignSettings):
    summary_rows: list[dict] = []
    activity_rows: list[dict] = []
    representative_map: dict[str, SimulationResult] = {}
    for percentile in settings.percentiles:
        representative, target = representative_result(results, percentile)
        if representative is None or target is None:
            continue
        scenario = f"P{percentile:g}"
        representative_map[scenario] = representative
        campaign_hours = float(representative.duration_hours or 0.0)
        summary_rows.append({
            "Planning scenario": scenario,
            "Statistical duration [days]": float(target) / 24.0,
            "Representative hindcast year": representative.start_year,
            "Representative duration [days]": campaign_hours / 24.0,
            "Workable time [hours]": float(representative.working_hours or 0.0),
            "Downtime [hours]": float(representative.downtime_hours or 0.0),
            "Workable time [% campaign]": float(representative.working_hours or 0.0) / campaign_hours if campaign_hours else 0.0,
            "Downtime [% campaign]": float(representative.downtime_hours or 0.0) / campaign_hours if campaign_hours else 0.0,
        })
        _, activity = downtime_breakdown_dataframe(representative)
        for _, row in activity.iterrows():
            activity_rows.append({
                "Planning scenario": scenario,
                "Representative hindcast year": representative.start_year,
                **row.to_dict(),
            })
    return pd.DataFrame(summary_rows), pd.DataFrame(activity_rows), representative_map


def _specific_month_statistics(results: list[SimulationResult], settings: CampaignSettings, monthly: pd.DataFrame | None = None) -> pd.DataFrame:
    """Format the authoritative planning statistics without inventing a schedule."""
    monthly = planning_monthly_dataframe(results, settings) if monthly is None else monthly
    if monthly.empty:
        return pd.DataFrame()
    source = monthly.copy()
    source.index = pd.to_datetime(source["Planning month"]).dt.to_period("M")
    first = pd.Period(year=settings.nominal_year, month=1, freq="M")
    last = max(pd.Period(year=settings.nominal_year, month=12, freq="M"), source.index.max())
    periods = pd.period_range(first, last, freq="M")
    multiple_years = len({period.year for period in periods}) > 1
    labels = ["Mean"] + [f"P{p:g}" for p in settings.percentiles]
    rows = []
    for period in periods:
        record = source.loc[period] if period in source.index else None
        row = {"Month": period.strftime("%b %Y" if multiple_years else "%b")}
        for label in labels:
            suffix = "mean" if label == "Mean" else label
            cumulative_column = f"cumulative_positions {suffix}"
            row[f"Cumulative positions - {label}"] = (
                float(record[cumulative_column]) if record is not None else
                float(source.iloc[-1][cumulative_column]) if period > source.index.max() else 0.0
            )
        for prefix, metric in [("Downtime hours", "downtime_hours"), ("Workable hours", "working_hours")]:
            for label in labels:
                suffix = "mean" if label == "Mean" else label
                row[f"{prefix} - {label}"] = float(record[f"{metric} {suffix}"]) if record is not None else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def _representative_monthly_scenarios(
    results: list[SimulationResult],
    settings: CampaignSettings,
) -> tuple[list[pd.Period], list[dict[str, object]]]:
    """Return complete representative-year monthly schedules for each percentile.

    Unlike the pointwise monthly statistics, every scenario here is one
    executable hindcast simulation. Monthly working time and downtime therefore
    add exactly to the selected representative duration.
    """
    start = planning_start(settings)
    representatives: list[dict[str, object]] = []
    latest_finish = datetime(settings.nominal_year, 12, 31, 23, 59, 59)

    for percentile in settings.percentiles:
        result, target = representative_result(results, percentile)
        if result is None or target is None or result.duration_hours is None:
            continue
        finish = start + timedelta(hours=float(result.duration_hours))
        latest_finish = max(latest_finish, finish)
        representatives.append({
            "label": f"P{percentile:g}",
            "percentile": float(percentile),
            "target_hours": float(target),
            "result": result,
            "finish": finish,
        })

    first_period = pd.Period(year=settings.nominal_year, month=1, freq="M")
    final_period = pd.Period(latest_finish, freq="M")
    periods = list(pd.period_range(first_period, final_period, freq="M"))
    start_period = pd.Period(start, freq="M")

    for scenario in representatives:
        result = scenario["result"]
        assert isinstance(result, SimulationResult)
        frame = remapped_monthly_dataframe(result, settings)
        by_period: dict[pd.Period, dict[str, object]] = {}
        for _, row in frame.iterrows():
            period = pd.Period(pd.Timestamp(row["Planning month"]), freq="M")
            by_period[period] = row.to_dict()

        rows: list[dict[str, object]] = []
        cumulative = 0.0
        finish = scenario["finish"]
        assert isinstance(finish, datetime)
        for period in periods:
            record = by_period.get(period)
            period_start = period.to_timestamp().to_pydatetime()
            if period < start_period:
                row = {
                    "Month": period,
                    "Positions": 0.0,
                    "Cumulative": 0.0,
                    "Working [h]": np.nan,
                    "Downtime [h]": np.nan,
                    "Campaign [h]": np.nan,
                    "DT [%]": np.nan,
                }
            elif record is not None:
                positions = float(record.get("positions_completed", 0.0))
                cumulative = float(record.get("cumulative_positions", cumulative + positions))
                working = float(record.get("working_hours", 0.0))
                downtime = float(record.get("downtime_hours", 0.0))
                campaign = working + downtime
                row = {
                    "Month": period,
                    "Positions": positions,
                    "Cumulative": cumulative,
                    "Working [h]": working,
                    "Downtime [h]": downtime,
                    "Campaign [h]": campaign,
                    "DT [%]": downtime / campaign if campaign else 0.0,
                }
            elif period_start >= finish:
                row = {
                    "Month": period,
                    "Positions": np.nan,
                    "Cumulative": float(settings.total_positions),
                    "Working [h]": np.nan,
                    "Downtime [h]": np.nan,
                    "Campaign [h]": np.nan,
                    "DT [%]": np.nan,
                }
            else:
                row = {
                    "Month": period,
                    "Positions": 0.0,
                    "Cumulative": cumulative,
                    "Working [h]": 0.0,
                    "Downtime [h]": 0.0,
                    "Campaign [h]": 0.0,
                    "DT [%]": 0.0,
                }
            rows.append(row)
        scenario["monthly"] = pd.DataFrame(rows)

    return periods, representatives


def _write_overall_monthly(
    worksheet,
    workbook,
    fmts,
    periods: list[pd.Period],
    scenarios: list[dict[str, object]],
    settings: CampaignSettings,
    p0_hours: float,
) -> None:
    """Write the additive representative-year monthly output."""
    group_width = 6
    end_col = max(18, group_width * max(1, len(scenarios)))
    _sheet_title(
        worksheet,
        "OUT_overall monthly",
        "Additive representative hindcast-year schedules for P50, P75 and P90. Each scenario reconciles independently to its complete representative campaign duration.",
        end_col,
        fmts,
    )

    # A. Statistical planning and representative-year selection.
    worksheet.merge_range(3, 0, 3, 7, "A. Statistical planning and representative-year selection", fmts["section"])
    headers_a = [
        "Scenario", "Statistical duration [h]", "Statistical duration [d]",
        "Representative year", "Representative duration [h]", "Representative duration [d]",
        "Representative - target [h]", "Interpretation",
    ]
    worksheet.write_row(4, 0, headers_a, fmts["header"])

    # B. Additive reconciliation.
    worksheet.merge_range(3, 9, 3, 18, "B. Additive representative-year reconciliation", fmts["section"])
    headers_b = [
        "Scenario", "Exact P0 [h]", "Timestep adjustment [h]", "Representative downtime [h]",
        "Reconciled duration [h]", "Reported representative duration [h]", "Variance [h]",
        "Downtime [%]", "Status", "Reconciliation",
    ]
    worksheet.write_row(4, 9, headers_b, fmts["header"])

    for offset, scenario in enumerate(scenarios, start=5):
        result = scenario["result"]
        assert isinstance(result, SimulationResult)
        target = float(scenario["target_hours"])
        duration = float(result.duration_hours or 0.0)
        adjustment = float(result.timestep_adjustment_hours or (result.working_hours - p0_hours))
        downtime = float(result.downtime_hours or 0.0)
        reconciled = p0_hours + adjustment + downtime
        variance = reconciled - duration
        label = str(scenario["label"])

        values_a = [
            label, target, target / 24.0, result.start_year, duration, duration / 24.0,
            duration - target, "Closest complete historical simulation to the statistical target",
        ]
        formats_a = [fmts["center"], fmts["number"], fmts["number"], fmts["integer"], fmts["number"], fmts["number"], fmts["number"], fmts["text"]]
        for col, (value, fmt) in enumerate(zip(values_a, formats_a)):
            _write_value(worksheet, offset, col, value, fmt)

        values_b = [
            label, p0_hours, adjustment, downtime, reconciled, duration, variance,
            downtime / duration if duration else 0.0,
            "RECONCILED" if abs(variance) < 0.001 else "CHECK",
            "P0 + timestep adjustment + representative downtime",
        ]
        formats_b = [fmts["center"], fmts["number"], fmts["number"], fmts["number"], fmts["number"], fmts["number"], fmts["number"], fmts["percent"], fmts["center"], fmts["text"]]
        for local_col, (value, fmt) in enumerate(zip(values_b, formats_b)):
            _write_value(worksheet, offset, 9 + local_col, value, fmt)

    # C. Additive monthly schedules.
    section_row = 10
    group_row = 11
    header_row = 12
    data_row = 13
    table_end_col = max(1, 6 * len(scenarios))
    worksheet.merge_range(section_row, 0, section_row, table_end_col, "C. Representative-year monthly schedules - additive", fmts["section"])
    worksheet.write(header_row, 0, "Month", fmts["header"])
    field_headers = ["Positions", "Cumulative", "Working [h]", "Downtime [h]", "Campaign [h]", "DT [%]"]

    for scenario_index, scenario in enumerate(scenarios):
        result = scenario["result"]
        assert isinstance(result, SimulationResult)
        start_col = 1 + scenario_index * group_width
        end_group_col = start_col + group_width - 1
        worksheet.merge_range(
            group_row, start_col, group_row, end_group_col,
            f"{scenario['label']} - representative year {result.start_year}", fmts["subheader"],
        )
        worksheet.write_row(header_row, start_col, field_headers, fmts["header"])

    multiple_years = len({period.year for period in periods}) > 1
    for row_index, period in enumerate(periods, start=data_row):
        worksheet.write(row_index, 0, period.strftime("%b %Y" if multiple_years else "%b"), fmts["text"])
        for scenario_index, scenario in enumerate(scenarios):
            monthly = scenario["monthly"]
            assert isinstance(monthly, pd.DataFrame)
            record = monthly.iloc[row_index - data_row]
            start_col = 1 + scenario_index * group_width
            values = [record[name] for name in field_headers]
            formats = [fmts["integer"], fmts["integer"], fmts["number"], fmts["number"], fmts["number"], fmts["percent"]]
            for local_col, (value, fmt) in enumerate(zip(values, formats)):
                _write_value(worksheet, row_index, start_col + local_col, value, fmt)

    total_row = data_row + len(periods)
    worksheet.write(total_row, 0, "Total", fmts["subheader"])
    for scenario_index, scenario in enumerate(scenarios):
        result = scenario["result"]
        assert isinstance(result, SimulationResult)
        duration = float(result.duration_hours or 0.0)
        start_col = 1 + scenario_index * group_width
        totals = [
            settings.total_positions,
            settings.total_positions,
            float(result.working_hours or 0.0),
            float(result.downtime_hours or 0.0),
            duration,
            float(result.downtime_hours or 0.0) / duration if duration else 0.0,
        ]
        formats = [fmts["integer"], fmts["integer"], fmts["number"], fmts["number"], fmts["number"], fmts["percent"]]
        for local_col, (value, fmt) in enumerate(zip(totals, formats)):
            _write_value(worksheet, total_row, start_col + local_col, value, fmt)

    note_row = total_row + 2
    worksheet.merge_range(
        note_row, 0, note_row + 1, table_end_col,
        "Interpretation: every P50/P75/P90 block is one complete representative hindcast-year simulation. "
        "Monthly working hours and downtime hours are additive and reconcile to the representative duration. "
        "Independent monthly percentile statistics are provided separately in OUT_specific month.",
        fmts["note"],
    )

    # Side-by-side scenario comparison chart. Hidden helper data sits in U:W.
    helper_col = 20
    worksheet.write_row(3, helper_col, ["Scenario", "Workable time [h]", "Downtime [h]"], fmts["header"])
    for row_offset, scenario in enumerate(scenarios, start=4):
        result = scenario["result"]
        assert isinstance(result, SimulationResult)
        worksheet.write(row_offset, helper_col, str(scenario["label"]), fmts["text"])
        worksheet.write_number(row_offset, helper_col + 1, float(result.working_hours or 0.0), fmts["number"])
        worksheet.write_number(row_offset, helper_col + 2, float(result.downtime_hours or 0.0), fmts["number"])
    worksheet.set_column(helper_col, helper_col + 2, None, None, {"hidden": True})

    if scenarios:
        chart = workbook.add_chart({"type": "column", "subtype": "clustered"})
        for col, name, color in [(helper_col + 1, "Workable time [h]", BLUE), (helper_col + 2, "Downtime [h]", ORANGE)]:
            chart.add_series({
                "name": name,
                "categories": ["OUT_overall monthly", 4, helper_col, 3 + len(scenarios), helper_col],
                "values": ["OUT_overall monthly", 4, col, 3 + len(scenarios), col],
                "fill": {"color": color},
                "border": {"color": color, "width": 0.25},
                "data_labels": {"value": True, "position": "outside_end", "num_format": "0.0"},
                "gap": 80,
            })
        chart.set_title({"name": "Representative-year workable time and downtime"})
        _style_chart(chart, x_name="Planning scenario", y_name="Hours")
        chart.set_y_axis({"min": 0, "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9", "width": 0.25}}})
        worksheet.insert_chart(note_row + 3, 9, chart, {"x_scale": 1.35, "y_scale": 1.15})

    worksheet.set_column(0, 0, 13)
    worksheet.set_column(1, table_end_col, 14)
    worksheet.freeze_panes(data_row, 1)


def _write_specific_month_statistics(
    worksheet,
    workbook,
    fmts,
    frame: pd.DataFrame,
    settings: CampaignSettings,
) -> None:
    """Write the previous pointwise monthly output under its clarified name."""
    _sheet_title(
        worksheet,
        "OUT_specific month",
        "Monthly statistical profile. Mean, P50, P75 and P90 are calculated independently for each calendar month across successful simulations. These monthly percentile values are non-additive and must not be summed to reconcile total campaign duration.",
        max(12, len(frame.columns) - 1),
        fmts,
    )
    formats = {column: fmts["number"] for column in frame.columns if column != "Month"}
    _write_dataframe(worksheet, frame, 3, 0, workbook, fmts, format_overrides=formats)
    worksheet.set_column(0, 0, 13)
    worksheet.set_column(1, max(1, len(frame.columns) - 1), 20)
    worksheet.freeze_panes(4, 1)

    if frame.empty:
        return
    labels = ["Mean"] + [f"P{p:g}" for p in settings.percentiles]
    chart_row = 3 + len(frame) + 3

    progress_chart = workbook.add_chart({"type": "line"})
    for label, color in zip(labels, [GREY, BLUE, GREEN, ORANGE]):
        column_name = f"Cumulative positions - {label}"
        if column_name not in frame.columns:
            continue
        col = list(frame.columns).index(column_name)
        progress_chart.add_series({
            "name": label,
            "categories": ["OUT_specific month", 4, 0, 3 + len(frame), 0],
            "values": ["OUT_specific month", 4, col, 3 + len(frame), col],
            "line": {"color": color, "width": 1.5},
            "marker": {"type": "circle", "size": 4, "border": {"color": color}, "fill": {"color": color}},
        })
    progress_chart.set_title({"name": "Monthly statistical cumulative-position profile"})
    _style_chart(progress_chart, x_name="Month", y_name="Cumulative positions")
    progress_chart.set_y_axis({"min": 0, "max": settings.total_positions, "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9", "width": 0.25}}})
    worksheet.insert_chart(chart_row, 0, progress_chart, {"x_scale": 1.35, "y_scale": 1.15})

    p50_label = f"P{settings.percentiles[0]:g}"
    downtime_name = f"Downtime hours - {p50_label}"
    workable_name = f"Workable hours - {p50_label}"
    if downtime_name in frame.columns and workable_name in frame.columns:
        hours_chart = workbook.add_chart({"type": "column", "subtype": "clustered"})
        for column_name, display_name, color in [
            (workable_name, f"Workable hours - {p50_label}", BLUE),
            (downtime_name, f"Downtime hours - {p50_label}", ORANGE),
        ]:
            col = list(frame.columns).index(column_name)
            hours_chart.add_series({
                "name": display_name,
                "categories": ["OUT_specific month", 4, 0, 3 + len(frame), 0],
                "values": ["OUT_specific month", 4, col, 3 + len(frame), col],
                "fill": {"color": color},
                "border": {"color": color, "width": 0.25},
                "data_labels": {"value": True, "position": "outside_end", "num_format": "0.0"},
                "gap": 80,
            })
        hours_chart.set_title({"name": f"{p50_label} monthly statistical hours - side-by-side"})
        _style_chart(hours_chart, x_name="Month", y_name="Hours")
        hours_chart.set_y_axis({"min": 0, "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9", "width": 0.25}}})
        worksheet.insert_chart(chart_row, 9, hours_chart, {"x_scale": 1.30, "y_scale": 1.15})


def _write_detail_summary(worksheet, rows: list[tuple[str, object, str, str]], start_row: int, workbook, fmts) -> tuple[int, int]:
    """Write the detailed summary with controlled three-decimal numeric display."""
    headers = ["Metric", "Value", "Unit", "Basis / note"]
    worksheet.write(start_row, 0, headers[0], fmts["header"])
    worksheet.write(start_row, 1, headers[1], fmts["header"])
    worksheet.write(start_row, 2, headers[2], fmts["header"])
    worksheet.merge_range(start_row, 3, start_row, 5, headers[3], fmts["header"])
    for offset, (metric, value, unit, note) in enumerate(rows, start=1):
        row = start_row + offset
        worksheet.write(row, 0, metric, fmts["text"])
        if value is None or pd.isna(value):
            worksheet.write_blank(row, 1, None, fmts["number"])
        elif isinstance(value, (np.integer, int)) and str(unit).strip().lower() == "year":
            worksheet.write_number(row, 1, int(value), fmts["integer"])
        elif isinstance(value, (np.integer, int, np.floating, float)) and not isinstance(value, bool):
            worksheet.write_number(row, 1, float(value), fmts["number"])
        else:
            worksheet.write(row, 1, str(value), fmts["text"])
        worksheet.write(row, 2, unit, fmts["text"])
        worksheet.merge_range(row, 3, row, 5, note, fmts["text"])
        worksheet.set_row(row, 18)
    return start_row + len(rows), 5


def _location_frames(detailed_result: SimulationResult | None, locations: list[Location]):
    rows: list[dict] = []
    cause_rows: list[dict] = []
    if detailed_result is None:
        return pd.DataFrame(rows), pd.DataFrame(cause_rows)
    for location in locations:
        working = float(detailed_result.working_by_location.get(location.location_id, 0.0))
        downtime = float(detailed_result.downtime_by_location.get(location.location_id, 0.0))
        total = working + downtime
        rows.append({
            "Location ID": location.location_id,
            "Location": location.name,
            "Type": location.location_type,
            "Working [h]": working,
            "Downtime [h]": downtime,
            "Total assessed [h]": total,
            "Downtime [%]": downtime / total if total else 0.0,
        })
        for cause_name, hours in detailed_result.downtime_by_location_cause.get(location.location_id, {}).items():
            cause_rows.append({
                "Location ID": location.location_id,
                "Location": location.name,
                "Downtime cause": cause_name,
                "Downtime [h]": float(hours),
            })
    return pd.DataFrame(rows), pd.DataFrame(cause_rows)


def build_excel_export(
    settings: CampaignSettings,
    locations: list[Location],
    activities: list[Activity],
    bins: list[HsTpBin],
    learning_curve: dict[int, float],
    safe_to_safe_groups: list[SafeToSafeGroup],
    sequence: list[SequenceItem],
    results: list[SimulationResult],
    detailed_result: SimulationResult | None,
    p0_summary: dict,
    app_version: str = "0.10.6",
    weather_filenames: dict[str, str] | None = None,
    analysis: AssessmentAnalytics | None = None,
) -> bytes:
    analysis = analysis or build_analytics(results, settings, p0_summary)
    valid = successful_results(results)
    p0_result = p0_simulation_result(sequence, settings)
    selected_seed = p0_result if is_p0_basis(settings) else detailed_result
    detailed_result, detail_label, detail_target, detail_is_percentile = selected_detailed_result(
        results, settings, selected_seed
    )
    detail_rep = detailed_result
    has_weather_detail = not is_p0_basis(settings)
    detail_sheet_name = f"OUT_{detail_label} DT" if has_weather_detail else None
    detail_matrix_sheet_name = f"OUT_{detail_label} DT detail" if has_weather_detail else None
    sheet_names = [*BASE_SHEET_NAMES]
    if detail_sheet_name:
        sheet_names.append(detail_sheet_name)
    if detail_matrix_sheet_name:
        sheet_names.append(detail_matrix_sheet_name)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="yyyy-mm-dd hh:mm") as writer:
        workbook = writer.book
        fmts = _formats(workbook)

        # Prepare all sheets in their final names before charts are created.
        sheets = {name: workbook.add_worksheet(name) for name in sheet_names}
        writer.sheets.update(sheets)
        workbook.set_properties({
            "title": f"{settings.project_name} Weather Assessment",
            "subject": "Weather assessment results",
            "author": "Weather Assessment",
            "company": "",
            "comments": f"Generated by Weather Assessment v{app_version}",
        })

        # 1 Assessment metadata.
        ws = sheets["Assessment metadata"]
        _sheet_title(ws, "Assessment metadata", "Project, weather-data and assessment basis used for this results workbook.", 1, fmts)
        rep_year = detailed_result.start_year if detailed_result else None
        metadata_rows: list[tuple[str, object, str]] = [
            ("Application", "Weather Assessment", "text"),
            ("Version", app_version, "text"),
            ("Project / scenario", settings.project_name, "text"),
            ("Generated", datetime.now(), "metadata_datetime"),
            ("Planning start", datetime(settings.nominal_year, settings.start_month, settings.start_day), "metadata_date"),
            ("Positions / positions per cycle", f"{settings.total_positions} / {settings.positions_per_cycle}", "text"),
            ("Simulation timestep [h]", float(settings.timestep_hours), "number"),
            ("Detailed results basis", detailed_results_basis_display(settings), "text"),
        ]
        if is_p0_basis(settings):
            metadata_rows.extend([
                ("P0 duration [days]", float(p0_summary.get("duration_hours", 0.0)) / 24.0, "number"),
                ("P0 weather downtime [h]", 0.0, "number"),
                ("P0 timestep adjustment [h]", 0.0, "number"),
            ])
        elif detail_is_percentile:
            metadata_rows.extend([
                (f"{detail_label} representative hindcast year", rep_year, "integer"),
                (f"{detail_label} statistical duration [days]", None if detail_target is None else float(detail_target) / 24.0, "number"),
            ])
        else:
            metadata_rows.extend([
                ("Selected hindcast year", rep_year, "integer"),
                ("Selected hindcast duration [days]", None if detailed_result is None or detailed_result.duration_hours is None else float(detailed_result.duration_hours) / 24.0, "number"),
            ])
        metadata_rows.extend([
            ("Successful simulations", len(valid), "integer"),
            ("Total simulations", len(results), "integer"),
            ("Weather files", "; ".join(f"{key}: {value}" for key, value in sorted((weather_filenames or {}).items())) or "Not recorded", "text"),
            ("Exact P0 [h]", float(p0_summary.get("duration_hours", 0.0)), "number"),
            ("Microsoft Project output", f"Selected-basis cycle-grouped XML ({detail_label}) available on page 15", "text"),
        ])
        ws.write_row(3, 0, ["Field", "Value"], fmts["header"])
        for offset, (field, value, fmt_key) in enumerate(metadata_rows, start=1):
            ws.write(3 + offset, 0, field, fmts["text"])
            _write_value(ws, 3 + offset, 1, value, fmts[fmt_key])
        ws.set_column("A:A", 36)
        ws.set_column("B:B", 78)
        ws.freeze_panes(4, 0)

        # Resolve the actual assessed hindcast range when automatic years were used.
        assessed_years = sorted(int(result.start_year) for result in results)
        resolved_hindcast_start = settings.hindcast_start_year if settings.hindcast_start_year is not None else (assessed_years[0] if assessed_years else None)
        resolved_hindcast_end = settings.hindcast_end_year if settings.hindcast_end_year is not None else (assessed_years[-1] if assessed_years else None)

        # 2 IN_general.
        ws = sheets["IN_general"]
        _sheet_title(ws, "IN_general", "Campaign settings and activity definitions. Boolean values are shown as TRUE/FALSE.", 17, fmts)
        _write_section(ws, 3, "Campaign settings", 4, fmts)
        settings_rows = [
            ("project_name", settings.project_name),
            ("planning_year", settings.nominal_year),
            ("campaign_start_month", settings.start_month),
            ("campaign_start_day", settings.start_day),
            ("positions_per_cycle", settings.positions_per_cycle),
            ("total_positions", settings.total_positions),
            ("percentiles", ", ".join(f"P{p:g}" for p in settings.percentiles)),
            ("simulation_timestep_hours", settings.timestep_hours),
            ("detailed_results_basis", detailed_results_basis_display(settings)),
            ("hindcast_start_year", resolved_hindcast_start),
            ("hindcast_end_year", resolved_hindcast_end),
            ("default_safe_to_safe_method", settings.default_safe_to_safe_method),
        ]
        end_settings, _ = _write_setting_value_table(ws, settings_rows, 4, workbook, fmts)
        ws.set_column("A:B", 16)
        ws.set_column("C:E", 17)
        activities_frame = pd.DataFrame([item.to_dict() for item in activities])
        if not activities_frame.empty:
            activities_frame["no_learning_curve"] = activities_frame["no_learning_curve"].astype(bool)
            activities_frame["milestone"] = activities_frame["milestone"].astype(bool)
            cols = [column for column in activities_frame.columns if column != "safe_to_safe_group"]
            insert_at = cols.index("weather_window_hours") + 1
            cols.insert(insert_at, "safe_to_safe_group")
            activities_frame = activities_frame[cols]
        activity_start = end_settings + 3
        _write_section(ws, activity_start, "Activity definitions", max(17, len(activities_frame.columns) - 1), fmts)
        _write_dataframe(ws, activities_frame, activity_start + 1, 0, workbook, fmts, autofilter=True)
        ws.set_column("A:D", 17)
        ws.set_column("E:E", 42)
        ws.set_column("F:R", 18)
        ws.freeze_panes(activity_start + 2, 5)

        # Inputs 3-7.
        input_specs = [
            ("IN_locations", "Work locations and weather-file mapping.", pd.DataFrame([item.to_dict() for item in locations]), [18, 32, 16, 18, 38, 55]),
            ("IN_safe to safe", "Safe-to-safe group definitions, assessment methods, assessment location and notes.", pd.DataFrame([item.to_dict() for item in safe_to_safe_groups]), [16, 44, 22, 24, 58]),
            ("IN_HsTp curve", "Hs-Tp curve bins used by activity criteria.", pd.DataFrame([item.to_dict() for item in bins]), [22, 18, 18, 20]),
            ("IN_learning curve", "Cycle duration multipliers applied to learning-enabled activities.", pd.DataFrame({"cycle": list(learning_curve), "multiplier": list(learning_curve.values())}), [14, 22]),
            ("IN_sequence", "Generated campaign sequence with learning multipliers, safe-to-safe group definitions and activity criteria.", sequence_dataframe(sequence), None),
        ]
        for sheet_name, subtitle, frame, widths in input_specs:
            ws = sheets[sheet_name]
            end_col = max(4, len(frame.columns) - 1) if len(frame.columns) else 4
            _sheet_title(ws, sheet_name, subtitle, end_col, fmts)
            _write_dataframe(ws, frame, 3, 0, workbook, fmts, autofilter=True)
            if widths:
                for col, width in enumerate(widths):
                    ws.set_column(col, col, width)
            else:
                ws.set_column(0, min(end_col, 7), 17)
                ws.set_column(8, end_col, 20)
                if "description" in frame.columns:
                    idx = list(frame.columns).index("description")
                    ws.set_column(idx, idx, 44)
            ws.freeze_panes(4, 0)

        # 8A OUT_P0 run - always included, exact continuous no-weather programme.
        ws = sheets["OUT_P0 run"]
        _sheet_title(
            ws,
            "OUT_P0 run — Exact deterministic no-weather programme",
            "Learning-adjusted productive durations executed continuously. Weather downtime = 0 and simulation-timestep rounding is not applied to P0.",
            15,
            fmts,
        )
        p0_trace = p0_trace_dataframe(sequence, settings)
        _write_dataframe(ws, p0_trace, 3, 0, workbook, fmts, autofilter=True)
        ws.set_column(0, 1, 20)
        ws.set_column(2, 2, 14)
        ws.set_column(3, 3, 48)
        ws.set_column(4, 15, 18)
        ws.freeze_panes(4, 5)

        # 9 OUT_run.
        ws = sheets["OUT_run"]
        if is_p0_basis(settings):
            run_title = "OUT_run — Detailed P0 (no weather)"
        elif detailed_result is not None:
            if detail_is_percentile:
                run_title = f"OUT_run — Detailed {detail_label} / representative year {detailed_result.start_year}"
            else:
                run_title = f"OUT_run — Detailed hindcast year {detailed_result.start_year}"
        else:
            run_title = f"OUT_run — Detailed {detail_label}"
        run_subtitle = (
            "Exact continuous no-weather trace. Weather downtime = 0; simulation-timestep rounding is not applied."
            if is_p0_basis(settings) else
            "Detailed operational trace for the selected Campaign settings basis. Downtime rows are highlighted in red."
        )
        _sheet_title(ws, run_title, run_subtitle, 36, fmts)
        trace = detailed_result.trace.copy() if detailed_result is not None and detailed_result.trace is not None else pd.DataFrame()
        if not trace.empty:
            preferred = [
                "Timestamp", "End timestamp", "Duration [h]", "Activity", "Location",
                "Wind 10 m", "Wind 100 m", "Hs", "Tp", "Current speed", "Status",
                "Downtime type", "Main factor", "Downtime category", "Assessment basis",
                "Blocking criteria", "Blocking actual", "Blocking limit", "Cycle", "Position",
                "Activity ID", "Remaining activity [h]", "Safe-to-safe group", "Group role",
                "Group method", "Group assessment location", "Window check", "Blocking activity ID",
                "Blocking activity", "Blocking location", "Blocking timestamp",
                "Blocking forecast offset [h]", "Blocking Wind 10 m", "Blocking Wind 100 m",
                "Blocking Hs", "Blocking Tp", "Blocking Current speed",
            ]
            trace = trace[[column for column in preferred if column in trace.columns] + [column for column in trace.columns if column not in preferred]]
        _write_dataframe(ws, trace, 3, 0, workbook, fmts, autofilter=True)
        ws.set_column(0, 2, 20)
        ws.set_column(3, 3, 48)
        ws.set_column(4, 4, 18)
        ws.set_column(5, 36, 18)
        if not trace.empty and "Status" in trace.columns:
            status_col = list(trace.columns).index("Status")
            status_letter = xl_col_to_name(status_col)
            last_row = 3 + len(trace)
            last_col = len(trace.columns) - 1
            ws.conditional_format(4, 0, last_row, last_col, {"type": "formula", "criteria": f'=${status_letter}5="Downtime"', "format": fmts["downtime"]})
            ws.conditional_format(4, 0, last_row, last_col, {"type": "formula", "criteria": f'=${status_letter}5="Working"', "format": fmts["working"]})
        ws.freeze_panes(4, 5)

        # Common result frames.
        campaign_summary = analysis.table("campaign")
        position_summary = analysis.table("positions")
        annual = analysis.table("annual")
        milestone = analysis.table("milestones")
        specific_month_statistics = _specific_month_statistics(results, settings, analysis.table("planning_monthly"))
        representative_periods, representative_monthly = _representative_monthly_scenarios(results, settings)
        planning_summary = analysis.table("planning_summary")
        planning_reps = analysis.table("representatives")
        planning_positions = analysis.table("planning_positions")
        planning_coverage = analysis.table("coverage")
        if not planning_coverage.empty:
            planning_coverage["Included in planning statistics"] = planning_coverage["Included in planning statistics"].map(lambda value: "TRUE" if bool(value) else "FALSE")
        planning_dt_summary, planning_activity, representative_map = _scenario_downtime_frames(results, settings)

        # OUT_years coverage is created directly after IN_sequence in tab order.
        ws = sheets["OUT_years coverage"]
        _sheet_title(ws, "OUT_years coverage", "Hindcast simulations included in or excluded from planning statistics.", max(4, len(planning_coverage.columns) - 1), fmts)
        _write_dataframe(ws, planning_coverage, 3, 0, workbook, fmts, autofilter=True)
        ws.set_column("A:A", 23)
        ws.set_column("B:B", 30)
        ws.set_column("C:C", 80)
        ws.freeze_panes(4, 0)

        # 10 OUT_overall.
        ws = sheets["OUT_overall"]
        _sheet_title(ws, "OUT_overall", "Overall campaign duration and position-completion profiles across the hindcast simulations.", 15, fmts)
        _write_section(ws, 3, "Campaign duration summary", 6, fmts)
        _write_dataframe(ws, campaign_summary, 4, 0, workbook, fmts)
        position_start = 4 + len(campaign_summary) + 3
        _write_section(ws, position_start, "Position completion profile", max(6, len(position_summary.columns) - 1), fmts)
        _write_dataframe(ws, position_summary, position_start + 1, 0, workbook, fmts)
        ws.set_column("A:A", 24)
        ws.set_column("B:G", 19)
        ws.freeze_panes(position_start + 2, 1)
        if not campaign_summary.empty:
            chart = workbook.add_chart({"type": "column"})
            chart.add_series({
                "name": "Duration [days]",
                "categories": ["OUT_overall", 5, 0, 4 + len(campaign_summary), 0],
                "values": ["OUT_overall", 5, 2, 4 + len(campaign_summary), 2],
                "fill": {"color": BLUE}, "border": {"color": BLUE, "width": 0.25},
            })
            chart.set_title({"name": "Campaign duration by scenario"})
            _style_chart(chart, x_name="Scenario", y_name="Duration [days]", legend="none")
            ws.insert_chart("I4", chart, {"x_scale": 1.15, "y_scale": 1.05})
        if not position_summary.empty:
            chart = workbook.add_chart({"type": "line"})
            colors = ["#5B9BD5", "#70AD47", "#4472C4", "#A5A5A5", "#ED7D31", "#C00000"]
            for index, column_name in enumerate(position_summary.columns[1:]):
                chart.add_series({
                    "name": column_name,
                    "categories": ["OUT_overall", position_start + 2, 0, position_start + 1 + len(position_summary), 0],
                    "values": ["OUT_overall", position_start + 2, index + 1, position_start + 1 + len(position_summary), index + 1],
                    "line": {"color": colors[index % len(colors)], "width": 0.25},
                })
            chart.set_title({"name": "Position completion profile"})
            _style_chart(chart, x_name="Position", y_name="Elapsed time [days]")
            ws.insert_chart("I22", chart, {"x_scale": 1.15, "y_scale": 1.10})

        # 10 OUT_overall MS transposed.
        ws = sheets["OUT_overall MS"]
        _sheet_title(ws, "OUT_overall MS", "Milestone completion dates by position and hindcast year. Blank cells indicate incomplete positions.", max(10, len(results)), fmts)
        years = [result.start_year for result in results]
        transposed = pd.DataFrame({"Position": list(range(1, settings.total_positions + 1))})
        by_year = {result.start_year: result for result in results}
        for year in years:
            result = by_year[year]
            transposed[str(year)] = [result.position_completion_dates.get(position) for position in range(1, settings.total_positions + 1)]
        date_overrides = {str(year): fmts["datetime_small"] for year in years}
        _write_dataframe(ws, transposed, 3, 0, workbook, fmts, format_overrides=date_overrides)
        ws.set_column("A:A", 14)
        ws.set_column(1, max(1, len(years)), 18)
        ws.set_row(3, 20)
        for row in range(4, 4 + len(transposed)):
            ws.set_row(row, 17)
        ws.freeze_panes(4, 1)

        # 12 OUT_overall monthly — additive representative-year schedules.
        ws = sheets["OUT_overall monthly"]
        _write_overall_monthly(
            ws, workbook, fmts, representative_periods, representative_monthly, settings,
            float(p0_summary.get("duration_hours", 0.0)),
        )

        # 13 OUT_specific month — independent pointwise monthly statistics.
        ws = sheets["OUT_specific month"]
        _write_specific_month_statistics(ws, workbook, fmts, specific_month_statistics, settings)

        # 12 OUT_overall annual.
        ws = sheets["OUT_overall annual"]
        _sheet_title(ws, "OUT_overall annual", "One row per hindcast start year, including success, duration, P0 reconciliation and data coverage.", max(12, len(annual.columns) - 1), fmts)
        _write_dataframe(ws, annual, 3, 0, workbook, fmts, autofilter=True)
        ws.set_column(0, len(annual.columns) - 1, 19)
        ws.freeze_panes(4, 1)
        if not annual.empty and "Duration [days]" in annual.columns:
            duration_col = list(annual.columns).index("Duration [days]")
            chart = workbook.add_chart({"type": "column"})
            chart.add_series({
                "name": "Duration [days]",
                "categories": ["OUT_overall annual", 4, 0, 3 + len(annual), 0],
                "values": ["OUT_overall annual", 4, duration_col, 3 + len(annual), duration_col],
                "fill": {"color": BLUE}, "border": {"color": BLUE, "width": 0.25},
            })
            chart.set_title({"name": "Campaign duration by hindcast year"})
            _style_chart(chart, x_name="Hindcast start year", y_name="Duration [days]", legend="none")
            ws.insert_chart("O4", chart, {"x_scale": 1.35, "y_scale": 1.20})

        # 13 OUT_planning summary.
        ws = sheets["OUT_planning summary"]
        _sheet_title(ws, "OUT_planning summary", f"Planning scenarios mapped to the {settings.nominal_year} campaign calendar.", max(12, len(planning_summary.columns) - 1), fmts)
        _write_section(ws, 3, "Planning scenario summary", 7, fmts)
        _write_last_column_spanned(ws, planning_summary, 4, workbook, fmts, span=3)
        rep_start = 4 + len(planning_summary) + 3
        _write_section(ws, rep_start, "Representative hindcast years", max(5, len(planning_reps.columns) - 1), fmts)
        _write_dataframe(ws, planning_reps, rep_start + 1, 0, workbook, fmts)
        ws.set_column(0, 0, 28)
        ws.set_column(1, 4, 21)
        ws.set_column(5, 7, 18)
        ws.freeze_panes(4, 1)
        percentile_rows = planning_summary[planning_summary["Scenario"].astype(str).str.fullmatch(r"P\d+(?:\.\d+)?")] if not planning_summary.empty else pd.DataFrame()
        if not percentile_rows.empty:
            chart_source_row = rep_start + len(planning_reps) + 4
            _write_dataframe(ws, percentile_rows[["Scenario", "Duration [days]"]], chart_source_row, 10, workbook, fmts)
            chart = workbook.add_chart({"type": "column"})
            chart.add_series({
                "name": "Duration [days]",
                "categories": ["OUT_planning summary", chart_source_row + 1, 10, chart_source_row + len(percentile_rows), 10],
                "values": ["OUT_planning summary", chart_source_row + 1, 11, chart_source_row + len(percentile_rows), 11],
                "fill": {"color": BLUE}, "border": {"color": BLUE, "width": 0.25},
            })
            chart.set_title({"name": f"{settings.nominal_year} planning duration"})
            _style_chart(chart, x_name="Scenario", y_name="Duration [days]", legend="none")
            chart_row = rep_start + len(planning_reps) + 4
            ws.insert_chart(chart_row, 0, chart, {"x_scale": 1.25, "y_scale": 1.10})
            ws.set_column("K:L", None, None, {"hidden": True})

        # 14 OUT_planning MS.
        ws = sheets["OUT_planning MS"]
        _sheet_title(ws, "OUT_planning MS", "Planning milestone dates and elapsed durations by position for P0, best, P50, P75, P90 and worst profiles.", max(12, len(planning_positions.columns) - 1), fmts)
        _write_dataframe(ws, planning_positions, 3, 0, workbook, fmts)
        ws.set_column(0, 0, 12)
        ws.set_column(1, len(planning_positions.columns) - 1, 21)
        ws.freeze_panes(4, 1)

        # 16 OUT_overall DT.
        ws = sheets["OUT_overall DT"]
        _sheet_title(ws, "OUT_overall DT", f"Representative P50, P75 and P90 time summary with clustered workable-time and downtime columns, plus selected {detail_label} downtime by activity.", 16, fmts)
        _write_section(ws, 3, "Representative scenario summary", 7, fmts)
        _write_dataframe(ws, planning_dt_summary, 4, 0, workbook, fmts)
        activity_start = 4 + len(planning_dt_summary) + 3
        _write_section(ws, activity_start, "Activity downtime by planning scenario", 5, fmts)
        _write_dataframe(ws, planning_activity, activity_start + 1, 0, workbook, fmts, autofilter=True)
        ws.set_column(0, 0, 20)
        ws.set_column(1, 1, 24)
        ws.set_column(2, 2, 50)
        ws.set_column(3, 7, 20)
        ws.freeze_panes(activity_start + 2, 2)
        if not planning_dt_summary.empty:
            helper_row = 3
            helper_col = 23
            helper = planning_dt_summary[["Planning scenario", "Workable time [hours]", "Downtime [hours]"]]
            _write_dataframe(ws, helper, helper_row, helper_col, workbook, fmts)
            chart = workbook.add_chart({"type": "column"})
            for idx, (name, color) in enumerate([("Workable time [h]", BLUE), ("Downtime [h]", ORANGE)], start=1):
                chart.add_series({
                    "name": name,
                    "categories": ["OUT_overall DT", helper_row + 1, helper_col, helper_row + len(helper), helper_col],
                    "values": ["OUT_overall DT", helper_row + 1, helper_col + idx, helper_row + len(helper), helper_col + idx],
                    "fill": {"color": color}, "border": {"color": color, "width": 0.25},
                })
            chart.set_title({"name": "Workable time and downtime by planning scenario"})
            _style_chart(chart, x_name="Planning scenario", y_name="Hours")
            chart.show_hidden_data()
            chart_start_row = activity_start + len(planning_activity) + 5
            ws.insert_chart(chart_start_row, 0, chart, {"x_scale": 1.25, "y_scale": 1.10})
        if detail_is_percentile:
            selected_activity = planning_activity[planning_activity["Planning scenario"] == detail_label] if not planning_activity.empty else pd.DataFrame()
        else:
            selected_activity = downtime_breakdown_dataframe(detailed_result)[1] if detailed_result is not None else pd.DataFrame()
            if not selected_activity.empty:
                selected_activity = selected_activity.copy()
        if not selected_activity.empty:
            top = selected_activity.sort_values("Downtime hours", ascending=False).head(9).copy()
            helper_row2 = 22
            helper_col2 = 23
            _write_dataframe(ws, top[["Activity", "Downtime hours"]].sort_values("Downtime hours"), helper_row2, helper_col2, workbook, fmts)
            chart = workbook.add_chart({"type": "bar"})
            chart.add_series({
                "name": "Downtime [h]",
                "categories": ["OUT_overall DT", helper_row2 + 1, helper_col2, helper_row2 + len(top), helper_col2],
                "values": ["OUT_overall DT", helper_row2 + 1, helper_col2 + 1, helper_row2 + len(top), helper_col2 + 1],
                "fill": {"color": ORANGE}, "border": {"color": ORANGE, "width": 0.25},
            })
            chart.set_title({"name": f"{detail_label} downtime by activity"})
            _style_chart(chart, x_name="Downtime [h]", y_name="Activity", legend="none")
            chart.show_hidden_data()
            chart_start_row = activity_start + len(planning_activity) + 5
            ws.insert_chart(chart_start_row, 9, chart, {"x_scale": 1.25, "y_scale": 1.35})
        ws.set_column("X:Z", None, None, {"hidden": True})

        # 18 Selected-detail downtime sheets (weather scenarios only).
        if has_weather_detail and detail_sheet_name and detail_matrix_sheet_name:
            ws = sheets[detail_sheet_name]
            detail_year = detailed_result.start_year if detailed_result else None
            if detail_is_percentile:
                detail_title = f"{detail_sheet_name} — representative year {detail_year or '-'}"
                detail_subtitle = f"{detail_label} representative-year duration, downtime detail, activity ranking, safe-to-safe waiting and location breakdown."
            else:
                detail_title = f"{detail_sheet_name} — selected hindcast year {detail_year or '-'}"
                detail_subtitle = f"Selected hindcast-year duration, downtime detail, activity ranking, safe-to-safe waiting and location breakdown."
            _sheet_title(ws, detail_title, detail_subtitle, 6, fmts)
            detail_summary_rows = []
            if detailed_result is not None:
                if detail_is_percentile:
                    detail_summary_rows = [
                        ("Planning scenario", detail_label, "", "Statistical planning percentile"),
                        (f"{detail_label} representative hindcast year", detailed_result.start_year, "year", f"Historical simulation closest to the {detail_label} duration"),
                        (f"Statistical {detail_label} duration", None if detail_target is None else detail_target / 24.0, "days", "Percentile result across completed scenarios"),
                    ]
                    summary_title = f"{detail_label} representative-year duration summary"
                else:
                    detail_summary_rows = [
                        ("Selected hindcast year", detailed_result.start_year, "year", "Historical year selected in Campaign settings"),
                    ]
                    summary_title = f"Hindcast year {detailed_result.start_year} duration summary"
                detail_summary_rows.extend([
                    ("Selected total duration", float(detailed_result.duration_hours or 0.0), "hours", "Workable time plus downtime"),
                    ("Selected total duration", float(detailed_result.duration_hours or 0.0) / 24.0, "days", "Complete selected schedule duration"),
                    ("Workable time", float(detailed_result.working_hours or 0.0), "hours", "Simulated working time"),
                    ("Downtime", float(detailed_result.downtime_hours or 0.0), "hours", "Weather and operational waiting"),
                    ("Downtime", 100.0 * float(detailed_result.downtime_hours or 0.0) / float(detailed_result.duration_hours or 1.0), "% total duration", "Selected-year downtime percentage"),
                    ("Timestep adjustment", float(detailed_result.timestep_adjustment_hours or 0.0), "hours", "Working-time grid adjustment above exact P0"),
                ])
            else:
                summary_title = f"{detail_label} duration summary"
            _write_section(ws, 3, summary_title, 5, fmts)
            _write_detail_summary(ws, detail_summary_rows, 4, workbook, fmts)
            cause, activity = downtime_breakdown_dataframe(detailed_result)
            cause_start = 4 + len(detail_summary_rows) + 3
            _write_section(ws, cause_start, "Detailed downtime causes", 3, fmts)
            _write_dataframe(ws, cause, cause_start + 1, 0, workbook, fmts)
            activity_start = cause_start + len(cause) + 4
            _write_section(ws, activity_start, "Activity downtime ranking", 4, fmts)
            if not activity.empty:
                activity = activity.copy()
                activity.insert(0, "Rank", range(1, len(activity) + 1))
                activity["Cumulative % of total downtime"] = activity["% of total downtime"].cumsum()
            _write_dataframe(ws, activity, activity_start + 1, 0, workbook, fmts)
            group_start = activity_start + len(activity) + 4
            _write_section(ws, group_start, "Safe-to-safe group waiting", 2, fmts)
            group_waiting = pd.DataFrame([
                {"Safe-to-safe group": group_id, "Waiting [h]": float(hours)}
                for group_id, hours in sorted((detailed_result.downtime_by_group if detailed_result else {}).items())
            ])
            _write_dataframe(ws, group_waiting, group_start + 1, 0, workbook, fmts)
            location_frame, location_causes = _location_frames(detailed_result, locations)
            location_start = group_start + len(group_waiting) + 4
            _write_section(ws, location_start, "Location summary", 6, fmts)
            _write_dataframe(ws, location_frame, location_start + 1, 0, workbook, fmts)
            location_cause_start = location_start + len(location_frame) + 4
            _write_section(ws, location_cause_start, "Downtime causes by location", 3, fmts)
            _write_dataframe(ws, location_causes, location_cause_start + 1, 0, workbook, fmts)
            ws.set_column("A:A", 42)
            ws.set_column("B:C", 18)
            ws.set_column("D:F", 18)
            ws.set_column("G:G", 24)
            ws.freeze_panes(4, 0)

            # 19 Selected-detail Activity × Cause matrix.
            ws = sheets[detail_matrix_sheet_name]
            cause_mech, activity_detail, activity_matrix = downtime_detail_frames(detailed_result)
            _sheet_title(
                ws,
                f"{detail_matrix_sheet_name} — Activity × Cause matrix",
                "Cause = actual weather criterion / combination. Mechanism = Direct exceedance or Window pre-check. Every downtime hour is counted once.",
                max(8, len(activity_matrix.columns) - 1 if not activity_matrix.empty else 8),
                fmts,
            )
            _write_section(ws, 3, "A. Cause / mechanism reconciliation", 5, fmts)
            _write_dataframe(ws, cause_mech, 4, 0, workbook, fmts, autofilter=True)
            activity_summary_start = 4 + len(cause_mech) + 4
            _write_section(ws, activity_summary_start, "B. Activity downtime summary", 6, fmts)
            _write_dataframe(ws, activity_detail, activity_summary_start + 1, 0, workbook, fmts, autofilter=True)
            matrix_start = activity_summary_start + len(activity_detail) + 5
            _write_section(ws, matrix_start, "C. Additive Activity × Cause matrix", max(8, len(activity_matrix.columns) - 1 if not activity_matrix.empty else 8), fmts)
            _write_dataframe(ws, activity_matrix, matrix_start + 1, 0, workbook, fmts, autofilter=True)
            ws.set_column("A:A", 44)
            ws.set_column("B:Z", 18)
            ws.freeze_panes(activity_summary_start + 2, 2)

        # General print setup and consistent page styling.
        for name in sheet_names:
            ws = sheets[name]
            ws.set_landscape()
            ws.set_paper(9)  # A4
            ws.fit_to_pages(1, 0)
            ws.set_margins(0.25, 0.25, 0.45, 0.45)
            ws.set_header(f'&L&"Calibri,Bold"{settings.project_name}&RWeather Assessment v{app_version}')
            ws.set_footer('&LGenerated by Weather Assessment&CPage &P of &N&RConfidential review output')

    return output.getvalue()
