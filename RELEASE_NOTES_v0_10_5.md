# Weather Assessment v0.10.5 — Release notes

## Selected-basis reporting

Page 15 now follows the Detailed results basis selected on Page 03 Campaign settings for all detailed exports. A representative percentile selection uses its nearest completed hindcast year; a specific-year selection uses that completed historical simulation directly.

- Excel: `OUT_run` is explicitly labelled with the selected basis.
- Excel: the detailed downtime sheet is named `OUT_P50 DT`, `OUT_P75 DT`, `OUT_P90 DT`, or `OUT_<year> DT` as applicable.
- PDF: the separate representative-detail percentile selector has been removed; detailed content follows Campaign settings.
- XML: the P50-only wording, metrics and review CSV controls have been removed. One `Generate and download XML` button produces the selected-basis schedule.

## Excel metadata

- `Generated` is stored as a true Excel datetime and displayed as `dd-mmm-yyyy hh:mm`.
- `Planning start` is stored as a true Excel date.
- Calculated metadata values display to three decimal places.

## Microsoft Project XML

The XML is intended for preliminary planning review.

- Native `Duration` = learning-adjusted baseline productive duration.
- Custom `Duration WDT [days]` = weather/operational waiting attributed to the activity.
- Start/Finish = simulated selected-basis dates including weather effects.
- Tasks are manually scheduled to preserve the simulated dates.
- Actual/progress/remaining-duration fields are omitted.
- Cycle summary tasks aggregate baseline productive duration and WDT.
- Invalid `24:00:00` time values are no longer emitted.

## Validation

- Python compilation completed successfully.
- 22 automated tests passed.
- Regression tests cover dynamic detailed-sheet names and preliminary-planning XML semantics.
