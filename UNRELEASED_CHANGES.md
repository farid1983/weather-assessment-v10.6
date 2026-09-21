# Unreleased audit remediation

Implemented after approval of the architecture audit:

- Split Streamlit entry point, state adapters and page renderers.
- Added an assessment service with protected input snapshots and atomic publication.
- Added cached shared analytics consumed by results pages, Excel and PDF.
- Corrected non-additive cumulative monthly percentiles and synthetic Excel monthly hours/progress.
- Replaced value-dependent Excel percentage formatting; fractional position statistics remain decimal.
- Included independent safe-to-safe assessment locations and rejected configuration errors before execution.
- Rejected nonfinite engineering inputs, invalid weather, duplicates and lossy downsampling; enforced consistent simulation clocks.
- Added explicit CSV source timezone and location-aware allowed-time evaluation; retained UTC campaign dates.
- Added full weather fingerprints, strict boolean/time parsing and project format checks.
- Made package imports atomic, report generation on demand, and P0 exports independent of hindcasts.
- Preserved completed simulations across presentation-only settings changes.
- Used stable activity identity in downtime reports and handled empty result sets.
- Added regression, service, UI and full reference-project tests.

Engineering policies intentionally preserved: shared Hs–Tp endpoints use the earlier bin; safe-to-safe MOST_STRINGENT/TIME_PHASED methods retain their existing feasibility definitions; missing learning cycles retain the existing 1.0 fallback; Microsoft Project retains manual scheduling and the 24-hour calendar. These are explicit future engineering/product decisions, not silently changed by this refactoring.

The original VERSION, BUILD_STATUS, MANIFEST_SHA256 and Review_examples are release-reference material, not a new release certification. No deployment or native Microsoft Project acceptance test has been performed.

Verification: the original pinned-runtime baseline passed 23 tests. The final suite passes 57 tests, including bundled startup, Streamlit workflows, exports, and the full Rev.2K_3 reference run. Reference totals remain P0 = 2,747.9 h, 44/45 completed years, P50 approximately 169.198 d, and representative year 1984. The new CI workflow has been added but has not run remotely.
