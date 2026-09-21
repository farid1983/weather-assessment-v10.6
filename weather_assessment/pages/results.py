from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from weather_assessment.planning import detailed_results_basis_display, is_p0_basis, representative_result
from weather_assessment.statistics import downtime_breakdown_dataframe, downtime_main_factor_dataframe, selected_year_monthly_dataframe, successful_results
from weather_assessment.ui import BLUE, GREEN, RED, TEAL, metric_card, page_header, section_gap
from weather_assessment.ui_context import (
    _decimal_axes,
    _decimal_pie,
    _qa_styler,
    _result_table,
    current_detail,
    current_analysis,
    dataframe_to_activities,
    dataframe_to_locations,
    require_results,
)


def page_campaign_summary() -> None:
    page_header("09", "Campaign summary", "Overview of campaign duration, installation progress and representative downtime.")
    if not require_results(): return
    settings = st.session_state.settings
    results = st.session_state.results
    p0 = st.session_state.p0_summary
    summary = current_analysis().table("campaign")
    valid = successful_results(results)
    if not valid:
        st.info("No completed weather scenarios are available. P0 remains available in the detailed results and exports.")
        return
    best = min(valid, key=lambda x: x.duration_hours) if valid else None
    worst = max(valid, key=lambda x: x.duration_hours) if valid else None
    scenario_map = summary.set_index("Scenario") if not summary.empty else pd.DataFrame()
    cards = st.columns(6)
    with cards[0]: metric_card("P0 duration", f"{p0['duration_days']:.3f}", "days", "No-weather duration")
    for idx, percentile in enumerate(settings.percentiles, start=1):
        row = scenario_map.loc[f"P{percentile:g}"]
        with cards[idx]: metric_card(f"P{percentile:g} duration", f"{row['Duration [days]']:.3f}", "days", f"{percentile:g}% duration percentile", TEAL if percentile == 50 else BLUE)
    with cards[4]: metric_card("Best year", str(best.start_year if best else "—"), note=f"{best.duration_hours/24:.3f} days" if best else "", accent=GREEN)
    with cards[5]: metric_card("Worst year", str(worst.start_year if worst else "—"), note=f"{worst.duration_hours/24:.3f} days" if worst else "", accent=RED)
    section_gap()

    positions = current_analysis().table("positions")
    c1, c2 = st.columns([2, 1])
    with c1:
        plot_columns = [column for column in positions.columns if column != "Position"]
        long = positions.melt(id_vars="Position", value_vars=plot_columns, var_name="Scenario", value_name="Elapsed days")
        fig = px.line(long, x="Elapsed days", y="Position", color="Scenario", title="Cumulative positions complete over time")
        fig.update_layout(yaxis_title="Positions complete", xaxis_title="Campaign duration [days]", height=430)
        st.plotly_chart(_decimal_axes(fig, x=True), use_container_width=True)
    with c2:
        rep, _ = representative_result(results, settings.percentiles[0])
        if rep:
            pie = pd.DataFrame({"Category": ["Working time", "Downtime"], "Hours": [rep.working_hours, rep.downtime_hours]})
            fig = px.pie(pie, names="Category", values="Hours", hole=.58, title=f"Working time vs downtime — P{settings.percentiles[0]:g} representative")
            st.plotly_chart(_decimal_pie(fig), use_container_width=True)
    section_gap()
    c3, c4 = st.columns([2, 1])
    with c3:
        annual = current_analysis().table("annual")
        st.subheader("Annual results")
        st.dataframe(_result_table(annual), use_container_width=True, hide_index=True, height=360)
    with c4:
        coverage = st.session_state.assessment_run.coverage
        st.subheader("Validation & metadata")
        st.dataframe(pd.DataFrame([
            {"Item": "Planning year", "Value": str(settings.nominal_year)},
            {"Item": "Common weather coverage", "Value": f"{coverage[0]:%Y-%m-%d} to {coverage[1]:%Y-%m-%d}" if coverage else "—"},
            {"Item": "Successful simulations", "Value": f"{len(valid)} / {len(results)}"},
            {"Item": "Locations used", "Value": str(len({item.location_id for item in dataframe_to_activities(st.session_state.activities_df)}))},
            {"Item": "Last run", "Value": str(st.session_state.last_run_at or "—")},
        ]), use_container_width=True, hide_index=True)


