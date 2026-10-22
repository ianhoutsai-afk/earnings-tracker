# All-company quarterly history implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Steps use checkbox syntax for tracking.

**Goal:** Apply the approved NVIDIA five-quarter policy to every active company and continuously check official sources without promoting unverified data.

**Architecture:** A shared quarterly policy owns identity, ordering, retention, and company event fields. SEC submissions and original earnings exhibits provide scalable official discovery; explicit inline XBRL contexts supply quarterly GAAP metrics. NVIDIA retains its tested newsroom adapter. Source failures preserve history and publish honest per-issuer status.

**Tech Stack:** Existing Python, lxml, requests; native JavaScript modules; GitHub Actions and Pages.

**Spec:** docs/superpowers/specs/2026-10-22-all-company-quarterly-design.md (the user's approved full-site plan, extended explicitly after the NVDA pilot).

## Global Constraints
- Maximum five distinct quarterly periods in every active history and official input. Retain existing records until verified replacements exist; missing quarters remain missing.
- Do not infer release dates from filing dates, company fiscal quarters from publication years, or quarterly EPS from annual EPS.
- Unknown legacy fiscal identities and dates are labelled unverified. Unknown numerical basis is hidden in the UI; original values remain recoverable in Git.
- Keep release, filing, period-end and future call dates distinct. No Bark schedule or notification changes.
- No secrets in logs. Malformed proxy configuration is sanitized/validated before requests. Failed official sources are failures, not healthy checks.
- Only publish validated bundles, with per-company failure isolation and source/metric provenance.

## Review Focus
- Same-day releases for different periods and amendments: use period identity, preserve first release date and metric provenance.
- Legacy FY labels do not prove Q4; show pending identity until explicit official evidence exists.
- Inline XBRL YTD, dimensioned, annual and conflicting contexts must not become quarterly totals.
- All-source failure must keep five-quarter data and be visible in both workflow status and website.
- Shared CIKs, missing mappings and short trading histories must receive truthful per-ticker coverage without fabricated entries.

### Task 1: Shared policy and migration
**Files:** quarterly_policy.py, verified_history.py, nvda_history.py, update_data.py, test_quarterly_policy.py, test_verified_history.py
**Interfaces:** retain_history(history, today=None), company_fields(company, history, today), retain_manifest(records).
- [x] Write failing tests for five-period order/dedupe, seed replay, all-company restatement/null preservation, non-mutating migration, short histories and invalid/future candidates.
- [x] Run focused tests; observe expected failures.
- [x] Implement policy and integrate every write path. Validate finite numeric values.
- [x] Run Python suite; update older assertions where newest-first replaces intentional pilot-only behavior.
- [x] Commit shared policy.

### Task 2: Official-source checks for all issuers
**Files:** official_sources.py, official_sync.py, proxy-worker.js, update_data.py, test_official_sources.py, test_official_sync.py
**Interfaces:** parse_inline_quarter(document, period_end), parse_earnings_release(document, report_date, filing_date, today), sync_all(root, today=None, fetch=None, full=False).
- [x] Write failing cases for release-vs-filing dates, exact XBRL contexts, explicit fiscal identity, missing metrics, revisions, issuer deduplication, per-issuer failure and failed preflight.
- [x] Implement SEC HTTPS transport validation, request pacing, conservative release/inline facts adapter, persistent source state and independent NVIDIA adapter.
- [x] Inspect real accessible official source fixtures. Test cloud preflight before claiming SEC coverage.
- [x] Run focused/full suites, then commit.

### Task 3: Full-site display
**Files:** quarterly-history.mjs, i18n.mjs, index.html, test_quarterly_history.mjs, test_i18n.mjs
**Interfaces:** selectHistory, fiscalQuarterLabel, nextCompanyEvent, quarterEstimates; common UI for all tickers.
- [x] Write failing tests for every-ticker five-quarter rule, legacy fiscal/date labels, unverified metrics, event expiry and source-status text.
- [x] Implement labels for verified releases vs unverified legacy dates, safe estimates, source health, short history and shared mobile layout.
- [x] Run JS tests and desktop/mobile browser checks for NVDA, AAPL, JPM, ACN, GOOGL and a short-history issuer.
- [x] Commit UI.

### Task 4: Migration, automation and release
**Files:** .github/workflows/main.yml, .github/workflows/nvda_history.yml, data JSONs, official_scan_state.json, docs/all-company-quarterly-migration.json, README.md
- [x] Record per-company before/after audit, migrate active files, preserve NVIDIA's five verified rows.
- [x] Enable hourly window checks plus daily all-company scans with shared write concurrency. Publish failure state before failing job. Preserve unrelated notifier behavior.
- [x] Verify complete tests, workflow syntax, data invariants, two idempotent syncs and external-source failure behavior.
- [x] Request independent whole-branch review, fix substantive findings with regressions.
- [ ] Create/attach PR, pass checks, merge, run cloud sync, verify deployed data and desktop/mobile website. Record unresolved sources truthfully.
