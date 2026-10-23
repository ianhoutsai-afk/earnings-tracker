# Quarterly coverage verification follow-up

Authorized continuation of the all-company five-quarter plan. Snapshot starts from production commit e81137b. No calendar-quarter inference, annual EPS subtraction, unscoped estimates, or unsupported GAAP totals.

Confirmed root causes:

- A UTC check timestamp may have a different calendar date from the New York earnings day. Freeze the clock in the regression rather than assuming the UTC prefix equals the local date.
- Consolidated income-statement tables can be inside single-child layout wrappers. Find their explicit heading across those wrappers, with note/table boundaries to avoid accepting revenue components.
- Original Item 2.02 publication statements explicitly establish dates and periods that some exhibits omit. Admit those statements only when they attest an actual earnings publication; a filing-cover date or future call is insufficient. Match fiscal identity against the corresponding official quarterly filing.
- High-volume issuers need SEC supplemental submission files to cover five quarters. Only same-issuer filenames and relevant dates are eligible.

Verification sequence: regression failures, focused/full tests, real-source candidates, full source backfill with per-metric provenance, validated publication bundle, independent review, deployment and public-data checks. Track remaining unsupported records separately from connection failures.

## Individually reviewed quarterly facts

Reviewed on 2026-10-23 (Asia/Shanghai). Financial release dates and verification business days use New York time.

| Ticker | Official fiscal quarter | Release date | Period end | GAAP diluted EPS, USD | Quarterly GAAP revenue, USD |
| --- | --- | --- | --- | ---: | ---: |
| JPM | FY2026 Q3 | 2026-10-13 | 2026-09-30 | 5.57 | 50,172,000,000 |
| JPM | FY2026 Q2 | 2026-07-14 | 2026-06-30 | 7.70 | 57,347,000,000 |
| JPM | FY2026 Q1 | 2026-04-14 | 2026-03-31 | 5.94 | 49,836,000,000 |
| JPM | FY2025 Q4 | 2026-01-13 | 2025-12-31 | 4.63 | 45,798,000,000 |
| JPM | FY2025 Q3 | 2025-10-14 | 2025-09-30 | 5.07 | 46,427,000,000 |
| AAPL | FY2025 Q4 | 2025-10-30 | 2025-09-27 | 1.85 | 102,466,000,000 |

JPM's five quarterly metrics come from the [official 3Q26 financial supplement](https://www.sec.gov/Archives/edgar/data/19617/000162828026065582/a3q26erfex992supplement.htm), its reported-GAAP consolidated income statement and diluted EPS quarterly-trends columns. The supplement explicitly lists the five three-month period ends in its footnotes. Original release dates retain their own dated 8-K publication statements. In particular, current reported revenue is USD 50.172 billion; managed/FTE revenue of USD 50.907 billion and adjusted EPS of USD 5.75 are excluded.

AAPL's quarter comes from the three-month September 27, 2025 column in its [original release financial statements](https://www.sec.gov/Archives/edgar/data/320193/000032019325000077/a8-kex991q4202509272025.htm). The twelve-month columns are excluded. The release's adjusted-comparison note concerns the prior-year tax charge, not a substitution for the current GAAP quarterly EPS. No Q4 EPS is calculated from annual EPS.

Independent review findings were reproduced with negative regressions before correction: call announcements versus actual results, scheduled release dates including suffix language, adjacent/same-clause prior-report references, and note text inside a layout wrapper. The final bounded review reported no remaining findings.