def page_annual() -> None:
    page_header("10", "Annual hindcast", "Compare campaign performance across all synchronized historical start years.")
    if not require_results(): return
    annual = current_analysis().table("annual")
    if annual.empty:
        st.info("No historical scenarios have been calculated.")
        return
    valid = annual[annual["Successful"] == True].copy()
    if valid.empty:
        st.warning("No successful historical simulations.")
        return
    best = valid.loc[valid["Duration [days]"].idxmin()]
    worst = valid.loc[valid["Duration [days]"].idxmax()]
    cards = st.columns(4)
    with cards[0]: metric_card("Best year", str(int(best["Hindcast start year"])), note=f"{best['Duration [days]']:.3f} days", accent=GREEN)
    with cards[1]: metric_card("Median duration", f"{valid['Duration [days]'].median():.3f}", "days", "Across successful years")
    with cards[2]: metric_card("Mean duration", f"{valid['Duration [days]'].mean():.3f}", "days", f"Std. dev. {valid['Duration [days]'].std():.3f} days")
    with cards[3]: metric_card("Worst year", str(int(worst["Hindcast start year"])), note=f"{worst['Duration [days]']:.3f} days", accent=RED)
    fig = px.bar(valid.sort_values("Duration [days]"), x="Duration [days]", y="Hindcast start year", orientation="h", title="Annual campaign-duration ranking")
    fig.update_layout(height=520)
    st.plotly_chart(_decimal_axes(fig, x=True), use_container_width=True)
    st.dataframe(_result_table(annual), use_container_width=True, hide_index=True)


def page_planning() -> None:
    settings = st.session_state.settings
    page_header("11", "Planning estimate", f"Map all successful historical scenarios onto the planned {settings.nominal_year} campaign calendar.")
    if not require_results(): return
    results = st.session_state.results
    if not successful_results(results):
        st.info("No completed weather scenarios are available for planning statistics.")
        return
    summary = current_analysis().table("planning_summary")
    reps = current_analysis().table("representatives")
    cards = st.columns(5)
    with cards[0]: metric_card("Planned start date", f"{settings.start_day:02d}-{settings.start_month:02d}-{settings.nominal_year}", note="Campaign calendar")
    for idx, percentile in enumerate(settings.percentiles, start=1):
        row = summary.loc[summary["Scenario"] == f"P{percentile:g}"].iloc[0]
        with cards[idx]: metric_card(f"P{percentile:g} duration", f"{row['Duration [days]']:.3f}", "days", f"Finish {row['Estimated finish']:%Y-%m-%d}", TEAL if percentile == 50 else BLUE)
    rep50, _ = representative_result(results, settings.percentiles[0])
    with cards[4]: metric_card("Representative year", str(rep50.start_year if rep50 else "—"), note=f"Nearest P{settings.percentiles[0]:g} duration", accent=GREEN)

    monthly = current_analysis().table("planning_monthly")
    c1, c2 = st.columns([2, 1])
    with c1:
        percentile_cols = [f"cumulative_positions P{p:g}" for p in settings.percentiles]
        long = monthly[["Month name"] + percentile_cols].melt(id_vars="Month name", var_name="Scenario", value_name="Positions")
        st.plotly_chart(px.line(long, x="Month name", y="Positions", color="Scenario", markers=True, title="Cumulative positions completed by planning month"), use_container_width=True)
    with c2:
        display_cols = ["Month name"] + [f"positions_completed P{p:g}" for p in settings.percentiles] + [f"downtime_pct P{settings.percentiles[0]:g}"]
        st.subheader("Monthly statistics")
        st.dataframe(_result_table(monthly[display_cols]), use_container_width=True, hide_index=True, height=410)

    st.subheader("Selected-percentile downtime breakdown")
    selected_p = st.radio("Planning percentile", [f"P{p:g}" for p in settings.percentiles], horizontal=True)
    percentile = float(selected_p[1:])
    representative, target_duration = representative_result(results, percentile)
    if representative:
        cause, activity = downtime_breakdown_dataframe(representative)
        work = representative.working_hours
        down = representative.downtime_hours
        total = representative.duration_hours or (work + down)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Statistical duration", f"{target_duration/24:.3f} days")
        m2.metric("Representative year", representative.start_year)
        m3.metric("Working time", f"{work/total*100:.3f}%" if total else "—")
        m4.metric("Downtime", f"{down/total*100:.3f}%" if total else "—")
        b1, b2 = st.columns([2, 1])
        with b1:
            if not cause.empty:
                cause_bar = px.bar(cause, x="% of total downtime", y="Downtime cause", orientation="h", title=f"{selected_p} downtime causes — representative year {representative.start_year}")
                st.plotly_chart(_decimal_axes(cause_bar, x=True), use_container_width=True)
                st.dataframe(_result_table(cause), use_container_width=True, hide_index=True)
        with b2:
            pie = pd.DataFrame({"Category": ["Working time", "Downtime"], "Hours": [work, down]})
            planning_pie = px.pie(pie, names="Category", values="Hours", hole=.58, title="Working time vs downtime")
            st.plotly_chart(_decimal_pie(planning_pie), use_container_width=True)
            st.subheader("Activity breakdown")
            st.dataframe(_result_table(activity.head(12)), use_container_width=True, hide_index=True)

    with st.expander("Historical scenarios included / excluded"):
        st.dataframe(_result_table(current_analysis().table("coverage")), use_container_width=True, hide_index=True)


