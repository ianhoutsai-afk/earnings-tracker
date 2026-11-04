# Completion evidence — 2026-11-04

- User authorized numeric completion and latest-quarter catch-up; other product changes are deferred.
- Original baseline tests passed: 182 Python / 26 JavaScript.
- Original source diagnostics run 41774181116 covered 35 issuers. Source capture 41774634080 retained original files and SHA-256 hashes.
- Observed RED regressions for TOC shadowing, completed-publication wording, HTML comment handling and extension-tag totals; initial fixes passed 188 Python tests locally.
- Reviewed title-order and customer-sales cases observed RED in 41775045833, GREEN in 41775278955.
- Wrapped issuer names, U.S. abbreviation, joint Q4/year and completed posting cases observed RED in 41775278955, GREEN in 41775707056.
- Five original release metric cases observed RED in 41775375447. Full regression and source backfill 41775846497 passed all 194 Python and 26 JavaScript tests before its source scan.
- Dated actual release/explicit fiscal identity and Inc. title cases observed RED in 41776008039.
- No framework, UI, watchlist, notification or future-calendar changes are included.
- Operational decision: GitHub source snapshots replace the unavailable local runtime; tests remain mandatory. Publication candidates use unique branch names to preserve the exact tested source revision.

## Final independent review

The fresh read-only reviewer independently ran 61 parser tests and verified all 11 source fixture SHA-256 hashes. It identified two Important false positives: a no-period release could take its later conference-call date, and generic extension revenue could inherit adjusted/pro forma/reconciliation scopes. Both were reproduced before correction (13 failing assertions across six regression methods). The fixes bind the candidate date to the actual-publication dateline, require exact GAAP statement headings (optionally prefixed by the authoritative DEI registrant name), and reject explicitly adjusted extension tags. Final local suite: 204 Python tests and 26 JavaScript tests pass.

Minor deferred: the opening release_metrics.py module overview still lists only the earlier reviewed issuers. The supported-issuer constant, source fixtures, tests and this change's documentation identify all five additional reviewed issuers.

Items the reviewer declined to judge are owned by final publication validation: issuer freshness and retained metric/provenance changes; fresh full-source availability; aggregate completeness versus newer parse exceptions; temporary workflow cleanup; merge reconciliation and deployment. Unsupported issuer layouts remain explicitly incomplete rather than being treated as complete because transport succeeded.

The first full source scan (41775846497) checked all 499 issuers with zero transport failures and produced 2421 official quarters / 1459 complete metric quarters. It was not published: validation crossed New York midnight and found an expired next-event date. Candidate preparation now refreshes existing publication fields after the scan and before validation. A fresh scan with the final reviewed parser is required before publication; this earlier count is not the final result.
