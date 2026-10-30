# Reviewed quarterly metric adapters — 2026-10-30

This increment continues the approved five-quarter design. It adds original-source adapters for Tesla's embedded image-exhibit statement text and Stryker's shared date / per-column duration and year headers. Fiscal identity remains verified by the existing official release and filing pipeline. Q4 EPS is read directly and is never annual EPS minus earlier quarters.

## Source-verified targets
- Tesla FY2025 Q4: revenue USD 24,901 million, GAAP diluted EPS USD 0.24. Source: https://www.sec.gov/Archives/edgar/data/1318605/000162828026003837/exhibit991.htm .
- Stryker FY2026 Q3: net sales USD 6,520 million, GAAP diluted EPS USD 1.96. Source: https://www.sec.gov/Archives/edgar/data/310764/000031076426000059/sykex991earningsq32026.htm .
Both issuers now have five complete-metric quarters in the candidate bundle, preserving separate release and per-metric URLs.

## Validation
Five initial regression failures reproduced the missing layouts. Independent review found three additional Important fail-closed gaps: explicit non-USD units, contradictory period headings, and adjusted statement scopes retaining a GAAP title marker. Six failing subcases reproduced these findings before a single fix pass. Final suite: 182 Python tests and 26 JavaScript tests pass locally and remotely. Original document source hashes are recorded in tests/fixtures/reviewed/README.md.

- Full-source branch scan, audit and critical replay: https://github.com/ianhoutsai-afk/earnings-tracker/actions/runs/41043397229
- Final guarded parser tests and original-source checks: https://github.com/ianhoutsai-afk/earnings-tracker/actions/runs/41044032444
- Per-ticker before/after evidence: reviewed-metric-results-2026-10-30.json

Full scan: 499 SEC issuer targets checked, no source failures or deferred issuers. Candidate coverage: 2,380 official quarters, 1,339 complete-metric quarters, 451 tickers with five official quarters, 33 tickers with five complete-metric quarters. Stored history remains 2,514 records across 503 tickers. Pending/unsupported cases remain explicit: sourceHealthy=true, dataComplete=false, healthy=false.

The scan admitted new quarters for LNT, AMZN, CVX, KVUE, LYB and REGN. Four companies' complete-quarter counts fell by one as a new incomplete quarter displaced the oldest completed quarter. The audit checks that every still-retained verified value is unchanged and any removed verified quarter is older than the five retained periods. New-quarter admission and other source-driven fills must not all be attributed to these two adapters. The complete history objects for TSLA/SYK/META/MSFT were unchanged after a second source sync.

## Decisions and limits
- Continue the existing approved metric design without reopening product scope or metric definitions.
- The code reviewer did not judge the pending live data bundle; its audit, consistency validation and replay are verified separately by the executor.
- No Critical or Minor review findings remained. All three Important findings are covered by regressions.
- Banks, insurers, REITs, foreign-currency reports and other unreviewed layouts remain pending. This increment does not establish full-market completeness or guarantee punctual cron execution.