def page_monthly() -> None:
    page_header("12", "Monthly statistics", "Review monthly positions, downtime and workable hours across the historical ensemble.")
    if not require_results(): return
    settings = st.session_state.settings
    monthly = current_analysis().table("planning_monthly")
    if monthly.empty:
        st.info("No completed weather scenarios are available for monthly statistics.")
        return
    st.caption("Monthly and cumulative percentiles are calculated separately across scenarios. Monthly percentiles are non-additive.")
    selected = st.selectbox("Percentile", [f"P{p:g}" for p in settings.percentiles])
    p = selected[1:]
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.bar(monthly, x="Month name", y=f"positions_completed P{p}", title=f"Positions completed — {selected}"), use_container_width=True)
    with c2:
        monthly["Cumulative"] = monthly[f"cumulative_positions P{p}"]
        st.plotly_chart(px.line(monthly, x="Month name", y="Cumulative", markers=True, title=f"Cumulative positions — {selected}"), use_container_width=True)
    c3, c4 = st.columns(2)
    with c3:
        downtime_fig = px.line(monthly, x="Month name", y=f"downtime_pct P{p}", markers=True, title=f"Downtime percentage — {selected}")
        downtime_fig.update_yaxes(tickformat=".3%")
        st.plotly_chart(downtime_fig, use_container_width=True)
    with c4:
        workable_fig = px.line(monthly, x="Month name", y=f"workable_hours_per_day P{p}", markers=True, title=f"Workable hours per day — {selected}")
        st.plotly_chart(_decimal_axes(workable_fig, y=True), use_container_width=True)
    st.dataframe(_result_table(monthly), use_container_width=True, hide_index=True)


