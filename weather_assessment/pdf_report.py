from __future__ import annotations

from datetime import datetime
from io import BytesIO

from .policies import engineering_percentile
from .analytics import AssessmentAnalytics, build_analytics

import numpy as np
import pandas as pd
from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Activity, CampaignSettings, Location, SafeToSafeGroup, SequenceItem, SimulationResult
from .planning import detailed_results_basis_display, selected_detailed_result, is_p0_basis, representative_result
from .sequence import p0_simulation_result
from .statistics import downtime_breakdown_dataframe, downtime_detail_frames, successful_results

NAVY = colors.HexColor("#1F4E78")
BLUE = colors.HexColor("#4472C4")
LIGHT_BLUE = colors.HexColor("#D9EAF7")
GREEN = colors.HexColor("#70AD47")
ORANGE = colors.HexColor("#ED7D31")
RED = colors.HexColor("#C00000")
GREY = colors.HexColor("#A5A5A5")
DARK = colors.HexColor("#1F1F1F")
BORDER = colors.HexColor("#D0DCE6")
PALE = colors.HexColor("#F5F8FB")


def _ascii_text(value) -> str:
    return str(value).replace("–", "-").replace("—", "-").replace("•", "-")


def _fmt(value, suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value).strftime("%d %b %Y")
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}{suffix}"
    try:
        return f"{float(value):,.3f}{suffix}"
    except (TypeError, ValueError):
        return _ascii_text(value)


def _styles():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(name="TitleMain", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=NAVY, spaceAfter=4))
    base.add(ParagraphStyle(name="TitleSub", parent=base["Normal"], fontName="Helvetica", fontSize=10, leading=13, textColor=colors.HexColor("#526579")))
    base.add(ParagraphStyle(name="Section", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, backColor=colors.HexColor("#EAF2F8"), borderPadding=(4, 6, 4, 6), spaceAfter=6))
    base.add(ParagraphStyle(name="Body", parent=base["Normal"], fontName="Helvetica", fontSize=7.8, leading=10.5, textColor=DARK))
    base.add(ParagraphStyle(name="Small", parent=base["Normal"], fontName="Helvetica", fontSize=6.5, leading=8.5, textColor=DARK))
    base.add(ParagraphStyle(name="Note", parent=base["Normal"], fontName="Helvetica", fontSize=6.5, leading=8.5, textColor=colors.HexColor("#526579"), backColor=PALE, borderPadding=5))
    base.add(ParagraphStyle(name="MetricLabel", parent=base["Normal"], fontName="Helvetica", fontSize=6.5, leading=8, alignment=TA_CENTER, textColor=colors.HexColor("#526579")))
    base.add(ParagraphStyle(name="MetricValue", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=13, alignment=TA_CENTER, textColor=NAVY))
    base.add(ParagraphStyle(name="LeftSmall", parent=base["Normal"], fontName="Helvetica", fontSize=6.7, leading=8.5, alignment=TA_LEFT, textColor=DARK))
    return base


def _paragraph(text: str, style) -> Paragraph:
    return Paragraph(_ascii_text(text), style)


def _table(data, widths, *, font_size=6.7, header=True, row_heights=None, align="LEFT") -> Table:
    converted = []
    for row_index, row in enumerate(data):
        converted.append([
            value if isinstance(value, Paragraph) else Paragraph(_ascii_text(value), ParagraphStyle(
                name=f"Cell{row_index}", fontName="Helvetica-Bold" if header and row_index == 0 else "Helvetica",
                fontSize=font_size, leading=font_size + 2, textColor=colors.white if header and row_index == 0 else DARK,
                alignment=TA_LEFT,
            ))
            for value in row
        ])
    table = Table(converted, colWidths=widths, rowHeights=row_heights, repeatRows=1 if header else 0, hAlign=align)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY)]
    for row in range(1 if header else 0, len(data)):
        style.append(("BACKGROUND", (0, row), (-1, row), colors.white if row % 2 else PALE))
    table.setStyle(TableStyle(style))
    return table


def _metric_card(label: str, value: str, note: str = "", *, accent=BLUE, width=38 * mm) -> Table:
    data = [[_paragraph(label, _styles()["MetricLabel"])], [_paragraph(value, _styles()["MetricValue"])] ]
    if note:
        data.append([_paragraph(note, _styles()["MetricLabel"])])
    card = Table(data, colWidths=[width], rowHeights=[8 * mm, 10 * mm] + ([7 * mm] if note else []))
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("LINEABOVE", (0, 0), (-1, 0), 2.2, accent),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return card


