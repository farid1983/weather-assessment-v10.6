from __future__ import annotations

import pandas as pd
import streamlit as st
from weather_assessment.statistics import successful_results
from weather_assessment.ui import fixed_bottom_turbine_html, page_header
from weather_assessment.validation import required_weather_locations
from weather_assessment.assessment import run_assessment
from weather_assessment.ui_context import (
    current_inputs,
    publish_assessment,
    show_validation,
    validation_errors,
)


def page_run() -> None:
    page_header("08", "Run assessment", "Validate inputs and execute synchronized historical simulations.")
    settings, locations, activities, bins, learning, groups = current_inputs()
    errors = validation_errors(require_weather=True)
    c1, c2, c3 = st.columns(3)
    validate_clicked = c1.button("Validate inputs", use_container_width=True)
    quick_clicked = c2.button("Run quick assessment", use_container_width=True)
    full_clicked = c3.button("Run full assessment", type="primary", use_container_width=True)
    if validate_clicked or errors:
        show_validation(errors)
    required = required_weather_locations(activities, groups)
    st.caption(f"{settings.total_positions} positions · {len(activities)} base activities · "
               f"{len(required)} required weather locations: {', '.join(sorted(required))}")
    mode = "full" if full_clicked else "quick" if quick_clicked else None
    if mode and not errors:
        progress = st.progress(0.0)
        detail = st.empty()
        indicator = st.empty()
        indicator.markdown(fixed_bottom_turbine_html(), unsafe_allow_html=True)
        def update_progress(done, total, year):
            progress.progress(done / total)
            detail.caption(f"Historical scenario {done} of {total} — start year {year}")
        try:
            run = run_assessment(settings, locations, activities, bins, learning, groups,
                                 st.session_state.weather_data,
                                 weather_configs=st.session_state.weather_configs,
                                 full=mode == "full", progress=update_progress)
            publish_assessment(run, mode)
            results = st.session_state.results
            st.session_state.run_history.insert(0, {
                "Started": st.session_state.last_run_at, "Mode": mode.title(),
                "Scenarios": len(results), "Successful": len(successful_results(results)),
                "Locations": len(required),
            })
            st.success(f"Completed {len(successful_results(results))} of {len(results)} historical scenarios.")
        except Exception as exc:
            st.error(str(exc))
        finally:
            indicator.empty()
            detail.empty()
    if st.session_state.run_history:
        st.subheader("Recent run history")
        st.dataframe(pd.DataFrame(st.session_state.run_history[:10]), use_container_width=True, hide_index=True)
