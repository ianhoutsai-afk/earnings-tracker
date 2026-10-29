# Quarterly data completion implementation plan

> Execute inline using systematic debugging, regression tests and remote CI. User approved continuation on 2026-10-30 (Asia/Shanghai).

**Goal:** Restore latest-quarter ingestion, improve directly reported GAAP quarterly metrics, and distinguish source availability from data completeness.
**Spec:** docs/superpowers/specs/2026-10-22-all-company-quarterly-design.md
**Baseline:** main 562e566bac114d525b4a395d59f40bbfaac389c4.

Constraints: at most five quarters; preserve official and per-metric provenance; never substitute adjusted/YTD/annual EPS; no inferred fiscal quarters; retain data on source failure.

- [x] Reproduce TSLA/META publication rejection with bounded read-only source diagnostics.
- [x] Observe failing regressions before fixing completed-publication verbs, paired release/call statements and empty SEC layout wrappers.
- [x] Implement reviewed Microsoft/Meta quarterly statement columns, including Q4 and embedded headings, and explicit official future-release schedules.
- [x] Separate sourceHealthy, dataComplete and healthy; add source/completeness regression coverage.
- [x] Run 165 Python tests, real-source smoke checks, two all-company backfills and validated publication bundles.
- [x] Replay TSLA/META/MSFT after final backfill; histories remain identical and contain five distinct quarters.
- [x] Review code/data diff and record the remaining exceptions in docs/quarterly-completion-results.json.
- [ ] Merge the final tested change and verify GitHub Pages deployment.

Actual coverage and remaining source-adapter/calendar work are documented in docs/quarterly-completion-followup-2026-10-30.md. This increment does not claim universal data completeness or punctual cron execution.
