# Build status — v0.10.6

Implemented:

- Explicit deterministic P0 detailed-results basis.
- Always-present OUT_P0 run exact continuous no-weather trace.
- P0 bug correction: zero WDT, no representative hindcast year and no timestep adjustment.
- Selected-basis OUT_run, PDF and Microsoft Project XML, including P0 and specific years.
- Dynamic OUT_<basis> DT and new OUT_<basis> DT detail sheets for weather scenarios.
- Exact weather-cause combinations replacing generic Multiple criteria attribution.
- Direct exceedance / Window pre-check retained as mechanisms, not causes.
- PDF Cause of downtime and Activities driving downtime sections.
- Statistical vs representative duration and position-completion vs campaign-completion clarification.
- Proper Generated datetime formatting and three-decimal calculated metadata display.
- Simplified basis-neutral Page 15 export workflow retained.
- Removed MFA sidebar footer wording.

Verification:

- 23 automated tests pass.
- Rev.2K_3 validation: 44/45 completed hindcast simulations.
- Rev.2K_3 Exact P0 = 2,747.900 h = 114.496 d with WDT = 0 and timestep adjustment = 0.
- Rev.2K_3 statistical P50 = 169.198 d; representative P50 = 1984 at 169.156 d.
- P50 Excel export includes OUT_P0 run, OUT_P50 DT and OUT_P50 DT detail.
- P0 Excel export omits weather-detail sheets and OUT_run reconciles to exact P0.
- P50 PDF renders to 11 pages; P0 PDF renders without weather-downtime pages.