def page_selected_year() -> None:
    page_header("13", "Detailed-results summary", "Detailed output for the representative percentile basis or historical hindcast year selected in campaign settings.")
    if not require_results(): return
    settings = st.session_state.settings
    result = current_detail()
    if result is None:
        st.warning("The latest run was a quick assessment. Run a full assessment on page 08 to store the detailed trace and breakdown.")
        return
    cards = st.columns(6)
    with cards[0]: metric_card("Detailed basis", ("P0" if is_p0_basis(settings) else str(result.start_year)), note=detailed_results_basis_display(settings))
    with cards[1]: metric_card("Duration", f"{result.duration_hours/24:.3f}" if result.duration_hours else "—", "days")
    with cards[2]: metric_card("Positions", str(len(result.position_completion_dates)), note=f"of {st.session_state.settings.total_positions}")
    with cards[3]: metric_card("Working time", f"{result.working_hours:.3f}", "h", f"{result.working_hours/result.duration_hours*100:.3f}%" if result.duration_hours else "")
    with cards[4]: metric_card("Downtime", f"{result.downtime_hours:.3f}", "h", f"{result.downtime_hours/result.duration_hours*100:.3f}%" if result.duration_hours else "", RED)
    with cards[5]: metric_card("Finish", result.campaign_finish.strftime("%Y-%m-%d") if result.campaign_finish else "Incomplete")
    monthly = selected_year_monthly_dataframe(result)
    if not monthly.empty:
        c1, c2 = st.columns(2)
        with c1: st.plotly_chart(px.bar(monthly, x="Month name", y="positions_completed", title="Monthly positions completed"), use_container_width=True)
        with c2:
            time_fig = px.bar(monthly, x="Month name", y=["working_hours", "downtime_hours"], barmode="stack", title="Working time vs downtime")
            st.plotly_chart(_decimal_axes(time_fig, y=True), use_container_width=True)
    milestones = pd.DataFrame({
        "Position": list(result.position_completion_dates),
        "Completion date": list(result.position_completion_dates.values()),
        "Elapsed days": [result.position_completion_elapsed_hours[p] / 24 for p in result.position_completion_dates],
    })
    if not milestones.empty:
        milestone_fig = px.line(milestones, x="Position", y="Elapsed days", markers=True, title=f"Position completion timeline — {result.start_year}")
        st.plotly_chart(_decimal_axes(milestone_fig, y=True), use_container_width=True)
    location_rows = []
    for location in dataframe_to_locations(st.session_state.locations_df):
        working = result.working_by_location.get(location.location_id, 0.0)
        downtime = result.downtime_by_location.get(location.location_id, 0.0)
        location_rows.append({"Location ID": location.location_id, "Location": location.name, "Working [h]": working, "Downtime [h]": downtime, "Downtime [%]": downtime/(working+downtime)*100 if working+downtime else 0})
    st.subheader("Location performance")
    st.dataframe(_result_table(pd.DataFrame(location_rows)), use_container_width=True, hide_index=True)


