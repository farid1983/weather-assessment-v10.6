# Assessment architecture

## Ownership and flow

`app.py` only configures and dispatches Streamlit pages. `weather_assessment/pages/` separates guide, setup, assessment, results, and exports. `ui_context.py` owns editable draft state and navigation; it adapts UI actions to application services.

`assessment.run_assessment()` validates and snapshots inputs, resolves every required weather location (including independent group assessment sites), prepares weather, expands the sequence, calculates exact P0, and runs hindcast scenarios. A successful call returns an `AssessmentRun`; the UI publishes it atomically. A failed run does not publish partially calculated state.

`AssessmentRun` owns its serialized input snapshot, prepared weather, expanded sequence, P0 result and historical results. Public result accessors return defensive copies. Its private fields and derived caches are implementation details. Detailed scenario replays use the original run inputs and must reconcile with the stored scenario totals.

`analytics.AssessmentAnalytics` supplies shared campaign, position, annual, milestone, planning and coverage tables. Tables are cached per percentile tuple within the run. Consumers receive copies, so chart formatting cannot mutate authoritative analytics. UI, Excel and PDF consume these tables. Legacy standalone report functions can construct the same analytics when called without a run context.

`policies.py` owns percentile direction, supported steps, finite-number checks, and boolean parsing. `sequence.py` owns deterministic P0. `simulator.py` owns weather feasibility and execution; report adapters never reevaluate feasibility. `ms_project.py` maps the selected trace onto tasks.

## Invalidation

Simulation settings, activities, locations, curves, learning and weather changes require a new run. Weather fingerprints hash every row. The UI blocks stale results rather than exporting a mixture of old results and new inputs.

Project name, percentile values and detailed-basis selection are presentation/analytics preferences. They preserve the engine run, while regenerating the relevant selection or analytics. Nominal year remains a simulation input because monthly planning records are computed on its calendar.

Reports are generated on request and cached by report kind and selection. P0 can be calculated without weather. Quick and full assessments use the same engine; full additionally prepares a trace before publication.

## Time and statistical contracts

- Campaign dates and prepared weather timestamps are UTC. Naive CSV timestamps default to UTC unless a source timezone is supplied. Explicit offsets take precedence.
- Activity allowed-time windows use the assigned location's timezone. DST ambiguity in source timestamps is rejected rather than guessed.
- Supported steps are 1, 0.5 and 0.25 hours. Downsampling that discards source observations is rejected. Upsampling retains the existing bounded forward-fill method; gaps and invalid samples are rejected.
- Adverse metrics use ordinary upper-tail percentiles. Beneficial metrics use the lower-tail assurance convention.
- Monthly completions and cumulative completions are percentiled independently across scenarios. Monthly percentile completions must not be summed into a cumulative percentile.
- Monthly hour statistics are direct scenario-hour statistics, including zero hours for inactive scenarios. Rates retain their existing active-scenario denominator. Seasonal historical month statistics remain a separate legacy API.
- P0 is continuous and exact. Weather execution rounds activity work to the simulation grid and exposes the timestep adjustment separately.
- Downtime report activity identity uses activity IDs. Description-only aggregates remain for backward compatibility.

## Validation

Use the supported environment and run:

```text
python -m pytest -q
```

The reference test loads the supplied Rev.2K_3 workbook and weather and checks 44/45 completed scenarios, exact P0 of 2747.9 hours, statistical P50 approximately 169.198 days, representative year 1984, and duration/working/downtime/monthly reconciliation. Other tests cover input edge cases, group assessment locations, timezone conversion, result isolation, report consistency, and Streamlit workflows.

Native Microsoft Project import and visual rendering in end-user Excel/PDF applications are separate acceptance checks; byte/XML validation does not replace them.
