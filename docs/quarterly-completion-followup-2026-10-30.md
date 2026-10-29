# Quarterly data completion follow-up — 2026-10-30

This continues the approved five-quarter plan. It preserves a maximum of five distinct fiscal quarters, GAAP diluted EPS, metric-specific provenance, and separate future-event dates.

## Reproduced causes and corrections

- TSLA's original Item 2.02 states it **released** its financial results. The publication parser discovered that verb but did not accept it as completed-result evidence. A failing regression preceded the correction; future release/call announcements remain rejected.
- META's October 2026 8-K includes an earlier board event. Its actual earnings publication was later, in a sentence also scheduling a call. The narrow combined construction now needs independent confirmation from the dated actual-results exhibit; the cover date and call date are not substituted for the release date.
- SEC statement wrappers can contain empty formatting spans. These no longer detach a total contract-revenue row from its consolidated statement heading. Notes, other tables, textual wrappers and revenue components remain boundaries.
- Reviewed Microsoft and Meta original release statements can supply directly reported quarterly metrics when the 10-K provides only annual contexts or the total is not tagged. Expanded rowspan/colspan headers bind each value to its explicit three-month period and year. Statement titles inside full-width header rows are supported. Annual/YTD, adjusted, segment, comprehensive-income, and weighted-share columns are excluded. Unsupported issuers stay pending; this adapter does not infer currency for the whole universe.
- Explicit financial-results schedules in checked official SEC earnings exhibits can populate the next release date, official source and BMO/AMC timing. A call alone, a preliminary result, a product announcement, an ambiguous date, and an expired event do not become a next release.
- The publication summary now separates sourceHealthy, historyComplete, metricsComplete and dataComplete. healthy requires both available sources and complete data. Transport success alone cannot claim data completeness. The updater's process exit status still reflects source/execution failures so verified partial progress can publish with explicit incomplete status.

## Evidence and verification

- Baseline: production commit 562e566bac114d525b4a395d59f40bbfaac389c4, 503 tickers, 2514 stored quarters, 2365 official quarters, 1275 complete-metric quarters, 448 tickers with five official quarters, 29 with five complete-metric quarters.
- The original 136 Python tests passed before changes. Added regression failures were observed before implementation. The final Python suite has 165 tests.
- Real-source checks confirm latest TSLA/META quarters on 2026-10-21 and MSFT on 2026-10-28. MSFT and META each return five complete-metric quarters. TSLA's Q4 metrics still require another reviewed layout.
- Full-source backfill and publication validation: https://github.com/ianhoutsai-afk/earnings-tracker/actions/runs/40920285850.
- Critical-issuer replay compares complete history objects after a second sync, validates the staged bundle, and never publishes its temporary files.
- Per-ticker changes and final counts: [quarterly-completion-results.json](quarterly-completion-results.json).
- Persistent regression CI runs for pull requests and code updates. Production data code changes also trigger a validated full update. Bark scheduling and notification files were not changed.

## Final measured coverage

| Measure | Before | After |
| --- | ---: | ---: |
| Officially verified quarters | 2365 | 2380 |
| Complete revenue and GAAP diluted EPS quarters | 1275 | 1327 |
| Tickers with five official quarters | 448 | 451 |
| Tickers with five complete-metric quarters | 29 | 32 |
| Stored quarters | 2514 | 2514 |

The latest full scan checked all 499 SEC issuer targets, plus the separate NVIDIA source, with zero recorded source failures and no deferred issuers. There remain 492 tickers with a parse or completeness exception. Explicit official future-release coverage in this snapshot is only 1 ticker; third-party estimates elsewhere are not relabelled as official.

A complete five-quarter window does not by itself prove the newest unparsed candidate was admitted. Remaining parse exceptions and source coverage must still be inspected. Naturally short issuer histories are not padded with invented quarters.

## Remaining work

- Official date and fiscal-identity exceptions still need reviewed source adapters; classify these separately from transport failures.
- Financial/insurance/REIT totals, issuer-specific revenue taxonomies, foreign-currency statements and other Q4 layouts remain conservative/pending when unsupported.
- SEC exhibits provide only part of future earnings-calendar coverage. Dedicated IR/RSS calendar adapters are still needed where no usable filing announces the date.
- GitHub cron is not a punctual-delivery guarantee. The hourly schedule remains in place; external scheduling and delay telemetry require separate work.

## Primary reproduction sources

- TSLA original results publication: https://www.sec.gov/Archives/edgar/data/1318605/000162828026066738/tsla-20261021.htm
- META original results publication: https://www.sec.gov/Archives/edgar/data/1326801/000162828026066700/meta-20261019.htm
- Microsoft Q4 release with three-month and twelve-month GAAP columns: https://www.sec.gov/Archives/edgar/data/789019/000119312526323632/msft-ex99_1.htm

Final calendar spot-check: Block/XYZ explicitly schedules its 2026 Q3 financial results for November 3, 2026 after the market closes. The post-date timing regression was observed failing before correction. Source: https://www.sec.gov/Archives/edgar/data/1512673/000119312526335117/d91486dex991.htm . The next production sync applies the corrected AMC timing.