def page_qa() -> None:
    page_header("14", "QA and downtime breakdown", "Filter the detailed operational trace and identify the weather cause and assessment mechanism behind downtime.")
    if not require_results():
        return
    settings = st.session_state.settings
    result = current_detail()
    if result is None or result.trace is None:
        st.warning("The selected completed scenario is unavailable. Run an assessment or choose another detailed basis.")
        return
    trace = result.trace
    f1, f2, f3, f4, f5, f6 = st.columns(6)
    statuses = f1.multiselect("Status", sorted(trace["Status"].dropna().unique()))
    activities = f2.multiselect("Activity", sorted(trace["Activity"].dropna().unique()))
    locations = f3.multiselect("Location", sorted(trace["Location"].dropna().unique()))
    downtime_types = f4.multiselect("Downtime type", sorted(item for item in trace["Downtime type"].dropna().unique() if item))
    main_factors = f5.multiselect("Main factor", sorted(item for item in trace["Main factor"].dropna().unique() if item))
    groups = f6.multiselect("Safe-to-safe group", sorted(item for item in trace["Safe-to-safe group"].dropna().astype(str).unique() if item))
    display = trace
    if statuses:
        display = display[display["Status"].isin(statuses)]
    if activities:
        display = display[display["Activity"].isin(activities)]
    if locations:
        display = display[display["Location"].isin(locations)]
    if downtime_types:
        display = display[display["Downtime type"].isin(downtime_types)]
    if main_factors:
        display = display[display["Main factor"].isin(main_factors)]
    if groups:
        display = display[display["Safe-to-safe group"].astype(str).isin(groups)]

    cards = st.columns(6)
    cards[0].metric("QA intervals", f"{len(trace):,}")
    cards[1].metric("Exact P0", f"{result.exact_p0_hours:,.3f} h")
    cards[2].metric("Timestep adjustment", f"{result.timestep_adjustment_hours:,.3f} h")
    cards[3].metric("Working time", f"{result.working_hours:,.3f} h")
    cards[4].metric("Weather downtime", f"{result.downtime_hours:,.3f} h")
    cards[5].metric("Completed positions", len(result.position_completion_dates))

    st.subheader("QA status detail")
    st.caption("Consecutive rows with the same operational state and blocker are combined into intervals. Blocking factor and assessment basis remain traceable.")
    row_options = [250, 500, 1000, 2500]
    max_display_rows = st.selectbox(
        "Rows to display", row_options, index=1,
        help="A smaller display limit keeps the coloured QA table responsive. The CSV download always contains all filtered intervals.",
    )
    display_view = display.head(int(max_display_rows))
    if len(display) > int(max_display_rows):
        st.info(f"Showing the first {int(max_display_rows):,} of {len(display):,} filtered QA intervals. The CSV download includes all filtered intervals.")
    st.dataframe(_qa_styler(display_view), use_container_width=True, hide_index=True, height=520)

    factor_summary = downtime_main_factor_dataframe(result)
    st.subheader("Main downtime factors")
    st.caption("Downtime is attributed to the exact weather criterion or criterion combination. Direct exceedance and Window pre-check are assessment mechanisms, not separate causes.")
    if not factor_summary.empty:
        c1, c2 = st.columns([1.15, 1])
        with c1:
            st.dataframe(_result_table(factor_summary), use_container_width=True, hide_index=True)
        with c2:
            factor_long = factor_summary.melt(
                id_vars="Main factor",
                value_vars=["Direct downtime [h]", "Window pre-check [h]"],
                var_name="Downtime type",
                value_name="Hours",
            )
            factor_fig = px.bar(
                factor_long, x="Hours", y="Main factor", color="Downtime type",
                orientation="h", barmode="stack", title="Direct and window-pre-check downtime by weather cause",
            )
            factor_fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(_decimal_axes(factor_fig, x=True), use_container_width=True)

    cause, activity = downtime_breakdown_dataframe(result)
    st.subheader("Detailed downtime labels and activities")
    c1, c2 = st.columns(2)
    with c1:
        if not cause.empty:
            cause_fig = px.pie(cause, names="Downtime cause", values="Hours", hole=.45, title="Detailed downtime labels")
            st.plotly_chart(_decimal_pie(cause_fig), use_container_width=True)
            st.dataframe(_result_table(cause), use_container_width=True, hide_index=True)
    with c2:
        if not activity.empty:
            activity_fig = px.bar(activity, x="Downtime hours", y="Activity", orientation="h", title="Downtime by activity")
            st.plotly_chart(_decimal_axes(activity_fig, x=True), use_container_width=True)
            st.dataframe(_result_table(activity.head(15)), use_container_width=True, hide_index=True)

    location_cause_rows = []
    for location_id, mapping in result.downtime_by_location_cause.items():
        for cause_name, hours in mapping.items():
            location_cause_rows.append({"Location": location_id, "Cause": cause_name, "Hours": hours})
    if location_cause_rows:
        st.subheader("Downtime by location and detailed cause")
        location_cause = pd.DataFrame(location_cause_rows)
        location_fig = px.bar(location_cause, x="Hours", y="Location", color="Cause", orientation="h", title="Location downtime attribution")
        st.plotly_chart(_decimal_axes(location_fig, x=True), use_container_width=True)
        st.dataframe(_result_table(location_cause), use_container_width=True, hide_index=True)
    if result.downtime_by_group:
        st.subheader("Safe-to-safe group waiting")
        group_waiting = pd.DataFrame([
            {"Safe-to-safe group": group_id, "Waiting hours": hours}
            for group_id, hours in sorted(result.downtime_by_group.items())
        ])
        group_fig = px.bar(group_waiting, x="Waiting hours", y="Safe-to-safe group", orientation="h", title="Waiting for complete group window")
        st.plotly_chart(_decimal_axes(group_fig, x=True), use_container_width=True)
        st.dataframe(_result_table(group_waiting), use_container_width=True, hide_index=True)
    st.download_button("Download filtered QA CSV", display.to_csv(index=False).encode("utf-8"), f"QA_{result.start_year}.csv", "text/csv")
