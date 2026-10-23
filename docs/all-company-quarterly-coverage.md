# All-company quarterly coverage after verification

Snapshot: 2026-10-23T03:26:00.326148Z. The comparison starts at production commit `e81137b`. These are measured source-coverage counts, not a guarantee that no newer earnings announcement exists.

## Verified coverage

| Measure | Before | After |
| --- | ---: | ---: |
| Tracked tickers | 503 | 503 |
| Retained quarter records | 2513 | 2514 |
| Official quarter/release identities | 1884 | 2363 |
| Companies with five official quarter/release identities | 324 | 447 |
| Quarters with both GAAP diluted EPS and quarterly USD revenue | 682 | 1288 |
| Companies with five complete metric quarters | 14 | 27 |
| Latest stored quarter still unverified | 103 | 25 |
| Companies with no verified quarter/release identity | 73 | 12 |

The completed scan checked 499/499 non-NVIDIA SEC issuer groups, plus NVIDIA's independent official-newsroom source, across all 503 tracked tickers. Deferred companies: 0. Final source failures: 0. Companies with any pending source/history/metric work: 495.

Zero connection failures means the relevant official endpoints were reachable after bounded retries. It does not mean every company has five current, fully parsed earnings reports. Original release dates and quarterly identities are verified separately from financial metrics. Pending status can include a source candidate outside the retained five-quarter window.

## Applied policy and corrections

All tracked tickers retain at most five distinct quarters, latest first. New verified quarters replace the oldest retained quarter. Fiscal years come from official sources; FY2027 can legitimately be released in calendar 2026. Earnings publication, SEC filing, quarter end, and conference-call dates remain separate.

Unverified legacy dates and labels remain explicitly marked; unverified numeric values are hidden. Missing records are not fabricated. Short histories in this snapshot: PSKY (4 quarters).

The parser now recognizes explicit completed Item 2.02 publication statements, standalone Exhibit 99 news releases, and same-issuer SEC supplemental histories. It rejects scheduled dates, future results, call announcements, and unrelated comparative-report references. Consolidated statement headings may span empty layout wrappers but cannot cross note/table boundaries. Revenue must be an explicit consolidated total; annual EPS is never subtracted to manufacture quarterly EPS.

JPM's five quarters and AAPL's FY2025 Q4 received individual source-table review. JPM uses reported GAAP revenue and diluted EPS rather than managed/FTE revenue or adjusted EPS. Their exact figures and primary sources are in [the verification notes](quarterly-coverage-followup-2026-10-23.md).

SATS is retained as the existing tracked historical alias. The current official SEC issuer response lists ECHO for the same CIK; unsupported forward dates are withheld. This finding is not treated as proof that earnings were never released.

## Remaining work

Latest stored quarter still unverified (25):

AEP, AES, AMCR, ARE, BAX, CAG, CFG, COIN, ES, FICO, FITB, GE, KDP, LHX, MET, MNST, MTD, ON, PFG, RF, SATS, SLB, SWKS, USB, VZ.

No verified quarterly identity in active history (12):

ARE, CAG, CFG, ES, FITB, GE, LHX, MNST, ON, PFG, SATS, USB.

These are coverage gaps, not findings that the companies have not released results. Remaining cases need targeted company-IR adapters or individual official-record review. Metric gaps include custom taxonomies, multiple revenue components, annual filings without standalone Q4 EPS, non-USD statements, and narrative or supplemental tables without standard quarterly tags.

## Verification evidence

- 136 Python tests and 26 JavaScript tests passed. Newly reproduced failures covered timezone rollover, publication wording, source history, and consolidated-total boundaries.
- Independent review confirmed all reported date/call/comparative/table defects were resolved; 53 focused tests independently passed.
- A complete source scan was followed by a second full check with up to three attempts per failed official URL. Only immutable official archive documents were reused from cache; SEC submission lists were fetched again. Final failures remain visible in the public source state.
- Publication validation passed for all 503 tickers. There are no duplicate verified fiscal-quarter identities, no lost retained verified metrics, and no unexpected eviction of a verified period.
- Two manifest replays added zero records and left history unchanged; a superseded trusted period was evicted only when five newer verified periods existed.
- Local browser QA passed 39 company flows at 390, 1024, and 1440 pixel widths: company search, card count/order, language switching, favorites, dark mode, empty state, and layout containment. No page errors were recorded. Browser plugin not available; the bundled Playwright and Chrome provided verification.
- The cross-midnight regression that blocked the old hourly updater was corrected by freezing its clock. Production UTC timestamps remain unchanged.
- [Implementation and review](https://github.com/ianhoutsai-afk/earnings-tracker/pull/9).

The [per-company before/after ledger](quarterly-coverage-followup-audit.json) includes every retained quarter and its official source URLs. The previous migration audit is preserved in [all-company-quarterly-migration.json](all-company-quarterly-migration.json). Live machine-readable evidence remains [official_scan_state.json](https://ianhoutsai-afk.github.io/earnings-tracker/official_scan_state.json) and [history_status.json](https://ianhoutsai-afk.github.io/earnings-tracker/history_status.json).
