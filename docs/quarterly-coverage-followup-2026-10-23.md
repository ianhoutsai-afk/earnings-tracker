# Quarterly coverage verification follow-up

Authorized continuation of the all-company five-quarter plan. Snapshot starts from production commit e81137b. No calendar-quarter inference, annual EPS subtraction, unscoped estimates, or unsupported GAAP totals.

Confirmed root causes:

- A UTC check timestamp may have a different calendar date from the New York earnings day. Freeze the clock in the regression rather than assuming the UTC prefix equals the local date.
- Consolidated income-statement tables can be inside single-child layout wrappers. Find their explicit heading across those wrappers, with note/table boundaries to avoid accepting revenue components.
- Original Item 2.02 publication statements explicitly establish dates and periods that some exhibits omit. Admit those statements only when they attest an actual earnings publication; a filing-cover date or future call is insufficient. Match fiscal identity against the corresponding official quarterly filing.
- High-volume issuers need SEC supplemental submission files to cover five quarters. Only same-issuer filenames and relevant dates are eligible.

Verification sequence: regression failures, focused/full tests, real-source candidates, full source backfill with per-metric provenance, validated publication bundle, independent review, deployment and public-data checks. Track remaining unsupported records separately from connection failures.