def _vertical_bar_chart(labels: list[str], series: list[list[float]], names: list[str], palette: list, *, title: str, width=126 * mm, height=67 * mm) -> Drawing:
    drawing = Drawing(width, height)
    if not labels or not series or not any(series):
        drawing.add(String(width / 2, height / 2, "No completed weather scenarios", fontSize=9, textAnchor="middle"))
        return drawing
    chart = VerticalBarChart()
    chart.x = 12 * mm
    chart.y = 13 * mm
    chart.width = width - 19 * mm
    chart.height = height - 25 * mm
    chart.data = series
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 0
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 6
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = "%.1f"
    chart.groupSpacing = 8
    chart.barSpacing = 2
    for index, color in enumerate(palette):
        chart.bars[index].fillColor = color
        chart.bars[index].strokeColor = color
        chart.bars[index].strokeWidth = 0.25
    chart.strokeColor = colors.transparent
    drawing.add(chart)
    drawing.add(String(width / 2, height - 7 * mm, title, fontName="Helvetica-Bold", fontSize=8, fillColor=NAVY, textAnchor="middle"))
    # Legend.
    x = 15 * mm
    for name, color in zip(names, palette):
        drawing.add(String(x + 4 * mm, 4 * mm, name, fontName="Helvetica", fontSize=5.8, fillColor=DARK))
        from reportlab.graphics.shapes import Rect
        drawing.add(Rect(x, 3.2 * mm, 3 * mm, 2.2 * mm, fillColor=color, strokeColor=color))
        x += max(28 * mm, len(name) * 2.3 * mm)
    return drawing


def _line_chart(x_values: list[float], series: list[list[float]], names: list[str], palette: list, *, title: str, width=126 * mm, height=67 * mm) -> Drawing:
    drawing = Drawing(width, height)
    if not x_values or not series or not any(series):
        drawing.add(String(width / 2, height / 2, "No completed weather scenarios", fontSize=9, textAnchor="middle"))
        return drawing
    chart = LinePlot()
    chart.x = 15 * mm
    chart.y = 13 * mm
    chart.width = width - 22 * mm
    chart.height = height - 25 * mm
    chart.data = [list(zip(x_values, values)) for values in series]
    chart.xValueAxis.labels.fontName = "Helvetica"
    chart.xValueAxis.labels.fontSize = 6
    chart.xValueAxis.labelTextFormat = "%g"
    chart.yValueAxis.labels.fontName = "Helvetica"
    chart.yValueAxis.labels.fontSize = 6
    chart.yValueAxis.labelTextFormat = "%.1f"
    for index, color in enumerate(palette):
        chart.lines[index].strokeColor = color
        chart.lines[index].strokeWidth = 0.25
    drawing.add(chart)
    drawing.add(String(width / 2, height - 7 * mm, title, fontName="Helvetica-Bold", fontSize=8, fillColor=NAVY, textAnchor="middle"))
    x = 14 * mm
    for name, color in zip(names, palette):
        drawing.add(String(x + 5 * mm, 4 * mm, name, fontName="Helvetica", fontSize=5.8, fillColor=DARK))
        from reportlab.graphics.shapes import Line
        drawing.add(Line(x, 4.2 * mm, x + 4 * mm, 4.2 * mm, strokeColor=color, strokeWidth=0.25))
        x += max(24 * mm, len(name) * 2.2 * mm)
    return drawing


def _horizontal_bar_chart(labels: list[str], values: list[float], *, title: str, color=ORANGE, width=126 * mm, height=67 * mm) -> Drawing:
    drawing = Drawing(width, height)
    chart = HorizontalBarChart()
    chart.x = 47 * mm
    chart.y = 10 * mm
    chart.width = width - 55 * mm
    chart.height = height - 22 * mm
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 5.5
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 6
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = "%.1f"
    chart.bars[0].fillColor = color
    chart.bars[0].strokeColor = color
    chart.bars[0].strokeWidth = 0.25
    chart.strokeColor = colors.transparent
    drawing.add(chart)
    drawing.add(String(width / 2, height - 7 * mm, title, fontName="Helvetica-Bold", fontSize=8, fillColor=NAVY, textAnchor="middle"))
    return drawing


def _horizontal_stacked_bar_chart(labels: list[str], series: list[list[float]], names: list[str], palette: list, *, title: str, width=260 * mm, height=82 * mm) -> Drawing:
    drawing = Drawing(width, height)
    chart = HorizontalBarChart()
    chart.x = 58 * mm
    chart.y = 13 * mm
    chart.width = width - 68 * mm
    chart.height = height - 27 * mm
    chart.data = series
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 5.2
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 6
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = "%.0f"
    chart.categoryAxis.style = "stacked"
    chart.groupSpacing = 4
    for index, color in enumerate(palette[:len(series)]):
        chart.bars[index].fillColor = color
        chart.bars[index].strokeColor = color
        chart.bars[index].strokeWidth = 0.2
    drawing.add(chart)
    drawing.add(String(width / 2, height - 7 * mm, title, fontName="Helvetica-Bold", fontSize=8, fillColor=NAVY, textAnchor="middle"))
    x = 10 * mm
    from reportlab.graphics.shapes import Rect
    for name, color in zip(names, palette):
        drawing.add(Rect(x, 3.2 * mm, 3 * mm, 2.2 * mm, fillColor=color, strokeColor=color))
        drawing.add(String(x + 4 * mm, 4 * mm, name, fontName="Helvetica", fontSize=5.5, fillColor=DARK))
        x += max(30 * mm, len(name) * 1.8 * mm)
    return drawing


