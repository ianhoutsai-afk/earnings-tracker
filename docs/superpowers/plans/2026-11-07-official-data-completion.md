# Official data completion — 2026-11-07

User instruction: continue filling data using available resources. Prior capped150/50 batches are completed and do not count again. Account quota is not observable; maximize source-verified missing facts rather than consume resources without useful output.

1. Profile remaining missing revenue/GAAP diluted EPS by source form. Collect all safe direct facts from existing official filings, newest first; retain exact original statement/context/unit/source evidence. No numeric cap is imposed by this request.
2. Diagnose missing EPS layouts and class dimensions before accepting them. Accept only direct company GAAP figures with matching issuer/quarter/USD units; common-stock-class EPS requires identical values or an exact SEC TradingSymbol-to-class match with a class note. No adjusted metrics, estimates, annual subtraction or bank revenue inference.
3. Stage null-to-number fills only, preserve every prior non-null fact/source/release date/current five-quarter window, and recompute truthful coverage counts. Keep production parsers unchanged for this data-only batch.
4. Run full existing tests and publication validator plus exact raw/display and per-source preservation audit. One fresh independent final review, then merge tested data and verify exact Pages deployment. Reconcile concurrent main changes before publication.
5. Report actual completed fields and remaining source limitations; do not claim complete data while gaps remain.

Execution record: baseline is b166038b3fce74e7350472613a0755ea5f58f35a. Current source profile:2434 official quarters;1661 have revenue and GAAP diluted EPS;700 revenue fields and599 EPS fields missing. Most remaining gaps are annual/Q4 or release-only sources. Review focus: consolidated revenue vs component; explicit quarter vs annual duration; exact issuer in combined filings; USD vs USD/share and sign/scale; common-stock EPS class conflicts.


Source scan complete:250 missing-field10-Q filings and all773 incomplete official quarters' release URLs scanned.399 candidate fields were gathered; source admission, deduplication and conservative exclusions leave354 fields (210revenue,144GAAP dilutedEPS) across183companies264periods, before publication. No conflicting accepted source values.

EPS clarification: where stock-class values differ, an exact SEC DEI TradingSymbol-to-stock-class-context match may identify the listed ticker's diluted EPS; such values receive a bilingual class note. Otherwise all reported common-class diluted values must agree. This replaces the initial overly restrictive all-classes-equal assumption with explicit listed-class evidence; no class is guessed. Dimensional contract-estimate impacts, basic-only EPS, continuing/discontinued component EPS, mixed adjusted sections and unclear combined-utility parent scope remain pending.

Read-only audit correction verified: currency codes match whole words, so UNAUDITED is not misread as AUD. The previous false positive was reproduced and corrected; nine foreign currency labels are still excluded. All forthcoming data changes must pass raw/display/source/window preservation audits and the full existing suite before publication.

Review correction: EFX2025-12-31 candidate122.3 is diluted share count, not EPS; no candidate has been published. The safe subset rejects weighted/share-count rows and release EPS captions that do not explicitly state diluted and per share. Regression assertions reject the actual EFX error and all weighted-share rows before publishing. Reapply from baseline and repeat all tests. The first reviewer exhausted its model quota; remaining review continues on an available model.
