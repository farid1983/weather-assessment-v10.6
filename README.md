# Weather Assessment - v0.10.6

Weather Assessment v0.10.6 makes the **Detailed results basis** selected on Page 03 the single basis for detailed Excel, PDF and Microsoft Project XML exports. The selection can be deterministic P0, a representative percentile scenario or a specific completed hindcast year.

## Main behaviour

- **P0 (no weather)** is a continuous deterministic schedule using exact learning-adjusted activity durations. It has zero WDT, no representative weather year and no weather-simulation timestep adjustment.
- Every Excel export includes **OUT_P0 run**.
- `OUT_run` follows the selected detailed basis.
- Weather scenarios receive dynamic `OUT_<basis> DT` and `OUT_<basis> DT detail` sheets.
- Downtime cause is the exact blocking criterion / combination. Direct exceedance and Window pre-check are separate assessment mechanisms.
- The executive PDF includes cause-of-downtime and activity-driver sections for weather scenarios.
- Microsoft Project XML follows the selected basis and uses baseline Duration, custom Duration WDT, Start and Finish.

## Page 15

Excel, PDF and XML exports use the Page 03 Detailed results basis. No separate report percentile selector is required.

## Local start

1. Install 64-bit Python 3.11 or newer.
2. Extract the ZIP.
3. Double-click `run_app.bat` on Windows, or run `./run_app.sh` on macOS/Linux.
4. Run a quick or full assessment for weather-scenario reports. Full assessments prepare the selected trace in advance; quick assessments generate it when needed. P0 reports can be generated without weather or a hindcast run.

All durations, criteria, assumptions, location assignments and safe-to-safe definitions must be checked against approved project procedures and operational limits.

## Unreleased architecture and correctness changes

See [ARCHITECTURE.md](ARCHITECTURE.md) for calculation ownership, state flow, and verification commands, and [UNRELEASED_CHANGES.md](UNRELEASED_CHANGES.md) for changed behavior and preserved engineering conventions.

Weather timestamps and campaign dates use a UTC clock. Set the CSV source timezone explicitly when naive timestamps are local; explicit timestamp offsets take precedence. Activity allowed-time windows use each location's operational timezone. Ambiguous/nonexistent daylight-saving timestamps must be resolved in the source.

Simulation steps are 1, 0.5, or 0.25 hours. Finer source weather cannot be downsampled silently: select a compatible simulation step. Duplicate timestamps, missing/nonfinite values, and negative weather magnitudes must be repaired before a run.

Run tests with `python -m pytest -q`. The suite includes the supplied 45-year Rev.2K_3 reference assessment and Streamlit workflow tests. The original release manifest and review artifacts are retained as historical references; they do not describe the modified working source.