def _page_pair(left, right, *, widths=(132 * mm, 132 * mm)) -> Table:
    table = Table([[left, right]], colWidths=list(widths), hAlign="CENTER")
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return table


def build_pdf_report(
    settings: CampaignSettings,
    locations: list[Location],
    activities: list[Activity],
    safe_to_safe_groups: list[SafeToSafeGroup],
    sequence: list[SequenceItem],
    results: list[SimulationResult],
    detailed_result: SimulationResult | None,
    p0_summary: dict,
    app_version: str,
    weather_filenames: dict[str, str] | None = None,
    selected_percentile: float | None = None,
    analysis: AssessmentAnalytics | None = None,
) -> bytes:
    analysis = analysis or build_analytics(results, settings, p0_summary)
    styles = _styles()
    # The detailed PDF basis follows Campaign settings. ``selected_percentile`` is
    # retained only for backward API compatibility and is intentionally ignored.
    valid = successful_results(results)
    p0_result = p0_simulation_result(sequence, settings)
    selected_seed = p0_result if is_p0_basis(settings) else detailed_result
    selected, selected_label, target_duration, selected_is_percentile = selected_detailed_result(
        results, settings, selected_seed
    )

    annual = analysis.table("annual")
    positions = analysis.table("positions")
    planning_monthly = analysis.table("planning_monthly")
    planning_positions = analysis.table("planning_positions")
    reps = analysis.table("representatives")
    coverage = analysis.table("coverage")
    cause, activity = downtime_breakdown_dataframe(selected)

    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=15 * mm,
        bottomMargin=14 * mm,
        title=f"{settings.project_name} Weather Assessment Executive Report",
        author="Weather Assessment",
    )

    def footer(canvas, document):
        canvas.saveState()
        width, height = landscape(A4)
        canvas.setStrokeColor(colors.HexColor("#D7E0E9"))
        canvas.line(14 * mm, 10 * mm, width - 14 * mm, 10 * mm)
        canvas.setFont("Helvetica", 6.2)
        canvas.setFillColor(colors.HexColor("#6A7C8E"))
        canvas.drawString(14 * mm, 6.2 * mm, "Weather Assessment Executive Report")
        canvas.drawRightString(width - 14 * mm, 6.2 * mm, f"Page {document.page}")
        canvas.restoreState()

    story = []

    # Cover.
    story.append(Spacer(1, 8 * mm))
    story.append(_paragraph("Weather Assessment Executive Report", styles["TitleMain"]))
    story.append(_paragraph(settings.project_name, styles["TitleSub"]))
    story.append(Spacer(1, 12 * mm))
    metrics = [
        _metric_card("Planning year", str(settings.nominal_year), accent=BLUE),
        _metric_card("Total positions", str(settings.total_positions), accent=GREEN),
        _metric_card("Completed scenarios", f"{len(valid)}/{len(results)}", accent=GREY),
        _metric_card(f"Selected {selected_label}", _fmt(None if selected is None else float(selected.duration_hours or 0.0) / 24.0, " days"), accent=BLUE),
        _metric_card("Exact P0", _fmt(float(p0_summary.get("duration_hours", 0.0)) / 24.0, " days"), accent=GREEN),
    ]
    story.append(Table([metrics], colWidths=[50 * mm] * 5, hAlign="LEFT", style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3)])))
    story.append(Spacer(1, 12 * mm))
    metadata = [
        ["Report basis", "Value"],
        ["Project / scenario", settings.project_name],
        ["Planning start", f"{settings.nominal_year}-{settings.start_month:02d}-{settings.start_day:02d}"],
        ["Simulation timestep", _fmt(settings.timestep_hours, " h")],
        ["Detailed results basis", detailed_results_basis_display(settings)],
        ["Selected detail hindcast year", "Not applicable - P0" if is_p0_basis(settings) else (selected.start_year if selected else "-")],
        ["Weather datasets", "; ".join(f"{key}: {value}" for key, value in sorted((weather_filenames or {}).items())) or "Not recorded"],
        ["Document status", "Review output"],
    ]
    story.append(_table(metadata, [55 * mm, 205 * mm], font_size=7.2))
    story.append(Spacer(1, 8 * mm))
    story.append(_paragraph(f"This report follows the detailed-results basis selected in Campaign settings ({detailed_results_basis_display(settings)}). A cycle-grouped Microsoft Project XML schedule for the same selected basis is available separately from the app export page.", styles["Note"]))
    story.append(PageBreak())

    # 1 Executive summary.
    story.append(_paragraph("1. Executive summary", styles["Section"]))
    durations = np.asarray([float(item.duration_hours) for item in valid], dtype=float) if valid else np.asarray([])
    best = min(valid, key=lambda item: float(item.duration_hours)) if valid else None
    worst = max(valid, key=lambda item: float(item.duration_hours)) if valid else None
    cards = [
        _metric_card("P0", _fmt(float(p0_summary.get("duration_hours", 0.0)) / 24.0, " d"), accent=GREEN),
    ]
    for percentile, accent in zip(settings.percentiles, [BLUE, GREEN, ORANGE]):
        duration = engineering_percentile(durations, percentile) / 24.0 if len(durations) else None
        cards.append(_metric_card(f"P{percentile:g}", _fmt(duration, " d"), accent=accent))
    cards += [
        _metric_card("Best", _fmt(None if best is None else float(best.duration_hours) / 24.0, " d"), f"Year {best.start_year}" if best else "", accent=GREEN),
        _metric_card("Worst", _fmt(None if worst is None else float(worst.duration_hours) / 24.0, " d"), f"Year {worst.start_year}" if worst else "", accent=RED),
    ]
    story.append(Table([cards], colWidths=[42 * mm] * 6, hAlign="LEFT", style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2)])))
    story.append(Spacer(1, 6 * mm))
    bullets = [
        f"The assessment includes {len(valid)} completed hindcast scenarios from {len(results)} simulated start years.",
        (f"The selected detailed output is deterministic P0 ({_fmt(float(p0_summary.get('duration_hours', 0.0)) / 24.0, ' d')}) with zero weather downtime." if is_p0_basis(settings) else f"The selected detailed output is {selected_label} and uses hindcast year {selected.start_year if selected else '-'}."),
        "P50, P75 and P90 durations are statistical percentile results across completed hindcast simulations.",
        ("P0 is a continuous no-weather programme and has no representative hindcast year." if is_p0_basis(settings) else ("The representative hindcast year is the completed simulation nearest to the selected statistical percentile duration." if selected_is_percentile else "The detailed hindcast year is the specific historical year selected in Campaign settings.")),
    ]
    story.append(_table([["Executive observations"]] + [[f"- {item}"] for item in bullets], [260 * mm], font_size=7.2))
    story.append(Spacer(1, 5 * mm))
    rep_rows = [["Planning scenario", "Statistical duration [days]", "Representative hindcast year", "Representative duration [days]", "Difference [days]"]]
    for _, row in reps.iterrows():
        rep_rows.append([row["Planning scenario"], _fmt(row["Statistical duration [days]"]), row["Representative hindcast year"], _fmt(row["Representative duration [days]"]), _fmt(row["Difference from target [days]"])])
    story.append(_table(rep_rows, [45 * mm, 48 * mm, 50 * mm, 50 * mm, 42 * mm], font_size=6.8))
    story.append(PageBreak())

    # 2 Overall campaign profile.
    story.append(_paragraph("2. Overall campaign profile", styles["Section"]))
    scenario_labels = ["P0", "Best"] + [f"P{p:g}" for p in settings.percentiles] + ["Worst"]
    scenario_values = [float(p0_summary.get("duration_hours", 0.0)) / 24.0]
    scenario_values.append(float(best.duration_hours) / 24.0 if best else 0.0)
    scenario_values.extend([analysis.duration_percentiles[p] / 24.0 for p in settings.percentiles] if len(durations) else [0.0] * len(settings.percentiles))
    scenario_values.append(float(worst.duration_hours) / 24.0 if worst else 0.0)
    duration_chart = _vertical_bar_chart(scenario_labels, [scenario_values], ["Duration [days]"], [BLUE], title="Campaign duration by scenario")
    line_names = ["P0"] + [f"P{p:g}" for p in settings.percentiles]
    line_cols = ["P0 [days]"] + [f"P{p:g} [days]" for p in settings.percentiles]
    position_chart = _line_chart(
        positions["Position"].astype(float).tolist() if not positions.empty else [],
        [positions[col].fillna(0.0).astype(float).tolist() for col in line_cols if col in positions.columns],
        [name for name, col in zip(line_names, line_cols) if col in positions.columns],
        [GREEN, BLUE, GREEN, ORANGE],
        title="Position completion profile",
    )
    story.append(_page_pair(duration_chart, position_chart))
    story.append(Spacer(1, 4 * mm))
    selected_positions = sorted(set([1, settings.total_positions] + [max(1, round(settings.total_positions * fraction)) for fraction in (0.25, 0.5, 0.75)]))
    rows = [["Position", "P0 [days]"] + [f"P{p:g} [days]" for p in settings.percentiles]]
    for position in selected_positions:
        row = positions.loc[positions["Position"] == position]
        if row.empty:
            continue
        record = row.iloc[0]
        rows.append([position, _fmt(record.get("P0 [days]"))] + [_fmt(record.get(f"P{p:g} [days]")) for p in settings.percentiles])
    campaign_row = ["Campaign complete", _fmt(float(p0_summary.get("duration_hours", 0.0)) / 24.0)]
    campaign_row += [_fmt(analysis.duration_percentiles[p] / 24.0 if len(durations) else None) for p in settings.percentiles]
    rows.append(campaign_row)
    story.append(_table(rows, [30 * mm] + [47 * mm] * (1 + len(settings.percentiles)), font_size=7.0))
    story.append(Spacer(1, 3 * mm))
    story.append(_paragraph("Position completion can precede full campaign completion because Type 3 close-out activities may remain after the final position milestone.", styles["Note"]))
    story.append(PageBreak())

    # 3 Monthly planning profile.
    story.append(_paragraph("3. Monthly planning profile", styles["Section"]))
    plan = planning_monthly.copy()
    labels = [pd.Timestamp(value).strftime("%b %Y") for value in plan["Planning month"]] if not plan.empty else []
    percentile_labels = [f"P{p:g}" for p in settings.percentiles]
    pos_series = [plan[f"positions_completed P{p:g}"].astype(float).tolist() for p in settings.percentiles if f"positions_completed P{p:g}" in plan]
    cum_series = [plan[f"cumulative_positions P{p:g}"].astype(float).tolist() for p in settings.percentiles if f"cumulative_positions P{p:g}" in plan]
    pos_chart = _vertical_bar_chart(labels, pos_series, percentile_labels[:len(pos_series)], [BLUE, GREEN, ORANGE][:len(pos_series)], title="Positions completed in the month")
    cum_chart = _line_chart(list(range(1, len(labels) + 1)), cum_series, percentile_labels[:len(cum_series)], [BLUE, GREEN, ORANGE][:len(cum_series)], title="Cumulative positions completed")
    story.append(_page_pair(pos_chart, cum_chart))
    story.append(Spacer(1, 3 * mm))
    monthly_rows = [["Month"] + [f"P{p:g} positions" for p in settings.percentiles] + [f"P{p:g} cumulative" for p in settings.percentiles]]
    for _, row in plan.head(8).iterrows():
        monthly_rows.append([pd.Timestamp(row["Planning month"]).strftime("%b %Y")] + [_fmt(row.get(f"positions_completed P{p:g}")) for p in settings.percentiles] + [_fmt(row.get(f"cumulative_positions P{p:g}")) for p in settings.percentiles])
    story.append(_table(monthly_rows, [35 * mm] + [34 * mm] * (2 * len(settings.percentiles)), font_size=6.5))
    story.append(PageBreak())

    # 4 Representatives and milestones.
    story.append(_paragraph("4. Representative scenarios and planning milestones", styles["Section"]))
    rep_rows = [["Planning scenario", "Statistical duration [days]", "Estimated finish", "Representative hindcast year", "Representative duration [days]", "Difference [days]"]]
    for _, row in reps.iterrows():
        rep_rows.append([row["Planning scenario"], _fmt(row["Statistical duration [days]"]), _fmt(row["Estimated finish"]), row["Representative hindcast year"], _fmt(row["Representative duration [days]"]), _fmt(row["Difference from target [days]"])])
    story.append(_table(rep_rows, [35 * mm, 43 * mm, 43 * mm, 47 * mm, 44 * mm, 36 * mm], font_size=6.3))
    story.append(Spacer(1, 8 * mm))
    milestone_positions = sorted(set([1, settings.total_positions] + [max(1, round(settings.total_positions * fraction)) for fraction in (0.25, 0.5, 0.75)]))
    date_cols = ["Position"] + [f"P{p:g} completion date" for p in settings.percentiles]
    elapsed_cols = [f"P{p:g} elapsed [days]" for p in settings.percentiles]
    rows = [["Position"] + [f"P{p:g} date" for p in settings.percentiles] + [f"P{p:g} elapsed [days]" for p in settings.percentiles]]
    for position in milestone_positions:
        item = planning_positions.loc[planning_positions["Position"] == position]
        if item.empty:
            continue
        record = item.iloc[0]
        rows.append([position] + [_fmt(record.get(col)) for col in date_cols[1:]] + [_fmt(record.get(col)) for col in elapsed_cols])
    story.append(_table(rows, [25 * mm] + [39 * mm] * (2 * len(settings.percentiles)), font_size=6.3))
    story.append(Spacer(1, 7 * mm))
    story.append(_paragraph("Representative-year detail does not replace the statistical percentile result. It provides a complete historical schedule and detailed downtime trace for review.", styles["Note"]))
    story.append(PageBreak())

    # 5 Planning workability and downtime.
    story.append(_paragraph("5. Planning workability and downtime", styles["Section"]))
    summary_rows = []
    workable_values = []
    downtime_values = []
    scenario_names = []
    representative_map = {}
    for percentile in settings.percentiles:
        rep, target = representative_result(results, percentile)
        if rep is None or target is None:
            continue
        scenario = f"P{percentile:g}"
        representative_map[scenario] = rep
        scenario_names.append(scenario)
        workable_values.append(float(rep.working_hours))
        downtime_values.append(float(rep.downtime_hours))
        total = float(rep.duration_hours or 0.0)
        summary_rows.append([scenario, rep.start_year, _fmt(target / 24.0), _fmt(total / 24.0), _fmt(rep.working_hours), _fmt(rep.downtime_hours), _fmt(rep.downtime_hours / total * 100.0 if total else 0.0, "%")])
    time_chart = _vertical_bar_chart(scenario_names, [workable_values, downtime_values], ["Workable time", "Downtime"], [BLUE, ORANGE], title="Workable time and downtime")
    selected_activity = downtime_breakdown_dataframe(selected)[1] if selected else pd.DataFrame()
    top = selected_activity.head(9).sort_values("Downtime hours") if not selected_activity.empty else pd.DataFrame()
    activity_labels = top["Activity"].astype(str).tolist() if not top.empty else ["No downtime"]
    activity_values = top["Downtime hours"].astype(float).tolist() if not top.empty else [0.0]
    activity_chart = _horizontal_bar_chart(activity_labels, activity_values, title=f"{selected_label} downtime by activity")
    story.append(_page_pair(time_chart, activity_chart))
    story.append(Spacer(1, 4 * mm))
    story.append(_table([["Scenario", "Representative year", "Statistical duration [days]", "Representative duration [days]", "Workable [h]", "Downtime [h]", "Downtime [%]"]] + summary_rows, [30 * mm, 35 * mm, 42 * mm, 45 * mm, 32 * mm, 32 * mm, 30 * mm], font_size=6.2))
    story.append(PageBreak())

    # 6 Selected detailed-result basis.
    if is_p0_basis(settings):
        detail_heading = "6. P0 deterministic no-weather detail"
    elif selected_is_percentile:
        detail_heading = f"6. {selected_label} representative hindcast-year detail"
    else:
        detail_heading = f"6. Hindcast year {selected_label} detail"
    story.append(_paragraph(detail_heading, styles["Section"]))
    cause, activity = downtime_breakdown_dataframe(selected)
    if is_p0_basis(settings):
        p0_overview = [
            ["P0 basis", "Value"],
            ["Exact learning-adjusted productive duration", _fmt(float(p0_summary.get("duration_hours", 0.0)), " h")],
            ["Weather downtime", "0.000 h"],
            ["Weather-simulation timestep adjustment", "Not applicable"],
            ["Representative hindcast year", "Not applicable"],
            ["Execution basis", "Continuous activity-to-activity schedule from the planning start"],
        ]
        story.append(_table(p0_overview, [105 * mm, 150 * mm], font_size=7.0))
        story.append(Spacer(1, 7 * mm))
    else:
        top_activity = activity.head(8).sort_values("Downtime hours") if not activity.empty else pd.DataFrame()
        detail_activity_labels = top_activity["Activity"].astype(str).tolist() if not top_activity.empty else ["No downtime"]
        detail_activity_values = top_activity["Downtime hours"].astype(float).tolist() if not top_activity.empty else [0.0]
        activity_chart = _horizontal_bar_chart(detail_activity_labels, detail_activity_values, title=f"{selected_label} activity downtime")
        waiting = selected.downtime_by_group if selected else {}
        waiting_labels = list(waiting.keys()) or ["No safe-to-safe waiting"]
        waiting_values = [float(waiting[key]) for key in waiting] if waiting else [0.0]
        waiting_chart = _vertical_bar_chart(waiting_labels, [waiting_values], ["Waiting [h]"], [GREEN], title="Safe-to-safe group waiting")
        story.append(_page_pair(activity_chart, waiting_chart))
        story.append(Spacer(1, 3 * mm))
    detail_rows = [["Metric", "Value", "% of campaign"]]
    if selected is not None:
        total = float(selected.duration_hours or 0.0)
        detail_rows += [
            ["Workable time", _fmt(selected.working_hours, " h"), _fmt(selected.working_hours / total * 100.0 if total else 0.0, "%")],
            ["Downtime", _fmt(selected.downtime_hours, " h"), _fmt(selected.downtime_hours / total * 100.0 if total else 0.0, "%")],
            ["Timestep adjustment", ("Not applicable" if is_p0_basis(settings) else _fmt(selected.timestep_adjustment_hours, " h")), ("0.000%" if is_p0_basis(settings) else _fmt(selected.timestep_adjustment_hours / total * 100.0 if total else 0.0, "%"))],
        ]
    location_rows = [["Location", "Working [h]", "Downtime [h]", "Total [h]", "Downtime [%]"]]
    if selected is not None:
        for location in locations:
            working = float(selected.working_by_location.get(location.location_id, 0.0))
            downtime = float(selected.downtime_by_location.get(location.location_id, 0.0))
            total = working + downtime
            location_rows.append([location.name, _fmt(working), _fmt(downtime), _fmt(total), _fmt(downtime / total * 100.0 if total else 0.0, "%")])
    lower = _page_pair(
        _table(detail_rows, [55 * mm, 40 * mm, 38 * mm], font_size=6.5),
        _table(location_rows, [50 * mm, 20 * mm, 20 * mm, 20 * mm, 20 * mm], font_size=5.8),
        widths=(133 * mm, 133 * mm),
    )
    story.append(lower)
    story.append(Spacer(1, 4 * mm))
    selected_note = (
        "Selected detailed output is deterministic P0: exact learning-adjusted activity durations executed continuously with zero weather downtime and no weather-simulation timestep adjustment."
        if is_p0_basis(settings) else
        f"Selected detailed output ({selected_label}) is based on hindcast year {selected.start_year if selected else '-'} and is used for activity, safe-to-safe and location-level review."
    )
    story.append(_paragraph(selected_note, styles["Note"]))
    story.append(PageBreak())

    # 7 Cause of downtime (weather scenarios only).
    if not is_p0_basis(settings) and selected is not None:
        cause_mech, activity_detail, activity_matrix = downtime_detail_frames(selected)
        story.append(_paragraph("7. Cause of downtime", styles["Section"]))
        if cause_mech.empty:
            story.append(_paragraph("No weather downtime was recorded for the selected detailed scenario.", styles["Note"]))
        else:
            cause_labels = cause_mech["Cause combination"].astype(str).tolist()[:10]
            cause_values = cause_mech["Total [h]"].astype(float).tolist()[:10]
            story.append(_horizontal_bar_chart(cause_labels[::-1], cause_values[::-1], title=f"{selected_label} downtime by weather cause", width=260 * mm, height=86 * mm))
            cause_rows = [["Cause combination", "Direct [h]", "Window pre-check [h]", "Total [h]", "% WDT", "% campaign"]]
            for _, row in cause_mech.head(12).iterrows():
                cause_rows.append([row["Cause combination"], _fmt(row["Direct [h]"]), _fmt(row["Window pre-check [h]"]), _fmt(row["Total [h]"]), _fmt(row["% WDT"], "%"), _fmt(row["% campaign"], "%")])
            story.append(_table(cause_rows, [80 * mm, 32 * mm, 42 * mm, 30 * mm, 30 * mm, 32 * mm], font_size=6.2))
            story.append(Spacer(1, 4 * mm))
            story.append(_paragraph("Cause is the actual weather criterion or criterion combination. Direct exceedance and Window pre-check are assessment mechanisms only; both remain attributed to the weather cause that blocks the operation.", styles["Note"]))
        story.append(PageBreak())

        # 8 Activities driving downtime.
        story.append(_paragraph("8. Activities driving downtime", styles["Section"]))
        top_activity = activity_detail.head(8).copy()
        if not top_activity.empty:
            cause_cols = [c for c in activity_matrix.columns if c not in {"Activity", "Total WDT [h]", "% total WDT"}]
            cause_cols = cause_cols[:6]
            matrix_top = activity_matrix.set_index("Activity").reindex(top_activity["Activity"]).fillna(0.0)
            chart_series = [matrix_top[c].astype(float).tolist() for c in cause_cols]
            palette = [BLUE, ORANGE, GREEN, RED, GREY, colors.HexColor("#8064A2")]
            story.append(_horizontal_stacked_bar_chart(top_activity["Activity"].astype(str).tolist(), chart_series, cause_cols, palette, title="Top activities split by weather cause"))
            act_rows = [["Activity", "Total WDT [h]", "% WDT", "Dominant cause", "Direct [h]", "Window pre-check [h]"]]
            for _, row in top_activity.iterrows():
                act_rows.append([row["Activity"], _fmt(row["Total WDT [h]"]), _fmt(row["% total WDT"], "%"), row["Dominant cause"], _fmt(row["Direct [h]"]), _fmt(row["Window pre-check [h]"])])
            story.append(_table(act_rows, [78 * mm, 30 * mm, 25 * mm, 65 * mm, 28 * mm, 38 * mm], font_size=5.8))
            story.append(Spacer(1, 4 * mm))
            story.append(_paragraph("The executive PDF shows the highest-impact activities. The Excel detail sheet provides the full additive Activity x Cause matrix and OUT_run retains the timestamp-level evidence.", styles["Note"]))
        story.append(PageBreak())
        coverage_section = 9
        methodology_section = 10
    else:
        coverage_section = 7
        methodology_section = 8

    # Hindcast distribution and coverage.
    story.append(_paragraph(f"{coverage_section}. Hindcast distribution and coverage", styles["Section"]))
    completed = annual[annual["Successful"] == True].copy() if not annual.empty and "Successful" in annual.columns else annual.copy()
    year_labels = completed["Hindcast start year"].astype(int).astype(str).tolist() if not completed.empty else []
    duration_values = completed["Duration [days]"].astype(float).tolist() if not completed.empty else []
    annual_chart = _vertical_bar_chart(year_labels, [duration_values], ["Duration [days]"], [BLUE], title="Completed hindcast campaign durations", width=260 * mm, height=88 * mm)
    story.append(annual_chart)
    story.append(Spacer(1, 3 * mm))
    coverage_rows = [
        ["Metric", "Value"],
        ["Completed simulations", len(valid)],
        ["Excluded simulations", len(results) - len(valid)],
        ["Campaign-year range", f"{min((item.start_year for item in results), default='-')} to {max((item.start_year for item in results), default='-')}"],
        ["Mean duration", _fmt(np.mean(durations) / 24.0 if len(durations) else None, " days")],
        ["Median duration", _fmt(np.median(durations) / 24.0 if len(durations) else None, " days")],
        ["Minimum duration", _fmt(np.min(durations) / 24.0 if len(durations) else None, " days")],
        ["Maximum duration", _fmt(np.max(durations) / 24.0 if len(durations) else None, " days")],
    ]
    story.append(_table(coverage_rows, [80 * mm, 180 * mm], font_size=7.0))
    story.append(Spacer(1, 5 * mm))
    story.append(_paragraph("Only completed hindcast simulations are included in percentile statistics. Incomplete simulations remain visible in the Excel planning-coverage output.", styles["Note"]))
    story.append(PageBreak())

    # 8 Methodology and definitions - no limitations section.
    story.append(_paragraph(f"{methodology_section}. Methodology, definitions and interpretation", styles["Section"]))
    definitions = [
        ["Term", "Definition used in this report"],
        ["Exact P0", f"Sum of exact learning-adjusted activity durations without weather delay: {_fmt(float(p0_summary.get('duration_hours', 0.0)), ' h')} ({_fmt(float(p0_summary.get('duration_hours', 0.0)) / 24.0, ' d')})."],
        ["Timestep adjustment", "Weather-simulation grid effect only. It is not applied to P0 and is reported separately from weather downtime."],
        ["Statistical P50/P75/P90", "Campaign-duration and progress percentiles calculated across the completed hindcast simulations."],
        ["Representative hindcast year", "A completed historical simulation selected because its total duration is closest to the statistical percentile target."],
        ["Detailed results basis", "Deterministic P0, Percentile 1, 2 or 3 representative hindcast year, or one selected historical year for QA review."],
        ["Positions completed in the month", "Percentile of scenario monthly completions. Cumulative positions are percentiled separately; monthly percentiles are non-additive."],
        ["Monthly downtime", "Monthly weather and operational downtime percentage. It is not cumulative."],
        ["Safe-to-safe group", "Consecutive activities pre-checked as one committed sequence from one safe state to the next; once started, weather waiting is not inserted between group members."],
        ["MOST_STRINGENT", "Applies the most restrictive populated limits continuously across the complete committed safe-to-safe duration."],
        ["TIME_PHASED", "Applies each activity's limits during its expected part of the committed safe-to-safe sequence."],
        ["Downtime cause", "The actual blocking weather criterion or criterion combination, for example Hs, Tp, or Wind 10 m + Hs."],
        ["Downtime mechanism", "Direct exceedance or Window pre-check. Window pre-check downtime is still attributed to the future weather criterion that blocks the required continuous window."],
        ["Data coverage exclusion", "A simulation that cannot complete before the weather data ends is excluded from percentile statistics."],
    ]
    story.append(_table(definitions, [58 * mm, 202 * mm], font_size=7.0))
    story.append(Spacer(1, 7 * mm))
    story.append(_paragraph(f"Source: Weather Assessment v{app_version}. Report generated {datetime.now().strftime('%d %b %Y, %H:%M')}.", styles["Small"]))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
