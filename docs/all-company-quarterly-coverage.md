# All-company quarterly coverage after deployment

Snapshot: 2026-10-22T17:42:19.309112Z. Coverage counts describe this snapshot, not a guarantee that no newer announcement exists.

## Applied policy

All 503 tracked tickers use the same five-period retention, fiscal identity, release/filing/period-end distinction, source provenance, and missing-value rules. New verified quarters evict the oldest retained quarter. Unknown legacy labels and dates remain explicitly unverified; unverified numeric values are hidden. A company with fewer than five records remains short.

## Verified coverage

| Measure | Count |
| --- | ---: |
| Tracked tickers | 503 |
| Retained records | 2513 |
| Officially verified quarter and release identities | 1882 |
| Tickers with five verified quarter/release identities | 324 |
| Quarters with both verified GAAP diluted EPS and USD quarterly revenue | 681 |
| Tickers with five complete metric quarters | 14 |
| Tickers whose latest stored row remains unverified | 104 |
| Tickers with no verified quarter/release identity | 73 |
| Tickers with any pending source/history/metric work | 496 |
| Source-connection failures in the second complete scan | 0 |

Zero transport failures means sources were reachable. It does **not** establish that every company has current, complete, or parseable financial data. Quarter/release verification and metric verification are separate measures. Pending status can include an unsupported candidate outside the retained five-period window.

PSKY has three stored records. Other tickers have five retained records, which may include unverified legacy rows. Fiscal years come from official evidence; FY2027 can legitimately have a release date in calendar 2026.

## Remaining source coverage

The following tickers currently have no verified quarter/release identity in the active history:

ABNB, ADP, AMCR, APD, APTV, ARE, AXON, BA, BAC, BRK-B, CAG, CB, CFG, CMS, COF, COIN, COP, COST, DG, DLR, DVN, EA, ECL, EOG, ERIE, ES, F, FITB, FRT, GE, HII, INTC, IR, JBHT, JNJ, JPM, LHX, LYV, MAS, MCD, MET, MNST, MRK, NEE, NFLX, NOC, NSC, NTAP, NTRS, NUE, ODFL, ON, OXY, PFE, PFG, PSKY, PSX, SATS, SNA, STT, STZ, SWK, T, TGT, TRMB, TXN, ULTA, USB, VRTX, VZ, WEC, XOM, XYZ.

These are unresolved coverage results, not evidence that those companies have not released earnings. Dedicated adapters or reviewed official records are still needed where the generic SEC parser cannot establish the original release date, explicit quarterly period, and fiscal identity. For example, JPM's narrative and separate financial supplement require joint interpretation; the parser does not infer its release date from the SEC filing date or its reporting period from a comparative footnote.

Other gaps include quarterly totals in custom taxonomies, mixed revenue components, annual filings without a standalone Q4 EPS context, high-volume filing histories beyond SEC's main recent list, non-USD reports, 6-K-only sources, and historical ticker aliases. Annual EPS is never subtracted to manufacture Q4 EPS.

## Validation evidence

- 117 Python tests and 26 JavaScript tests passed, including source failure preservation, amendments, metric provenance, fiscal identity, and seed replay.
- Two complete source scans covered all 499 non-NVIDIA issuer groups plus NVIDIA across 503 tickers. The second scan lost no previously verified periods.
- Two manifest replays added zero records and produced a stable result.
- A check of 8,521 downloaded source documents found no common access-denied or rate-limit error pages in their initial content.
- Local and public-site browser checks passed 39 company flows each across 390, 1024, and 1440 pixel widths, including language switching, search, favorites, dark mode, card count/order, and layout containment.
- [Implementation and independent-review fixes](https://github.com/ianhoutsai-afk/earnings-tracker/pull/8).
- [Complete branch cloud scan](https://github.com/ianhoutsai-afk/earnings-tracker/actions/runs/39819159609).
- [First production hourly-window scan](https://github.com/ianhoutsai-afk/earnings-tracker/actions/runs/39825850820) passed: 400/400 issuer groups, zero source failures, zero new records, and a validated bot commit published to Pages. The retained quarter count stayed at 1,882 verified identities.

The per-ticker before/after ledger is [all-company-quarterly-migration.json](all-company-quarterly-migration.json); current public source state is [official_scan_state.json](https://ianhoutsai-afk.github.io/earnings-tracker/official_scan_state.json) and [history_status.json](https://ianhoutsai-afk.github.io/earnings-tracker/history_status.json). Source setup and parser boundaries are documented in [official-source-setup.md](official-source-setup.md).
