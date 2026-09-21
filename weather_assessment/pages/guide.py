from __future__ import annotations

import pandas as pd
import streamlit as st
from weather_assessment.ui import page_header, workflow_step_card


def page_guide() -> None:
    page_header("00", "User guide", "A single reference page for preparing inputs, running assessments and interpreting results.")

    st.subheader("Recommended workflow")
    cols = st.columns(6)
    steps = [
        ("1", "Weather data", "Create work locations and load the weather CSV for each location used by the campaign."),
        ("2", "Project input", "Import the project workbook, reopen a saved project package, or edit inputs directly."),
        ("3", "Configure", "Review campaign settings, activity locations, Hs–Tp curves and the learning curve."),
        ("4", "Sequence", "Generate and inspect the expanded campaign sequence before calculation."),
        ("5", "Run", "Use Quick for summary outputs or Full for the selected-year QA trace."),
        ("6", "Review & export", "Review results, then download the Excel workbook or PDF executive summary."),
    ]
    for col, (number, title, body) in zip(cols, steps):
        with col:
            workflow_step_card(number, title, body)

    st.subheader("Activity sequence logic")
    st.dataframe(pd.DataFrame([
        {"Type": 1, "When it runs": "Once at the start of every cycle", "Examples": "Loadout, mobilisation, departure preparation"},
        {"Type": 2, "When it runs": "Repeated for every position", "Examples": "Positioning, lifting, installation, survey"},
        {"Type": 3, "When it runs": "Once at the end of every cycle", "Examples": "Return transit, replenishment, cycle close-out"},
    ]), use_container_width=True, hide_index=True)

    st.markdown("""
**Important activity fields**

- **No learning curve:** keeps the activity duration unchanged between cycles.
- **Position complete:** mark exactly one Type 2 activity; completing it counts one installed position.
- **Work location:** selects the location weather dataset controlling the activity.
- **Safe-to-safe group:** enter the same Group ID on consecutive activities that must be completed as one committed sequence.
- **Duration:** productive working time needed to complete the activity.
- **Weather window:** minimum continuous workable period required before the activity may start or continue.
- **Hs–Tp curve:** optional combined wave-height and peak-period operating envelope.
""")

    st.subheader("Safe-to-safe commitment groups")
    st.markdown("""
Use a Group ID such as **G1** or **G2** when the first activity may start only after a suitable forecast window has been confirmed for the complete sequence through the declared safe condition.

- Group members must be consecutive and use the same activity type.
- **MOST_STRINGENT** applies the lowest populated limits from the group over the full continuous safe-to-safe duration.
- **TIME_PHASED** applies each activity's own limits during its expected part of the sequence.
- Page 03 defines the project default; page 04 allows a group-specific override and assessment location.
- Both methods pre-check the complete sequence before the first activity starts.
- Once the group starts, no weather waiting is allowed between grouped activities.
- Blank Group ID means the activity remains standalone.

Example:

`Tower preparation part 1 → Tower preparation part 2 and rigging → Tower lifting safe to safe → Tower derigging`
""")
    st.dataframe(pd.DataFrame([
        {"Group": "G1", "Activity": "Tower preparation part 1: remove seafastening bolts", "Role": "Start"},
        {"Group": "G1", "Activity": "Tower preparation part 2 and rigging", "Role": "Continue"},
        {"Group": "G1", "Activity": "Tower lifting safe to safe", "Role": "Continue"},
        {"Group": "G1", "Activity": "Tower derigging", "Role": "End / safe condition"},
        {"Group": "G2", "Activity": "Nacelle preparation and rigging", "Role": "Start"},
        {"Group": "G2", "Activity": "Nacelle lifting safe to safe", "Role": "Continue"},
        {"Group": "G2", "Activity": "Nacelle derigging", "Role": "End / safe condition"},
    ]), use_container_width=True, hide_index=True)
    st.dataframe(pd.DataFrame([
        {"Method": "MOST_STRINGENT", "How the start is decided": "Lowest group limits applied continuously for the full group duration", "Recommended use": "Normal conservative operational decision"},
        {"Method": "TIME_PHASED", "How the start is decided": "Each activity is assessed with its own limits at its forecast execution time", "Recommended use": "Approved procedures that explicitly allow changing limits by stage"},
    ]), use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Weather and multi-location setup")
        st.markdown("""
1. Define a unique Location ID for each port, transit route or offshore site.
2. Upload one weather CSV for every location referenced by an activity.
3. Map Timestamp, Wind10, Wind100, Hs, Tp and Current.
4. Use a consistent timezone and overlapping historical years at all used locations.
5. Every historical scenario uses the same year and timestamp at every location.
""")
        st.subheader("Project packages")
        st.markdown("""
- **Save project package** stores settings, locations, activities, curves and weather mappings.
- Select **Include uploaded weather CSV files** to make a self-contained, larger package.
- **Open project package** restores the saved project. Results are recalculated after opening.
""")
    with c2:
        st.subheader("Percentile interpretation")
        st.dataframe(pd.DataFrame([
            {"Metric": "Campaign duration, finish date and downtime", "P90 interpretation": "Higher / later / more conservative"},
            {"Metric": "Positions completed and workable hours", "P90 interpretation": "Lower / more conservative"},
            {"Metric": "P0", "P90 interpretation": "Deterministic no-weather campaign"},
        ]), use_container_width=True, hide_index=True)
        st.markdown("The selected-percentile downtime breakdown uses the complete historical simulation nearest to that campaign-duration percentile. It does not combine causes from different years.")
        st.subheader("P0, timestep and downtime")
        st.markdown("""
- **P0** uses exact learning-adjusted activity durations and does not change with the simulation timestep.
- The weather engine represents each activity with complete timestep blocks. The resulting **timestep adjustment** is reported separately.
- **Direct exceedance** means a criterion is already outside its limit.
- **Window pre-check** means conditions pass now but a future weather criterion blocks the required continuous window before it is complete.
- Downtime is attributed to the exact blocking criterion or criterion combination; the Hs-Tp curve remains recorded as the assessment basis when applicable.
- A scenario reaching the end of weather data is marked incomplete and excluded from percentile statistics.
""")
        st.subheader("Quick versus Full assessment")
        st.dataframe(pd.DataFrame([
            {"Mode": "Quick", "Purpose": "Annual, percentile, planning and milestone summaries", "Detailed QA trace": "No"},
            {"Mode": "Full", "Purpose": "All summary outputs plus selected-year operational trace", "Detailed QA trace": "Yes — compressed into consecutive operational intervals for faster generation and display"},
        ]), use_container_width=True, hide_index=True)

    st.subheader("Page reference")
    page_help = pd.DataFrame([
        {"Page": "01 Weather data", "Use": "Locations, weather uploads, mappings and data-quality checks."},
        {"Page": "02 Project input", "Use": "Excel project import, project package save/open and project summary."},
        {"Page": "03 Campaign settings", "Use": "Dates, positions, percentiles, hindcast range, detailed-results basis, activity locations and the default safe-to-safe method."},
        {"Page": "04 Activities", "Use": "Editable activities plus per-group safe-to-safe method, description and assessment location."},
        {"Page": "05 Hs–Tp curves", "Use": "Optional combined Hs–Tp operating envelopes."},
        {"Page": "06 Learning curve", "Use": "Cycle-based duration multipliers."},
        {"Page": "07 Generated sequence", "Use": "Expanded cycle/position sequence and deterministic P0 check."},
        {"Page": "08 Run assessment", "Use": "Validation, Quick/Full execution and run history."},
        {"Page": "09–13 Results", "Use": "Campaign, annual, planning, monthly and selected-year outputs."},
        {"Page": "14 QA and downtime", "Use": "Detailed Full-run trace, direct/window downtime and consolidated main-factor attribution."},
        {"Page": "15 Reports and export", "Use": "Traceable Excel workbook and PDF executive summary with tables and graphs."},
    ])
    st.dataframe(page_help, use_container_width=True, hide_index=True)

    st.subheader("Display precision")
    st.markdown("Calculated decimal values and percentages are displayed to **three decimal places** in the app, Excel output and PDF report. Raw uploaded weather data retains its source precision. Calculations continue at full internal precision.")

    st.info("All example durations and weather criteria must be verified against approved project procedures, vessel limits and assurance requirements.")
