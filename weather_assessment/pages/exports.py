from __future__ import annotations

import streamlit as st
from weather_assessment.export import build_excel_export
from weather_assessment.pdf_report import build_pdf_report
from weather_assessment.ms_project import build_ms_project_xml
from weather_assessment.planning import detailed_results_basis_display, detailed_results_label
from weather_assessment.ui import page_header
from weather_assessment.ui_context import (
    APP_VERSION,
    current_detail,
    require_results,
    safe_filename,
)


def page_export() -> None:
    page_header("15", "Reports and export", "Generate reports from the completed assessment and selected detailed basis.")
    if not require_results():
        return
    settings = st.session_state.settings
    st.caption(f"Detailed results: {detailed_results_basis_display(settings)}")
    kind = st.radio("Report format", ["Excel workbook", "PDF summary", "Microsoft Project XML"], horizontal=True)
    key = (kind, settings.project_name, settings.detailed_results_basis, settings.year_of_interest, tuple(settings.percentiles))
    cache = st.session_state.setdefault("export_cache", {})
    if st.button("Generate report", type="primary"):
        try:
            run = st.session_state.assessment_run
            context = run.report_context(settings)
            detail = current_detail()
            if detail is None:
                raise ValueError("The selected detailed scenario did not complete or is unavailable. Select another basis.")
            label = detailed_results_label(settings)
            if kind == "Excel workbook":
                data = build_excel_export(**context, detailed_result=detail, app_version=APP_VERSION)
                extension, mime = "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif kind == "PDF summary":
                pdf_context = {name: value for name, value in context.items() if name not in {"bins", "learning_curve"}}
                data = build_pdf_report(**pdf_context, detailed_result=detail, app_version=APP_VERSION)
                extension, mime = "pdf", "application/pdf"
            else:
                data = build_ms_project_xml(settings=context["settings"], sequence=context["sequence"],
                                            result=detail, app_version=APP_VERSION, scenario_label=label)
                extension, mime = "xml", "application/xml"
            filename = f"{safe_filename(settings.project_name)}_{label}_v{APP_VERSION}.{extension}"
            cache[key] = (data, filename, mime)
        except Exception as exc:
            st.error(f"Report generation failed: {exc}")
    if key in cache:
        data, filename, mime = cache[key]
        st.download_button("Download report", data, filename, mime, use_container_width=True)
