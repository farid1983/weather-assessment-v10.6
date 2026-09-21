# Changelog

## v0.10.6
- Added explicit deterministic P0 detailed-results basis with zero weather downtime and no timestep adjustment.
- Added always-present OUT_P0 run exact continuous no-weather trace.
- Added OUT_<basis> DT detail Activity x Cause matrix for weather scenarios.
- Replaced generic Multiple criteria downtime labels with exact weather criterion combinations.
- Separated weather cause from Direct exceedance / Window pre-check mechanism.
- Added PDF cause-of-downtime and activities-driving-downtime sections.
- Clarified statistical vs representative duration and final-position vs full-campaign completion.
- Added P0 PDF/XML handling and removed MFA sidebar wording.

## v0.10.5

- Routed detailed Excel, PDF and Microsoft Project XML exports through the Campaign settings Detailed results basis instead of hard-wiring P50.
- Added dynamic selected-detail labels to `OUT_run` and renamed the detailed downtime sheet to `OUT_<basis> DT`.
- Formatted Assessment metadata `Generated` as a true Excel datetime and calculated metadata to three decimals.
- Removed the separate PDF representative-detail percentile selector.
- Simplified Microsoft Project XML export to one generate/download control and removed P50-only wording, summary cards and the review CSV control.
- Changed XML planning semantics so native Duration is baseline productive duration and `Duration WDT [days]` is a separate custom field while Start/Finish preserve the simulated selected schedule.
- Made XML tasks manually scheduled and removed actual/remaining-duration progress fields.
- Removed invalid `24:00:00` XML time values.
- Added dynamic detail-sheet and XML regression tests; 22 automated tests pass.

## v0.10.4

- Added a P50 Microsoft Project XML generator to Page 15.
- Grouped the XML hierarchy by campaign cycle, with one summary row for each cycle and its positions.
- Aggregated weather waiting into each affected activity instead of exporting separate waiting-event tasks.
- Added Plan Duration [days] and Downtime [days] as named Microsoft Project custom Number1/Number2 fields.
- Added Location, Position, Activity ID and Safe-to-safe group custom text fields.
- Added a cycle-grouped task-list review CSV generated from the same P50 trace.
- Added XML hierarchy, duration and downtime regression tests.

## v0.10.3

- Rebuilt `OUT_overall monthly` as additive P50/P75/P90 representative-year schedules.
- Added statistical-target and representative-duration selection tables.
- Added Exact P0, timestep-adjustment, downtime and zero-variance reconciliation for each representative scenario.
- Renamed the former pointwise monthly output to `OUT_specific month` and labelled it non-additive.
- Changed workable-time and downtime charts to clustered side-by-side columns and prohibited stacked/waterfall grouping.
- Expanded the Excel export from 17 to 18 worksheets.

## v0.10.2

- Consolidated monthly Excel reporting into `OUT_overall monthly` and removed `OUT_planning monthly`.
- Converted monthly downtime/workability to hours and capped completion-month values at the statistical finish timestamp.
- Added cumulative-progress and side-by-side P50 monthly-hours charts with bar values.
- Renamed `OUT_planning DT` to `OUT_overall DT`.
- Renamed and repositioned `OUT_planning coverage` as `OUT_years coverage` directly after `IN_sequence`.
- Resolved automatic hindcast start/end years in `IN_general`.
- Standardized `OUT_P50 DT details` to three decimals and displayed summary downtime percentage as XX.XXX.

## v0.10.1
- Combined Percentile 1/2/3 representative-year choices and available hindcast years into one Detailed results basis selector.
- Removed the separate Specific hindcast year control and the Weather ready sidebar notice.
- Rebuilt both `OUT_planning DT` charts below the tables and ensured hidden helper data does not suppress chart series.
- Expanded IN_general Setting/Value, planning Basis and detailed Basis/note using merged physical columns.
- Improved milestone date/time visibility and removed incremental planning positions-completed columns.
- Replaced `Year of interest` with **Detailed results basis**.
- Added automatic selection and detailed rerun of the P50 representative hindcast year.
- Updated the bundled YHO FEM2 project input to 42 positions and corrected G1–G5 safe-to-safe descriptions and notes.
- Implemented the reviewed 18-tab Excel export with final worksheet names.
- Standardised Excel output to Calibri and 0.25 pt chart/series lines.
- Removed chart boxes and gridlines and corrected chart placement.
- Added clustered P50/P75/P90 workable-time and downtime columns.
- Added the revised nine-page landscape executive PDF report.
- Removed the key-limitations section and corrected table/chart page positioning.
- Excluded Microsoft Project output from the release.
- Updated tests, templates, README and build documentation.

