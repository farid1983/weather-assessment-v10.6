from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from weather_assessment.defaults import default_activities, default_hstp_bins, default_learning_curve, default_locations, default_settings, safe_to_safe_groups_dataframe
from weather_assessment.input_workbook import build_project_input_workbook, load_project_input_workbook
from weather_assessment.models import CampaignSettings
from weather_assessment.planning import detailed_results_basis_display
from weather_assessment.project import deserialize_project
from weather_assessment.project_package import build_project_package, load_project_package
from weather_assessment.sequence import build_sequence, no_weather_summary, sequence_dataframe
from weather_assessment.ui import AMBER, GREEN, metric_card, page_header
from weather_assessment.validation import validate_inputs
from weather_assessment.assessment import simulation_settings
from weather_assessment.policies import SUPPORTED_TIMESTEPS
from weather_assessment.weather import auto_preview, common_weather_coverage, load_weather_csv, weather_qa
from weather_assessment.ui_context import (
    APP_ROOT,
    APP_VERSION,
    GROUP_COLUMNS,
    _decimal_axes,
    _result_table,
    apply_project_inputs,
    clear_results,
    current_inputs,
    dataframe_to_activities,
    dataframe_to_locations,
    dataframe_to_safe_to_safe_groups,
    default_column,
    load_saved_weather,
    safe_filename,
    show_validation,
)


