# Quarterly numeric and latest-period completion — 2026-11-05

This increment follows the user's requested data priority. It repairs completed-publication discovery and reviewed statement layouts, then rechecks every SEC issuer with the final reviewed parser. It does not claim all-market data completeness.

## Final measured results

Baseline production commit: 3c55faf5351747a0c48164a0f2a6d8f13983dceb. Audited source candidate: 5233407d5572a10f1e7a1da5b4cfe9c912a21ccd. Full source/validation run: https://github.com/ianhoutsai-afk/earnings-tracker/actions/runs/41954136236 .

| Measure | Production before | Audited candidate |
| --- | ---: | ---: |
| Companies / stored rows | 503 / 2514 | 503 / 2514 |
| Officially verified quarters | 2388 | 2432 |
| Revenue and GAAP diluted EPS both verified | 1364 | 1460 |
| Companies with five official periods | 455 | 468 |
| Companies with five complete metric periods | 35 | 38 |

The final scan checked all 499 SEC issuer targets with zero source failures and no deferred companies, plus the separate NVIDIA source. Regression verification passed 204 Python tests and 26 JavaScript tests. Original source fixtures retain their documented hashes. One independent review identified two Important false positives; regressions reproduced them before the fixes, and the complete suite then passed.

## Exact data changes

- 158 newly populated numeric fields across 127 issuer/period pairs: 90 in retained periods and 68 in newly admitted official periods.
- Zero changed non-null raw revenue/EPS values in retained issuer-period pairs; zero lost retained numeric values; zero changed original release dates.
- 62 added official periods and 18 older official periods removed as five-period windows advanced. These counts include replacing unverified history, and are not all new earnings announcements.
- 14 companies gained a newer latest officially verified period. These include ARE, AMCR, CAG, DG, LIN, MNST, NVR, ODFL, PFG, RSG, SLB, STLD, USB, WTW.
- Every retained window has at most five distinct period-end dates, and no company's latest official period regressed.

The complete per-field values, source URLs and latest-period comparisons are in [quarterly-completion-final-audit.json](quarterly-completion-final-audit.json).

## Remaining exceptions

1054 of 2514 stored quarters still lack simultaneous official verification of both revenue and GAAP diluted EPS. Unsupported Q4 statements, issuer-specific totals, ambiguous fiscal identity and other unreviewed layouts remain pending. The latest stored row is still unverified for 13 tickers: AES, AEP, BAX, CFG, COIN, SATS, FITB, KDP, MTD, ON, RF, SWKS, VZ. A fully populated old window does not establish that every newer unparsed announcement has been admitted. SourceHealthy is true; dataComplete and healthy remain false.

This change preserves verified figures when a source cannot supply a field. It does not use adjusted EPS, annual/YTD EPS subtraction, third-party actuals, or inferred fiscal identities to close gaps.

## Integration decisions and review limits

- Current production data was reconciled before the fresh full scan. The audit baseline is the exact production commit above, rather than the older implementation baseline.
- Publication rollover cleanup applies company_fields to company metadata only. Re-running the whole discovery refresh after a source scan can reset status for AMCR/KDP when stored-date ordering differs; an offline reproduction established that cause, and fields-only cleanup preserved history/status and passed publication validation.
- Existing FedEx periods ending February 28 and September 30, 2026 are retained as separate periods despite repeated Q3 labels. The current SEC release explicitly identifies the latter as calendar-year 2026. Deduplicating fiscal label text would discard a distinct official reporting period. Source: https://www.sec.gov/Archives/edgar/data/1048911/000104891126000128/fdx-earningsreleasety2026q3.htm .
- Minor deferred from review: release_metrics.py's opening module overview still names only the earlier reviewed issuers. The constant, fixtures and tests document the five added issuers.
- The independent reviewer did not judge the final live bundle or deployment. The executor performed the full-source scan, retained-value/period audit and consistency validation; deployment is verified separately after integration.
