# Restore the official SEC source

## Verified current limitation

The branch diagnostic on 2026-10-22 received HTTP 404 from the existing proxy for both submissions and an existing quarterly filing. `PROXY_TOKEN` and `SEC_CONTACT_EMAIL` were absent from the Actions environment. Direct requests from the local runtime returned HTTP 403. Thus the code/UI migration does not establish that all 503 tickers have current source-verified history.

Diagnostics: https://github.com/ianhoutsai-afk/earnings-tracker/actions/runs/39807571201

## Deployable files and settings

Deploy the repository's `proxy-worker.js` as a Cloudflare Worker using the account that owns the service. It now accepts both `/archives/` and `/Archives/` and forwards the canonical `/Archives/` SEC path. It remains authenticated and restricted to SEC submissions, XBRL API and archive routes.

In that Worker's Settings:

1. Set `PROXY_TOKEN` as a secret with a strong, newly generated token.
2. Set `SEC_CONTACT_EMAIL` to a working contact email. The Worker uses it for SEC's required User-Agent.
3. Confirm its deployed HTTPS origin (for example `https://sec-proxy.<account>.workers.dev`). An editor URL, dashboard URL, sample hostname or a route that serves a 404 is not the origin.

In the repository's Settings → Secrets and variables → Actions:

1. Set `SEC_PROXY_URL` to that deployed HTTPS origin, without a path, query or credentials. Older origins without an explicit scheme are normalized to HTTPS by the client.
2. Set `PROXY_TOKEN` to the same secret value as the Worker.
3. Set `SEC_CONTACT_EMAIL` to the working contact email for direct SEC fallback/request identification.

Never put secret values into a commit, an issue, a screenshot or a chat message. This setup does not require sharing credentials with the coding agent.

## Verify and resume

In GitHub Actions, choose **Official Quarterly History** (workflow file `nvda_history.yml` is retained to preserve the registered workflow identity):

1. Run `mode=preflight`. Both `submissions` and `quarterly_filing` must return HTTP 200. The check logs statuses and error types, never configuration values.
2. Run `mode=sync`, `full=true`. Every active issuer is checked once per CIK. Original 8-K Item 2.02 earnings exhibits establish release dates and quarter ends. A matching 10-Q/10-K with exact dimensionless quarterly inline-XBRL contexts supplies GAAP diluted EPS and revenue when unambiguous. Unsupported layouts or missing release evidence remain explicitly pending.
3. Run the sync a second time. Check source errors and pending companies, then verify no duplicate periods, no seed resurrection, no more than five records and a successful Pages deployment.

Hourly runs check the reporting window and companies whose last check is stale or failed. Daily full runs cover all companies, including those with no expected date. Source failures preserve historical records, publish the source error, and fail the workflow visibly. A successful request does not imply every financial field was parseable.

## Known coverage boundaries

- The generic SEC parser is conservative. A company needs a dated original earnings exhibit, an explicit quarterly period, and either explicit fiscal identity in the release or a matching filing's DEI fields. An 8-K event date alone is never a release date.
- Q4 EPS is never calculated by subtracting cumulative EPS. Missing quarterly contexts remain blank.
- Non-USD or company-specific taxonomy totals, 6-K-only issuers, financial-year transition reports, and conflicting contexts require a dedicated reviewed adapter. They must not silently inherit calendar quarter labels.
- Companies do not necessarily publish five quarters of history. Existing short histories (PSKY and Q in the migration snapshot) remain short and labelled.
- SEC submissions include at most the latest 1,000 filings in the main recent list. High-volume issuers may need supplemental submission files. If the recent list does not cover five quarters, the scan reports incomplete coverage; it cannot claim a complete five-quarter backfill.
