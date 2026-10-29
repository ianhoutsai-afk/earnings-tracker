# Quarterly data completion implementation plan

> Execute inline using systematic debugging, regression tests and remote CI. User approved continuation on 2026-10-30 (Asia/Shanghai).
Goal: make the latest officially published quarters arrive reliably, improve GAAP quarterly metric completeness, and distinguish source availability from data completeness.
Spec: docs/superpowers/specs/2026-10-22-all-company-quarterly-design.md
Baseline: main 562e566bac114d525b4a395d59f40bbfaac389c4. Production snapshot: 503 tickers, 2365 official quarters, 1275 complete metric quarters, 29 five-complete-metric tickers.

Constraints: at most five quarters; preserve official provenance; never substitute adjusted/YTD/annual EPS; no inferred fiscal quarters; retain old data on failure; do not change Bark notifications.

1. [ ] Reproduce TSLA/META release rejection and representative missing metrics using current official sources, with bounded read-only CI diagnostics.
2. [ ] Add failing regression fixtures for evidenced failure modes; verify red remotely.
3. [ ] Apply minimal parser/discovery fixes; verify focused and existing test suites remotely.
4. [ ] Add explicit source-health versus completeness status; test successful transport with incomplete data.
5. [ ] Backfill and validate a branch-only publication bundle; compare all-company coverage and inspect changed records with sources.
6. [ ] Review final diff and CI, then publish the validated result within authorized scope; verify deployment and a repeat sync.

Review focus: future/call announcements must not become actual results; new quarter identity must be explicit; consolidated totals must not become revenue components; same-period revisions must retain original release provenance; success of requests must not imply complete metrics.
