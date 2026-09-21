# Weather Assessment v0.10.6 release notes

This revision implements the agreed P0, downtime-attribution, Excel, PDF, XML and Page 15 reporting updates.

## P0
- Added **P0 (no weather)** as an explicit Detailed results basis on Page 03.
- P0 is now a deterministic continuous programme using exact learning-adjusted activity durations.
- P0 has zero weather downtime, no representative hindcast year and no weather-simulation timestep adjustment.
- Added an always-present **OUT_P0 run** worksheet with the exact continuous P0 activity trace.
- When P0 is selected, OUT_run, PDF and XML all use the deterministic P0 schedule.
- Weather-detail sheets are omitted for P0 because weather downtime is zero.

## Downtime cause and mechanism
- Replaced generic **Multiple criteria** attribution with the exact criterion combination, such as `Wind 10 m + Hs` or `Hs + Tp`.
- Separated **cause** from **mechanism**:
  - Cause = blocking weather criterion / combination.
  - Mechanism = Direct exceedance or Window pre-check.
- Window pre-check waiting remains attributed to the weather criterion that blocks the required continuous window.
- Added **OUT_<basis> DT detail** with:
  - cause / mechanism reconciliation,
  - activity downtime summary,
  - additive Activity x Cause matrix.

## PDF
- Added Cause of downtime and Activities driving downtime pages for weather-based detailed scenarios.
- Clarified statistical percentile duration versus representative hindcast-year duration.
- Clarified final-position completion versus full campaign completion.
- P0 report pages explicitly show zero WDT, no representative year and no timestep adjustment.

## Excel / metadata
- `Generated` is stored as a real Excel datetime and displayed as `dd-mmm-yyyy hh:mm`.
- Calculated metadata values display to three decimals.
- Selected detail sheet names follow the Page 03 basis, e.g. OUT_P75 DT, OUT_1992 DT and matching detail sheets.

## Microsoft Project XML
- XML follows the Page 03 Detailed results basis, including deterministic P0.
- Native Duration remains the baseline productive duration.
- Custom Duration WDT [days] carries weather downtime.
- Start / Finish preserve the selected schedule.
- P0 XML has Duration WDT = 0.

## UI
- Page 15 wording remains basis-neutral; exports follow Page 03.
- Removed the `MFA` wording from the bottom of the left sidebar.
