# Reliable quarterly publication and official coverage implementation

**Goal:** Implement the user's approved 2026-10-24 four-phase plan: reliable publication/deployment, durable field-level diagnostics, all-company latest-quarter discovery, then five-quarter official backfill.
**Architecture:** Keep GitHub Actions/Pages and six JSON files. Use one staged, validated, optimistic publication helper and an independent exact-commit Pages deploy. Keep release identity and metric evidence separate. Extend conservative official parsers, persist discovery/backfill progress, and show separate source/freshness/coverage states.
**Runtime:** Python 3.11, existing requests/pandas/lxml/yfinance; browser ES modules. No paid data or database.
**Spec:** The full plan explicitly supplied by the user in this conversation is binding.

## Global constraints
- Work from current origin/main in an isolated worktree; preserve unrelated and untracked files. Bark is outside this scope.
- Six publication files: data.json, historical_data.json, official_history.json, history_status.json, official_scan_state.json, sp500_mapping.json.
- One writer lock; checkout latest main after acquiring it. Stage and validate complete bundle. Never rebase generated JSON or force push.
- At most three publication attempts, 2400 seconds total source budget, 3300 seconds job timeout. Retry data-only advancement with fresh subprocesses. Abort superseded runs on non-generated changes.
- Safe source-error bundles may publish while source verdict fails; invalid bundles never publish. Separate source, push, deployment verdicts.
- Exact-commit Pages deployment even after safe source-error publication. Reconcile pushed-but-undeployed commits on no-change runs. Verify six public hashes within 900 seconds. Never deploy an older batch over a newer one.
- Latest official quarter for ALL 503 tickers first, then latest five distinct fiscal periods. No verified seed resurrection or unverified eviction of five trusted periods.
- Explicit original release evidence; quarter GAAP diluted EPS and USD revenue only. No adjusted/FFO/annual/YTD substitution or annual EPS subtraction. Source and provenance per field; unresolved official conflicts suppress that field and retain prior evidence.
- Official-only sources: original SEC/IR releases, exact-context filings and CompanyFacts, explicit consolidated financial statements, reviewed issuer-specific adapters. Unknown/unsupported is unresolved, not not-disclosed or complete.
- Global SEC limiter <=5 requests/sec, immutable document cache, bounded retries.
- Durable campaign audit cutoff, per-CIK source cursors, last successful discovery (not attempt), and field gaps atomically published. Provisional source key CIK+accession+URL until fiscal identity is known. Post-cutoff new quarters still ingest; evicted work is superseded.
- Backward-compatible public status fields. Separate source reachability, latest discovery, five-period identity and numeric completeness. Only proven outside-window candidates stop affecting target coverage. Warn after 30 hours without successful discovery per issuer.
- Coverage declines require explicit field/period evidence: correction, withdrawal/conflict or legitimate rollover. Explained gaps do not count as numeric completeness.

## Review focus
- Stale trigger SHA despite correct concurrency; changing code during a retry; successful push but missing result artifact.
- Source-error publication must deploy; exact SHA validation and superseded deployment handling.
- False release/date from preannouncements, conference calls, comparative text or cover dates; fiscal-year mismatches.
- Annual/adjusted/segment figures mistaken for quarterly GAAP consolidated metrics; rounding versus actual conflict; amendments.
- Discovery checkpoint starvation, unknown newer candidates, old non-target candidates and five-quarter retention/replay.

## Task 1: Reliable publisher and Pages
- Reproduce races using real temporary git repositories and a bare origin before implementing publication.py.
- Shared publisher stages six files, regenerates on data-only advancement, validates, pushes normally, records structured result and hashes, supports no-change deployment reconciliation.
- Route all three writer workflows through latest-main checkout/shared lock/helper. Preserve manual workflow interfaces.
- Add independent main-only Pages workflow triggered by writer workflow completion (any conclusion), ordinary main code push, and manual invocation; producer artifact authorizes exact SHA, fallback/reconciliation is explicit; package public assets only, generated deployment metadata, deploy and verify six hashes.
- Test source failure/validation failure/retry exhaustion/code change/reconciliation/deployment supersession.

## Task 2: Official parsing and metric evidence
- Real cached ARE/CFG/GE source fixtures first, RED then GREEN. Parse real DOM publication blocks and table periods, retain strict negative guards.
- Expand exact-context metrics plus CompanyFacts fallback and explicit GAAP statement tables. Custom adapters only with real evidence fixtures.
- Add per-field verified/pending/conflict states and amendment/restatement precedence preserving independent source provenance; conflicted values hidden without deleting evidence.
- Run full Python/JS suites and commit independently.

## Task 3: Durable gaps, scheduling and frontend
- Field-level diagnostic ledger, source/latest/coverage/issues/progress interfaces in existing JSON, all legacy keys retained.
- Latest-first bounded scanning and resumable discovery, campaign cutoff and successful-discovery timestamps, no fixed release/file truncation before five-period source coverage is established.
- Accurate bilingual health banner and per-company/per-field explanations, strict latest-not-established state and 30-hour stale state.
- Test old-window versus possible-new candidates, short history, identity/currency, resume, retention, and all standard browser controls.

## Task 4: Official backfill and audit
- Baseline remote main and publish snapshot; cache reuse only for original immutable docs. Apply new discovery to every company and prioritize latest identity/metrics, then five-quarter historical fields.
- Publish per-company before/after ledger, real source URLs/reasons and remaining unresolved items; distinguish actual values from status-only corrections.
- Repeat complete backfill to demonstrate idempotence/no unexpected data changes; allow timestamps and legitimate new official releases.
- Preserve any source failures and unexplained gaps visibly; no claims of full numerical completeness while unsupported sources remain.

## Task 5: Review and delivery
- Full tests, YAML/CLI integration, browser at 390/1024/1440, bundle validation and independent review.
- Produce reviewable staged commits and PR; attach PR to this chat. Prepare exact deployment/rollback steps before any production switch.
- Do not merge or change production Pages settings without concrete final approval. Keep later independently verified quarters during rollback.