def page_weather() -> None:
    page_header("01", "Weather data", "Review the three work locations and their weather data. The bundled example assigns the same reconciled CSV to PORT, TRANSIT and OFFSHORE.")
    current_locations = dataframe_to_locations(st.session_state.locations_df)
    used_location_ids = {item.location_id for item in dataframe_to_activities(st.session_state.activities_df)}
    loaded_location_ids = set(st.session_state.weather_data)
    coverage_now = common_weather_coverage(st.session_state.weather_data) if st.session_state.weather_data else None
    overview = st.columns(4)
    with overview[0]: metric_card("Locations defined", str(len(current_locations)), note="Port, transit, offshore or other")
    with overview[1]: metric_card("Locations used", str(len(used_location_ids)), note=", ".join(sorted(used_location_ids)) or "No activities assigned")
    with overview[2]: metric_card("Weather files ready", str(len(loaded_location_ids)), note=f"of {len(used_location_ids)} required", accent=GREEN if used_location_ids <= loaded_location_ids else AMBER)
    with overview[3]: metric_card("Common coverage", f"{coverage_now[0]:%Y}–{coverage_now[1]:%Y}" if coverage_now else "—", note="Synchronized historical clock")
    st.subheader("Location register")
    original = st.session_state.locations_df.copy()
    edited = st.data_editor(
        original,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "location_id": st.column_config.TextColumn("Location ID"),
            "name": st.column_config.TextColumn("Location name"),
            "location_type": st.column_config.SelectboxColumn("Type", options=["Port", "Transit", "Offshore", "Other"]),
            "timezone": st.column_config.TextColumn("Operational time zone", help="Allowed-time windows use this location timezone; campaign timestamps use UTC."),
            "weather_filename": st.column_config.TextColumn("Weather file name", disabled=True),
            "notes": st.column_config.TextColumn("Notes"),
        },
        key="locations_editor",
    )
    if not edited.equals(original):
        old_ids = set(original["location_id"].dropna().astype(str))
        new_ids = set(edited["location_id"].dropna().astype(str))
        for removed in old_ids - new_ids:
            for store in ("weather_files", "weather_configs", "weather_data", "weather_qa"):
                st.session_state[store].pop(removed, None)
        st.session_state.locations_df = edited
        clear_results()

    locations = dataframe_to_locations(st.session_state.locations_df)
    if not locations:
        st.warning("Add at least one location.")
        return

    tabs = st.tabs([item.location_id for item in locations])
    for tab, location in zip(tabs, locations):
        with tab:
            st.markdown(f"### {location.name}")
            st.caption(f"{location.location_type} location • {location.timezone}")
            qa = st.session_state.weather_qa.get(location.location_id)
            if qa:
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    filename = st.session_state.weather_configs[location.location_id].get("filename", "CSV")
                    metric_card("Detected file", filename, note=f"{qa.row_count:,} rows", wrap=True, tooltip=filename)
                with m2: metric_card("Date coverage", qa.start.strftime("%Y-%m-%d"), note=f"to {qa.end:%Y-%m-%d}")
                with m3: metric_card("Time resolution", f"{qa.inferred_step_hours:g}", "h", f"{len(qa.available_years)} calendar years")
                with m4: metric_card("Status", "Ready", note="Parsed and available", accent=GREEN)

            upload = st.file_uploader(
                f"Upload weather CSV for {location.name}",
                type=["csv", "txt"],
                key=f"weather_upload_{location.location_id}",
            )
            if upload is not None:
                data = upload.getvalue()
                try:
                    preview, guessed_skip = auto_preview(data)
                    columns = list(preview.columns)
                    c1, c2, c3 = st.columns([1, 1, 2])
                    with c1:
                        skip_rows = st.number_input("Rows before header", min_value=0, max_value=100, value=int(guessed_skip), key=f"skip_{location.location_id}")
                    with c2:
                        delimiter = st.selectbox("Delimiter", ["Auto", ",", ";", "\t", "|"], key=f"delimiter_{location.location_id}")
                    with c3:
                        st.markdown("**Column mapping**")
                    mapping_cols = st.columns(3)
                    with mapping_cols[0]:
                        timestamp_col = st.selectbox("Timestamp", columns, index=columns.index(default_column(columns, ["timestamp", "date", "time"], 0)), key=f"timestamp_{location.location_id}")
                        wind10_col = st.selectbox("Wind10 [m/s]", columns, index=columns.index(default_column(columns, ["wind10", "ws10", "u10"], 1)), key=f"wind10_{location.location_id}")
                    with mapping_cols[1]:
                        wind100_col = st.selectbox("Wind100 [m/s]", columns, index=columns.index(default_column(columns, ["wind100", "ws100", "u100"], 2)), key=f"wind100_{location.location_id}")
                        hs_col = st.selectbox("Hs [m]", columns, index=columns.index(default_column(columns, ["hs", "waveheight"], 3)), key=f"hs_{location.location_id}")
                    with mapping_cols[2]:
                        tp_col = st.selectbox("Tp [s]", columns, index=columns.index(default_column(columns, ["tp", "peakperiod"], 4)), key=f"tp_{location.location_id}")
                        current_col = st.selectbox("Current [m/s]", columns, index=columns.index(default_column(columns, ["current", "vc"], 5)), key=f"current_{location.location_id}")
                    date_cols = st.columns(2)
                    with date_cols[0]: dayfirst = st.checkbox("Day-first dates", value=False, key=f"dayfirst_{location.location_id}")
                    with date_cols[1]: date_format = st.text_input("Optional timestamp format", placeholder="e.g. %Y-%m-%d %H:%M:%S", key=f"datefmt_{location.location_id}")
                    source_timezone = st.text_input("CSV source timezone for timestamps without an offset", value="UTC", key=f"source_timezone_{location.location_id}")
                    if st.button("Validate and use this weather file", type="primary", key=f"load_weather_{location.location_id}"):
                        config = {
                            "filename": upload.name,
                            "skip_rows": int(skip_rows),
                            "delimiter": delimiter,
                            "column_map": {"timestamp": timestamp_col, "wind10": wind10_col, "wind100": wind100_col, "hs": hs_col, "tp": tp_col, "current": current_col},
                            "dayfirst": bool(dayfirst),
                            "date_format": date_format or None,
                            "source_timezone": source_timezone,
                        }
                        load_saved_weather(location.location_id, data, config)
                        mask = st.session_state.locations_df["location_id"].astype(str) == location.location_id
                        st.session_state.locations_df.loc[mask, "weather_filename"] = upload.name
                        clear_results()
                        st.success(f"{upload.name} loaded for {location.location_id}.")
                        st.rerun()
                    st.dataframe(preview.head(10), use_container_width=True, hide_index=True)
                except Exception as exc:
                    st.error(str(exc))
            elif qa:
                frame = st.session_state.weather_data[location.location_id]
                st.subheader("Data quality")
                checks = pd.DataFrame([
                    {"Check": "Missing weather values", "Result": sum(qa.missing_values.values()), "Status": "Pass" if sum(qa.missing_values.values()) == 0 else "Error"},
                    {"Check": "Duplicate timestamps", "Result": qa.duplicate_timestamps, "Status": "Pass" if qa.duplicate_timestamps == 0 else "Error"},
                    {"Check": "Irregular intervals", "Result": qa.irregular_intervals, "Status": "Pass" if qa.irregular_intervals == 0 else "Warning"},
                    {"Check": "Usable years", "Result": len(qa.available_years), "Status": "Pass"},
                ])
                st.dataframe(checks, use_container_width=True, hide_index=True)
                st.dataframe(frame.head(10), use_container_width=True, hide_index=True)
                if st.button("Remove weather file", key=f"remove_weather_{location.location_id}"):
                    for store in ("weather_files", "weather_configs", "weather_data", "weather_qa"):
                        st.session_state[store].pop(location.location_id, None)
                    clear_results()
                    st.rerun()

    used = {item.location_id for item in dataframe_to_activities(st.session_state.activities_df)}
    loaded = set(st.session_state.weather_data)
    st.subheader("Location coverage summary")
    rows = []
    for location in locations:
        qa = st.session_state.weather_qa.get(location.location_id)
        rows.append({
            "Location ID": location.location_id,
            "Location": location.name,
            "Used by activities": "Yes" if location.location_id in used else "No",
            "Weather loaded": "Yes" if qa else "No",
            "Start": qa.start if qa else None,
            "End": qa.end if qa else None,
            "Resolution [h]": qa.inferred_step_hours if qa else None,
        })
    st.dataframe(_result_table(pd.DataFrame(rows)), use_container_width=True, hide_index=True)
    required_loaded = used <= loaded
    coverage = common_weather_coverage({key: value for key, value in st.session_state.weather_data.items() if key in used}) if required_loaded and used else None
    if coverage:
        st.success(f"Common used-location coverage: {coverage[0]:%Y-%m-%d %H:%M} to {coverage[1]:%Y-%m-%d %H:%M}.")
    elif used - loaded:
        st.warning("Weather is still required for: " + ", ".join(sorted(used - loaded)))