## v0.9.0
- Changed P0 to use exact learning-adjusted durations, independent of simulation timestep.
- Added explicit timestep-adjustment reporting separate from weather downtime.
- Added first-future-blocker attribution for insufficient weather windows.
- Consolidated downtime by main factor and separated direct from insufficient-window downtime.
- Attributed Hs-Tp curve failures to Hs, Tp or Multiple criteria while retaining the curve as assessment basis.
- Marked end-of-weather-data scenarios incomplete and excluded them from percentile calculations.
- Standardised calculated decimal values and percentages to three decimal places while preserving raw weather precision.
- Kept `safe_to_safe_group` immediately after `weather_window_hours` in exported `INPUT general`.
- Added spacing between Page 09 metric cards and lower chart/table sections.
- Added PDF executive-summary export and renamed Page 15 to Reports and export.
- Updated User Guide, README, tests and workbook templates.

## v0.8.0
- Added two selectable safe-to-safe assessment methods: `MOST_STRINGENT` and `TIME_PHASED`.
- Added a project-level default method on Campaign Settings and per-group overrides on Activities.
- Added the dedicated `04 Safe-to-Safe Groups` Excel worksheet and project-package data.
- Positioned `Safe-to-safe group` immediately after `Weather window [h]` in `03 Activities`.
- Updated the User Guide, Generated Sequence, QA records and Excel export for both methods.
- Configured G1 tower and G2 nacelle groups as `MOST_STRINGENT` at `OFFSHORE` in the built-in G09B example.
- Changed the Campaign Settings form action to blue with white text.
- Compressed detailed QA records into consecutive operational intervals and limited the initial coloured table display to 500 rows.
- Precomputed and reused consolidated group weather masks, reducing the full 45-year G09B hindcast benchmark to about 13 seconds in the build environment.
- Bundled the reconciled FM2 weather CSV and assigned the same dataset to PORT, TRANSIT and OFFSHORE for software demonstration.
- Retained the v0.5.2 light UI, MFA-only footer, equal Run Assessment cards and established downtime chart palette.

## v0.7.1
- Corrected Streamlit toast icons by replacing symbol glyphs with valid single-character emoji.
- Restored the light v0.5.2 engineering-dashboard appearance while retaining the v0.7.0 safe-to-safe calculation engine.
- Restored light Plotly charts and white engineering cards and editors.
- Replaced the generic calculation status indicator with a compact symmetrical fixed-bottom wind-turbine animation.
- Kept all multi-location, safe-to-safe grouping, QA and Excel-export functionality unchanged.

## v0.7.0
- Added safe-to-safe commitment groups to Activities, Generated Sequence, simulation, QA and Excel export.
- Added the `Safe-to-safe group` project-input column. Blank remains standalone.
- Added validation requiring each group to contain at least two consecutive activities of one activity type.
- Added complete future group-window pre-check using each member's own location, duration, weather window and limits.
- Added uninterrupted group execution after commitment.
- Added QA blocker fields: group, blocking activity, blocking location and blocking timestamp.
- Added waiting-time reporting by safe-to-safe group.
- Updated `.waproject` format to version 3 while keeping earlier files compatible.
- Corrected duplicate counting in the standalone insufficient-window branch.
- Expanded automated tests to cover commitment-group logic and workbook round trips.

## v0.6.0
- Introduced the Offshore Control Room UI with a dark offshore gradient and glass-style summary cards.
- Grouped the sidebar into Setup, Assessment, Results and Export.
- Added a bundled dark Plotly theme for consistent offline charts.
- Kept engineering tables and editors on solid high-contrast surfaces.
- Added dashboard summaries to Weather Data, Activities and Run Assessment.
- Enhanced the fixed-bottom wind-turbine progress animation and key-action toast messages.
- Retained the v0.5.2 calculation engine, multi-location logic, project packages, QA and Excel export.

## v0.5.2
- Kept long detected weather filenames fully inside the summary card with wrapping and hover text.
- Replaced the browser/app icon with a fixed-bottom wind-turbine icon.
- Removed the duplicated project name from the lower sidebar and tightened the lower controls.
- Standardized all six workflow cards on the User Guide page to the same dimensions.
- Corrected the Weather Data location editor call discovered during validation.


## v0.5.1
- Added a separate Generated sequence page before Run assessment.
- Reordered QA before Excel export and made Excel export the final page.
- Removed the duplicate QA CSV download from Excel export.
- Consolidated page guidance into the User guide.
- Improved the project package save/open layout.
- Corrected the fixed-bottom turbine animation symmetry.
- Improved sidebar colour and reset-button visibility.
- Replaced the top brand subtitle with the current project name.
- Removed any legacy product-name references.

## v0.5
- Complete UI redesign based on the approved dashboard concept.
- Added multi-location weather and activity-location assignment.
- Added complete project package save/open.
- Added location-level QA and downtime outputs.
- Added multi-location Excel input format.
- Replaced the run graphic with a fixed-bottom offshore wind turbine.
- Retained v0.4.1 simulation, percentile, planning and downtime logic.
