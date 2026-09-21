"""Streamlit entry point. Start with: streamlit run app.py."""
from weather_assessment.ui_context import configure_ui, initialise_state, sidebar, PAGES
from weather_assessment.pages.guide import page_guide
from weather_assessment.pages.setup import page_weather, page_project_input, page_settings, page_activities, page_hstp, page_learning, page_sequence
from weather_assessment.pages.assessment import page_run
from weather_assessment.pages.results import page_campaign_summary, page_annual, page_planning, page_monthly, page_selected_year, page_qa
from weather_assessment.pages.exports import page_export


def main() -> None:
    configure_ui()
    initialise_state()
    selected_page = sidebar()
    page_functions = {
        PAGES[0]: page_guide,
        PAGES[1]: page_weather,
        PAGES[2]: page_project_input,
        PAGES[3]: page_settings,
        PAGES[4]: page_activities,
        PAGES[5]: page_hstp,
        PAGES[6]: page_learning,
        PAGES[7]: page_sequence,
        PAGES[8]: page_run,
        PAGES[9]: page_campaign_summary,
        PAGES[10]: page_annual,
        PAGES[11]: page_planning,
        PAGES[12]: page_monthly,
        PAGES[13]: page_selected_year,
        PAGES[14]: page_qa,
        PAGES[15]: page_export,
    }
    page_functions[selected_page]()


if __name__ == "__main__":
    main()