def page_project_input() -> None:
    page_header("02", "Project input", "Use the bundled YHO FEM2 workbook as the reviewed example template, import another workbook, or save and reopen a complete multi-location project.")
    settings, locations, activities, bins, learning, groups = current_inputs()
    blank = build_project_input_workbook(default_settings(), default_locations(), default_activities(), default_hstp_bins(), default_learning_curve(), [], APP_VERSION)
    current = build_project_input_workbook(settings, locations, activities, bins, learning, groups, APP_VERSION)
    c1, c2, c3 = st.columns(3)
    c1.download_button("Download blank workbook", blank, "Blank_Project_Input_MultiLocation.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    c2.download_button("Download current inputs", current, f"{safe_filename(settings.project_name)}_Project_Input.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    example_path = APP_ROOT / "Example_Project_Input.xlsx"
    example_bytes = example_path.read_bytes() if example_path.exists() else current
    c3.download_button("Download YHO FEM2 example workbook", example_bytes, "YHO_FEM2_Project_Input_MultiLocation_v0_10_5.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    st.subheader("Import project-input workbook")
    project_xlsx = st.file_uploader("Upload completed project-input workbook", type=["xlsx"], key="project_xlsx_upload")
    if project_xlsx is not None:
        try:
            loaded_settings, loaded_locations, loaded_activities, loaded_bins, loaded_learning, loaded_groups = load_project_input_workbook(project_xlsx.getvalue())
            errors = validate_inputs(loaded_settings, loaded_activities, loaded_bins, loaded_learning, loaded_locations, safe_to_safe_groups=loaded_groups)
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Locations", len(loaded_locations))
            s2.metric("Activities", len(loaded_activities))
            s3.metric("Hs–Tp rows", len(loaded_bins))
            s4.metric("Validation issues", len(errors))
            show_validation(errors)
            if st.button("Apply imported workbook", type="primary", disabled=bool(errors)):
                apply_project_inputs(loaded_settings, loaded_locations, loaded_activities, loaded_bins, loaded_learning, loaded_groups)
                st.session_state.project_import_message = f"Imported {project_xlsx.name}"
                st.success("Project workbook applied.")
                st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.subheader("Save / open project package")
    include_weather = st.checkbox("Include uploaded weather CSV files in the saved package", value=True)
    package = build_project_package(
        settings, locations, activities, bins, learning, groups,
        st.session_state.weather_configs,
        st.session_state.weather_files,
        APP_VERSION,
        include_weather=include_weather,
    )
    p1, p2 = st.columns(2, gap="large")
    with p1:
        with st.container(border=True):
            st.markdown("**Save project package**")
            st.download_button(
                "Save project package",
                package,
                f"{safe_filename(settings.project_name)}.waproject",
                "application/zip",
                type="primary",
                use_container_width=True,
            )
    with p2:
        with st.container(border=True):
            st.markdown("**Open project package**")
            project_package = st.file_uploader(
                "Select .waproject or ZIP file",
                type=["waproject", "zip"],
                key="project_package_upload",
                label_visibility="collapsed",
            )
            open_project_clicked = st.button(
                "Open project package",
                type="primary",
                use_container_width=True,
                disabled=project_package is None,
                key="open_project_package_button",
            )
    if project_package is not None and open_project_clicked:
        try:
            project_text, weather_files = load_project_package(project_package.getvalue())
            loaded_settings, loaded_locations, loaded_activities, loaded_bins, loaded_learning, loaded_groups, weather_configs = deserialize_project(project_text)
            errors = validate_inputs(loaded_settings, loaded_activities, loaded_bins, loaded_learning,
                                     loaded_locations, safe_to_safe_groups=loaded_groups)
            if errors:
                raise ValueError("\n".join(errors))
            parsed_weather, parsed_qa = {}, {}
            for location_id, content in weather_files.items():
                config = weather_configs.get(location_id)
                if not config:
                    raise ValueError(f"Weather configuration missing for {location_id}.")
                frame = load_weather_csv(content, int(config.get("skip_rows", 0)),
                                         config.get("delimiter", "Auto"), config["column_map"],
                                         dayfirst=bool(config.get("dayfirst", True)), date_format=config.get("date_format") or None,
                                         source_timezone=config.get("source_timezone", "UTC"))
                parsed_qa[location_id] = weather_qa(frame)
                parsed_weather[location_id] = frame
            apply_project_inputs(loaded_settings, loaded_locations, loaded_activities, loaded_bins, loaded_learning, loaded_groups)
            st.session_state.weather_files = weather_files
            st.session_state.weather_configs = {key: weather_configs[key] for key in weather_files}
            st.session_state.weather_data = parsed_weather
            st.session_state.weather_qa = parsed_qa
            st.success("Project package opened.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.subheader("Current project summary")
    st.dataframe(pd.DataFrame([
        {"Item": "Project", "Value": str(settings.project_name)},
        {"Item": "Planning year", "Value": str(settings.nominal_year)},
        {"Item": "Locations", "Value": str(len(locations))},
        {"Item": "Activities", "Value": str(len(activities))},
        {"Item": "Weather files loaded", "Value": str(len(st.session_state.weather_data))},
    ]), use_container_width=True, hide_index=True)


def page_settings() -> None:
    page_header("03", "Campaign settings", "Define planning dates, positions, percentiles, simulation period and activity locations.")
    current = st.session_state.settings
    with st.form("settings_form"):
        c1, c2 = st.columns(2)
        with c1:
            project_name = st.text_input("Project / scenario name", current.project_name)
            nominal_year = st.number_input("Planning year", min_value=2000, max_value=2200, value=int(current.nominal_year))
            date_cols = st.columns(2)
            start_month = date_cols[0].number_input("Start month", 1, 12, int(current.start_month))
            start_day = date_cols[1].number_input("Start day", 1, 31, int(current.start_day))
            total_positions = st.number_input("Total positions", 1, 10000, int(current.total_positions))
            positions_per_cycle = st.number_input("Positions per cycle", 1, 10000, int(current.positions_per_cycle))
        with c2:
            percentile_cols = st.columns(3)
            p1 = percentile_cols[0].number_input("Percentile 1", 0.0, 100.0, float(current.percentiles[0]))
            p2 = percentile_cols[1].number_input("Percentile 2", 0.0, 100.0, float(current.percentiles[1]))
            p3 = percentile_cols[2].number_input("Percentile 3", 0.0, 100.0, float(current.percentiles[2]))
            timestep = st.selectbox("Simulation time step [h]", SUPPORTED_TIMESTEPS, index=SUPPORTED_TIMESTEPS.index(float(current.timestep_hours)) if float(current.timestep_hours) in SUPPORTED_TIMESTEPS else 0)
            years = sorted(set.intersection(*[set(item.available_years) for item in st.session_state.weather_qa.values()])) if st.session_state.weather_qa else []
            percentile_basis = [
                (f"Percentile {index} representative hindcast year (P{percentile:g})", f"Percentile {index} representative hindcast year")
                for index, percentile in enumerate(current.percentiles, start=1)
                if float(percentile) != 0.0
            ]
            basis_display_to_value = {display: value for display, value in percentile_basis}
            basis_display_to_value["P0 (no weather)"] = "P0 (no weather)"
            detailed_options = ["P0 (no weather)"] + [display for display, _ in percentile_basis] + [str(year) for year in years]
            current_display = detailed_results_basis_display(current)
            if current.detailed_results_basis == "Specific hindcast year" and current.year_of_interest is not None:
                current_display = str(int(current.year_of_interest))
                if current_display not in detailed_options:
                    detailed_options.append(current_display)
            if current_display not in detailed_options:
                current_display = detailed_options[0]
            selected_detail_basis = st.selectbox(
                "Detailed results basis",
                detailed_options,
                index=detailed_options.index(current_display),
                help="Choose deterministic P0, a representative hindcast year nearest to Percentile 1, 2 or 3, or one available historical year for targeted QA review.",
            )
            if selected_detail_basis in basis_display_to_value:
                detailed_results_basis = basis_display_to_value[selected_detail_basis]
                year_of_interest = None
            else:
                detailed_results_basis = "Specific hindcast year"
                year_of_interest = int(selected_detail_basis)
            h1, h2 = st.columns(2)
            hindcast_start = h1.number_input("Hindcast start year (0 = automatic)", min_value=0, max_value=2200, value=int(current.hindcast_start_year or 0))
            hindcast_end = h2.number_input("Hindcast end year (0 = automatic)", min_value=0, max_value=2200, value=int(current.hindcast_end_year or 0))
            method_options = ["MOST_STRINGENT", "TIME_PHASED"]
            default_group_method = st.selectbox(
                "Default safe-to-safe assessment method",
                method_options,
                index=method_options.index(current.default_safe_to_safe_method) if current.default_safe_to_safe_method in method_options else 0,
                help="MOST_STRINGENT applies the lowest group limits over the full safe-to-safe duration. TIME_PHASED applies each activity's own limits during its expected execution period.",
            )
        submitted = st.form_submit_button("Apply campaign settings", type="secondary")
    if submitted:
        st.session_state.settings = CampaignSettings(
            project_name=project_name,
            nominal_year=int(nominal_year),
            start_month=int(start_month),
            start_day=int(start_day),
            positions_per_cycle=int(positions_per_cycle),
            total_positions=int(total_positions),
            percentiles=(float(p1), float(p2), float(p3)),
            timestep_hours=float(timestep),
            detailed_results_basis=detailed_results_basis,
            year_of_interest=int(year_of_interest) if year_of_interest is not None else None,
            hindcast_start_year=int(hindcast_start) or None,
            hindcast_end_year=int(hindcast_end) or None,
            default_safe_to_safe_method=default_group_method,
        )
        if simulation_settings(current) != simulation_settings(st.session_state.settings):
            clear_results()
        else:
            st.session_state.detail_cache = {}
            st.session_state.export_cache = {}
        st.success("Campaign settings updated.")

    st.subheader("Activity location assignments")
    activity_frame = st.session_state.activities_df.copy()
    assignment = activity_frame[["activity_id", "description", "location_id"]]
    location_options = [item.location_id for item in dataframe_to_locations(st.session_state.locations_df)]
    edited = st.data_editor(
        assignment,
        use_container_width=True,
        hide_index=True,
        disabled=["activity_id", "description"],
        column_config={"location_id": st.column_config.SelectboxColumn("Work location", options=location_options, required=True)},
        key="settings_location_assignments",
    )
    if not edited.equals(assignment):
        lookup = edited.set_index("activity_id")["location_id"].to_dict()
        st.session_state.activities_df["location_id"] = st.session_state.activities_df["activity_id"].map(lookup).fillna(st.session_state.activities_df["location_id"])
        clear_results()


def page_activities() -> None:
    page_header("04", "Activities", "Define the sequence, duration, work location and weather criteria for each operation.")
    activity_snapshot = dataframe_to_activities(st.session_state.activities_df)
    locations = dataframe_to_locations(st.session_state.locations_df)
    activity_cards = st.columns(6)
    with activity_cards[0]: metric_card("Activities", str(len(activity_snapshot)), note="Editable campaign operations")
    with activity_cards[1]: metric_card("Type 1", str(sum(a.activity_type == 1 for a in activity_snapshot)), note="Start of cycle")
    with activity_cards[2]: metric_card("Type 2", str(sum(a.activity_type == 2 for a in activity_snapshot)), note="Repeated per position")
    with activity_cards[3]: metric_card("Type 3", str(sum(a.activity_type == 3 for a in activity_snapshot)), note="End of cycle")
    with activity_cards[4]: metric_card("Work locations", str(len({a.location_id for a in activity_snapshot})), note="Assigned weather sources")
    with activity_cards[5]: metric_card("Safe-to-safe groups", str(len({a.safe_to_safe_group for a in activity_snapshot if a.safe_to_safe_group})), note="Commitment sequences")
    st.subheader("Activity register")
    location_options = [item.location_id for item in locations]
    curve_options = ["None"] + sorted(set(st.session_state.hstp_df["curve"].dropna().astype(str)))
    original = st.session_state.activities_df.copy()
    edited = st.data_editor(
        original,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        height=560,
        column_config={
            "activity_id": st.column_config.NumberColumn("Activity ID", step=1, required=True),
            "activity_type": st.column_config.SelectboxColumn("Type", options=[1, 2, 3], required=True),
            "no_learning_curve": st.column_config.CheckboxColumn("No learning curve"),
            "milestone": st.column_config.CheckboxColumn("Position complete"),
            "description": st.column_config.TextColumn("Description", width="large", required=True),
            "location_id": st.column_config.SelectboxColumn("Work location", options=location_options, required=True),
            "safe_to_safe_group": st.column_config.TextColumn("Safe-to-safe group", help="Use the same Group ID on consecutive activities that require one complete forecast window before starting."),
            "duration_hours": st.column_config.NumberColumn("Duration [h]", min_value=0.0, format="%.3f"),
            "weather_window_hours": st.column_config.NumberColumn("Weather window [h]", min_value=0.0, format="%.3f"),
            "wind10_limit": st.column_config.NumberColumn("Wind10 [m/s]", format="%.3f"),
            "wind100_limit": st.column_config.NumberColumn("Wind100 [m/s]", format="%.3f"),
            "hs_limit": st.column_config.NumberColumn("Hs [m]", format="%.3f"),
            "tp_limit": st.column_config.NumberColumn("Tp [s]", format="%.3f"),
            "current_limit": st.column_config.NumberColumn("Current [m/s]", format="%.3f"),
            "hstp_curve": st.column_config.SelectboxColumn("Hs–Tp curve", options=curve_options),
            "remarks": st.column_config.TextColumn("Remarks", width="large"),
        },
        key="activities_editor",
    )
    if not edited.equals(original):
        st.session_state.activities_df = edited
        clear_results()

    edited_activities = dataframe_to_activities(edited)
    used_group_ids = sorted({item.safe_to_safe_group for item in edited_activities if item.safe_to_safe_group})
    existing_groups = {item.group_id: item for item in dataframe_to_safe_to_safe_groups(st.session_state.safe_to_safe_groups_df)}
    group_rows = []
    for group_id in used_group_ids:
        members = [item for item in edited_activities if item.safe_to_safe_group == group_id]
        member_locations = sorted({item.location_id for item in members})
        existing = existing_groups.get(group_id)
        group_rows.append({
            "group_id": group_id,
            "description": existing.description if existing and existing.description else (f"{members[0].description} to {members[-1].description}" if members else group_id),
            "assessment_method": existing.assessment_method if existing else st.session_state.settings.default_safe_to_safe_method,
            "assessment_location": existing.assessment_location if existing and existing.assessment_location else (member_locations[0] if len(member_locations) == 1 else ""),
            "notes": existing.notes if existing else "",
        })
    group_frame = pd.DataFrame(group_rows, columns=GROUP_COLUMNS)
    st.subheader("Safe-to-safe group settings")
    st.caption("The project default is used when a group is first created. Each group can then override the assessment method.")
    if group_frame.empty:
        st.info("No safe-to-safe groups are currently defined in the activity register.")
        if not st.session_state.safe_to_safe_groups_df.empty:
            st.session_state.safe_to_safe_groups_df = safe_to_safe_groups_dataframe([])
    else:
        edited_groups = st.data_editor(
            group_frame,
            use_container_width=True,
            hide_index=True,
            disabled=["group_id"],
            column_config={
                "group_id": st.column_config.TextColumn("Group ID"),
                "description": st.column_config.TextColumn("Description", width="large"),
                "assessment_method": st.column_config.SelectboxColumn(
                    "Assessment method", options=["MOST_STRINGENT", "TIME_PHASED"], required=True,
                    help="MOST_STRINGENT uses the lowest group limits for the full duration. TIME_PHASED checks each activity at its expected time."
                ),
                "assessment_location": st.column_config.SelectboxColumn(
                    "Assessment location", options=[""] + location_options,
                    help="Required for MOST_STRINGENT when group activities use more than one location."
                ),
                "notes": st.column_config.TextColumn("Notes", width="large"),
            },
            key="safe_to_safe_group_editor",
        )
        if not edited_groups.equals(st.session_state.safe_to_safe_groups_df):
            st.session_state.safe_to_safe_groups_df = edited_groups
            clear_results()

        preview_rows = []
        group_lookup = {item.group_id: item for item in dataframe_to_safe_to_safe_groups(edited_groups)}
        for group_id in used_group_ids:
            members = [item for item in edited_activities if item.safe_to_safe_group == group_id]
            config = group_lookup[group_id]
            valid_limits = {
                "Wind10 [m/s]": min([item.wind10_limit for item in members if item.wind10_limit > 0], default=None),
                "Wind100 [m/s]": min([item.wind100_limit for item in members if item.wind100_limit > 0], default=None),
                "Hs [m]": min([item.hs_limit for item in members if item.hs_limit > 0], default=None),
                "Tp [s]": min([item.tp_limit for item in members if item.tp_limit > 0], default=None),
                "Current [m/s]": min([item.current_limit for item in members if item.current_limit > 0], default=None),
            }
            preview_rows.append({
                "Group": group_id,
                "Method": config.assessment_method,
                "Activities": len(members),
                "Base duration before learning [h]": sum(item.duration_hours for item in members),
                "Assessment location": config.assessment_location or "Activity locations",
                "Standalone limits": (", ".join(f"{key} ≤ {value:g}" for key, value in valid_limits.items() if value is not None) if config.assessment_method == "MOST_STRINGENT" else "Per-activity limits; see generated sequence"),
            })
        st.dataframe(_result_table(pd.DataFrame(preview_rows)), use_container_width=True, hide_index=True)


def page_hstp() -> None:
    page_header("05", "Hs–Tp curves", "Define optional combined significant-wave-height and peak-period operating envelopes.")
    original = st.session_state.hstp_df.copy()
    edited = st.data_editor(
        original,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "curve": st.column_config.TextColumn("Curve", required=True),
            "tp_from": st.column_config.NumberColumn("Tp from [s]", format="%.3f"),
            "tp_to": st.column_config.NumberColumn("Tp to [s]", format="%.3f"),
            "hs_max": st.column_config.NumberColumn("Hs maximum [m]", format="%.3f"),
        },
        key="hstp_editor",
    )
    if not edited.equals(original):
        st.session_state.hstp_df = edited
        clear_results()
    curves = sorted(set(edited["curve"].dropna().astype(str)))
    if curves:
        selected = st.selectbox("Curve preview", curves)
        subset = edited[edited["curve"].astype(str) == selected].sort_values("tp_from")
        if not subset.empty:
            fig = go.Figure()
            x, y = [], []
            previous_end = None
            for row in subset.itertuples():
                if previous_end is not None and float(row.tp_from) > previous_end:
                    x.append(None)
                    y.append(None)
                x.extend([float(row.tp_from), float(row.tp_to)])
                y.extend([float(row.hs_max), float(row.hs_max)])
                previous_end = float(row.tp_to)
            st.caption("Gaps are outside the curve domain. At shared endpoints the preceding bin governs, matching the calculation engine.")
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers", line_shape="hv", fill="tozeroy", name=selected))
            fig.update_layout(title=f"Operating envelope — {selected}", xaxis_title="Tp [s]", yaxis_title="Maximum Hs [m]", height=420)
            st.plotly_chart(_decimal_axes(fig, x=True, y=True), use_container_width=True)


def page_learning() -> None:
    page_header("06", "Learning curve", "Apply a cycle-based duration multiplier to activities that allow learning.")
    original = st.session_state.learning_df.copy()
    c1, c2 = st.columns([1, 2])
    with c1:
        edited = st.data_editor(
            original,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "cycle": st.column_config.NumberColumn("Cycle", min_value=1, step=1),
                "multiplier": st.column_config.NumberColumn("Duration multiplier", min_value=0.01, format="%.3f"),
            },
            key="learning_editor",
        )
        if not edited.equals(original):
            st.session_state.learning_df = edited
            clear_results()
    with c2:
        chart = edited.dropna(subset=["cycle", "multiplier"]).sort_values("cycle")
        if not chart.empty:
            learning_fig = px.line(chart, x="cycle", y="multiplier", markers=True, title="Learning multiplier by cycle")
            st.plotly_chart(_decimal_axes(learning_fig, y=True), use_container_width=True)
    activities = dataframe_to_activities(st.session_state.activities_df)
    sample = next((item for item in activities if not item.no_learning_curve), None)
    if sample and not edited.empty:
        impact = edited.dropna().copy()
        impact["Base duration [h]"] = sample.duration_hours
        impact["Adjusted duration [h]"] = impact["multiplier"] * sample.duration_hours
        st.subheader(f"Impact example — {sample.description}")
        st.dataframe(_result_table(impact[["cycle", "multiplier", "Base duration [h]", "Adjusted duration [h]"]]), use_container_width=True, hide_index=True)


def page_sequence() -> None:
    page_header("07", "Generated sequence", "Review the expanded cycle and position sequence before running the assessment.")
    settings, locations, activities, bins, learning, groups = current_inputs()
    errors = validate_inputs(settings, activities, bins, learning, locations, loaded_weather_locations=None, safe_to_safe_groups=groups)
    if errors:
        show_validation(errors)
        return
    try:
        sequence = build_sequence(settings, activities, learning, groups, locations)
        p0 = no_weather_summary(sequence, settings)
        st.session_state.sequence = sequence
        st.session_state.p0_summary = p0
        frame = sequence_dataframe(sequence)

        cards = st.columns(5)
        cards[0].metric("Sequence rows", f"{len(frame):,}")
        cards[1].metric("Cycles", int(frame["cycle"].max()) if not frame.empty else 0)
        cards[2].metric("Positions", settings.total_positions)
        cards[3].metric("P0 duration", f"{p0['duration_days']:.3f} days")
        group_count = frame.loc[frame["safe_to_safe_group"].astype(str).str.strip() != "", "safe_to_safe_group"].nunique()
        cards[4].metric("Safe-to-safe groups", int(group_count))

        filters = st.columns(5)
        cycle_values = sorted(frame["cycle"].dropna().unique().tolist())
        position_values = sorted(frame["position"].dropna().unique().tolist())
        location_values = sorted(frame["location_id"].dropna().astype(str).unique().tolist())
        group_values = sorted(item for item in frame["safe_to_safe_group"].dropna().astype(str).unique().tolist() if item.strip())
        selected_cycles = filters[0].multiselect("Cycle", cycle_values)
        selected_positions = filters[1].multiselect("Position", position_values)
        selected_locations = filters[2].multiselect("Work location", location_values)
        selected_groups = filters[3].multiselect("Safe-to-safe group", group_values)
        search_text = filters[4].text_input("Activity search")

        display = frame
        if selected_cycles:
            display = display[display["cycle"].isin(selected_cycles)]
        if selected_positions:
            display = display[display["position"].isin(selected_positions)]
        if selected_locations:
            display = display[display["location_id"].astype(str).isin(selected_locations)]
        if selected_groups:
            display = display[display["safe_to_safe_group"].astype(str).isin(selected_groups)]
        if search_text:
            display = display[display["description"].astype(str).str.contains(search_text, case=False, na=False, regex=False)]

        display_columns = {
            "sequence_no": "Sequence",
            "cycle": "Cycle",
            "position": "Position",
            "activity_id": "Activity ID",
            "activity_type": "Type",
            "learning_multiplier": "Learning factor",
            "milestone": "Position complete",
            "description": "Description",
            "location_id": "Work location",
            "safe_to_safe_group": "Safe-to-safe group",
            "group_role": "Group role",
            "group_method": "Group method",
            "group_assessment_location": "Group assessment location",
            "duration_hours": "Duration [h]",
            "weather_window_hours": "Weather window [h]",
            "wind10_limit": "Wind10 [m/s]",
            "wind100_limit": "Wind100 [m/s]",
            "hs_limit": "Hs [m]",
            "tp_limit": "Tp [s]",
            "current_limit": "Current [m/s]",
            "time_start": "Start hour",
            "time_end": "End hour",
            "hstp_curve": "Hs–Tp curve",
            "remarks": "Remarks",
        }
        st.dataframe(_result_table(display.rename(columns=display_columns)), use_container_width=True, hide_index=True, height=620)
        st.download_button(
            "Download generated sequence CSV",
            frame.to_csv(index=False).encode("utf-8"),
            f"{safe_filename(settings.project_name)}_generated_sequence.csv",
            "text/csv",
        )
    except Exception as exc:
        st.error(str(exc))
