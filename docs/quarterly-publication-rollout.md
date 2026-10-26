# Quarterly publication rollout and recovery

This change is prepared on `codex/reliable-quarterly-data`. It has not switched production Pages settings or merged into `main`.

## Verified configuration

Read on 2026-10-24: repository Actions are enabled; the connected repository account has administrator permission. Pages reports `build_type: legacy`, source `main:/`, status `built`. The known good starting data/code commit is `6983d484762f9fddbdc5a09b4ee9d6ffbe243d9f`; do not restore this entire data snapshot after newer quarters are independently verified.

The new workflow declares `pages: write`, `id-token: write`, `actions: read` and the `github-pages` environment. Local packaging and verifier regression tests exercise exact-commit authorization and public hashes. Production token/environment permission and actual CDN propagation can only be confirmed by the first approved deployment; read access to Pages settings alone does not prove a deployment will succeed.

## Approved production switch

1. Review and merge the implementation PR only after its full test job and bundle validation pass. Recheck current `main` first: if another producer has added data, preserve and reconcile its verified records before merging generated JSON. Do not resolve conflicts by replacing a whole file with an older branch snapshot.
2. In repository Settings → Pages → Build and deployment, select **GitHub Actions**. This removes the old branch-build route. The equivalent administrator API update is `PUT /repos/ianhoutsai-afk/earnings-tracker/pages` with `{"build_type":"workflow"}`. Obtain the user's production approval before this shared setting change.
3. Run **Verified Pages Deployment** on `main`. Its build step fetches current main and skips superseded trigger commits. It packages only the three public app assets, six JSON files, `.nojekyll`, and generated `deployment.json`.
4. Confirm the deploy job completed and its verification step reports all six hashes and `sourceCommit` matching the exact authorized commit. Verification stops after 900 seconds. An unconfirmed public bundle is a failed verification, not a successful update.
5. Run **Official Quarterly History** with `mode=sync, full=true`. Inspect the producer's separate `sourceHealthy`, `publication`, `pushedSha`, and `hashes`. A red source verdict may still have safely pushed validated data; its completion-triggered Pages deployment must proceed using that result artifact.
6. Run the writer again without new data. It must either publish new check state or emit `publication=unchanged` with hashes/commit. This is the reconciliation path if a previous runner pushed successfully but stopped before uploading its result artifact.

## What each outcome means

| Outcome | Data publication | Website behavior |
|---|---|---|
| Some source inaccessible or work deferred | Validate preserved history plus honest source/progress state; a safe bundle can be pushed | Independent Pages job can deploy the safe state; source job remains red |
| Structural or cross-file inconsistency | No push | Existing deployed site remains |
| Main advanced only in generated JSON | Regenerate from newest main, maximum three attempts within one 40-minute source budget | No merge/rebase of generated snapshots |
| Main changed code/config/schema | Old generator returns `superseded` | Next writer starts from new code |
| Producer artifact missing | No artifact-based deployment for that run | Next validated writer authorizes current main even when unchanged |
| Superseded deployment batch | Skip | Serialized deployment jobs prevent an older queued batch replacing a newer release |
| Public hashes do not converge | Deployment unconfirmed | Investigate Pages/CDN; never report confirmed success |

## Recovery while preserving later verified quarters

1. Disable affected data writer workflows and the custom Pages workflow, and cancel queued deployment runs. Keep the last confirmed public deployment while investigating. Do not delete data or reset `main`.
2. Save the current six JSON files and `deployment.json` with their commit SHA and hashes. Keep the result artifacts and original source evidence. The audit file lists every addition, conflict withdrawal and legitimate five-quarter eviction.
3. Prepare a corrective branch from current main. Revert the faulty **code/configuration** change. If data must be corrected, remove or withdraw only the affected field/period with source evidence, retain other independently verified additions, and regenerate status/coverage from the corrected history. Do not restore an old six-file snapshot wholesale.
4. Re-run the full tests, bundle validation and repeat-scan comparison. Review the corrective diff, then merge with approval.
5. Re-enable custom Pages deployment and publish the repaired current main commit. Confirm all six public hashes before re-enabling normal writers. If custom Pages itself is broken, first create a reviewed current-main recovery commit containing the preserved valid records; only then temporarily select the legacy `main:/` publishing source.

No new paid data service, database or secret is required. Keep the existing official SEC contact/proxy configuration. Original SEC archive documents use the existing cache; mutable submissions and Company Facts are fetched afresh each run. The process-wide SEC gate applies to direct requests, proxy attempts and retries at no more than five starts per second.

References: [GitHub custom Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [Pages settings API](https://docs.github.com/en/rest/pages/pages#update-information-about-a-github-pages-site).
