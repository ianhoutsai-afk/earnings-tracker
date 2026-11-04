# Latest-quarter and numeric completion — 2026-11-04

User scope: fill official quarterly revenue and GAAP diluted EPS and catch up to published quarters, then report before another improvement priority.

Baseline main: 96098d22457da3a2fd003d4be1b04efaabe27854. 503 tickers, 2514 rows, 2384 official quarters, 1356 complete metric quarters, 33 companies with five complete metric quarters. Baseline: 182 Python and 26 JavaScript tests pass.

1. Diagnose original SEC submissions, 8-K publications, release statements and financial filings.
2. Reproduce missing latest quarters and numeric fields in failing tests. Preserve explicit fiscal identity, dimensionless quarter contexts, USD units, consolidated totals, GAAP diluted EPS and per-field source URLs. Never subtract annual EPS.
3. Run complete tests and source backfill; audit every issuer-period change and retained prior value. Validate at most five periods and classify unresolved gaps honestly.
4. Obtain one fresh read-only review, fix important findings through regressions, reconcile concurrent official updates, merge tested work and verify deployment.

Review focus: annual/YTD/segment/adjusted substitution, statement scope leaking into notes, fiscal identity inferred from calendar dates, conference calls substituted for release dates, loss of retained figures/provenance, and a complete old window hiding a newer unparsed candidate.

Execution: isolated remote branch codex/quarterly-completion-20261104. The user's stale checkout remains untouched. The local host became unavailable; remaining source checks and tests execute in isolated GitHub Actions. Data candidates are written to unique run branches so ongoing source work cannot overwrite or race a publication candidate.
