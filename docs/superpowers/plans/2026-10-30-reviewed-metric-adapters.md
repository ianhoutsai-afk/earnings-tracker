# Reviewed quarterly metric adapters — 2026-10-30
Continue the user-approved design in docs/superpowers/specs/2026-10-22-all-company-quarterly-design.md.
Base: 2bf95b067f1a8ab7b104d4e6faa601da55649212. Execution: inline, requested continuation.
Goal: fill directly reported GAAP quarterly gaps with reviewed official layouts; preserve five-quarter windows and per-field sources.

1. Capture bounded TSLA Q4 and SYK latest original-source diagnostics on this isolated branch. Keep original evidence as artifacts; record why parsing failed.
2. Add real-layout failing regressions and negative controls (annual/YTD/adjusted EPS, weighted shares, wrong period/currency, conflicting tables). Extend only layouts supported by observed evidence. No annual EPS subtraction.
3. Run complete Python/JavaScript suites, original-source checks and publication validation. Backfill all issuers on the branch, inspect changes and replay critical issuers.
4. Review the whole diff independently, reconcile any newer main data, and publish only a validated bundle. Report exact coverage and remaining exceptions.
