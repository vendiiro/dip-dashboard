# Overnight findings, 2026-11-06

## Baseline (before any change, commit f258a31, new .venv with Playwright)

`10 failed, 1014 passed, 1 skipped in 407.79s (0:06:47)`

Failed:
- tests/test_web_build.py::test_template_is_the_assembled_parts (CRLF working file vs LF page; fixed in Task 1)
- tests/test_web_build.py::test_the_placeholder_appears_once_and_the_page_is_one_self_contained_file (CRLF; fixed in Task 1)
- tests/test_guards.py::test_check_fails_early_on_a_stale_template_and_web_fixes_it (CRLF; fixed in Task 1)
- tests/test_browser.py::test_stale_banner_names_the_date_when_prices_are_over_two_weekdays_old
- tests/test_browser.py::test_a_broken_row_is_skipped_and_named_in_a_visible_alert
- tests/test_browser.py::test_a_broken_chart_leaves_the_detail_and_the_table
- tests/test_browser.py::test_a_data_file_that_is_not_valid_javascript_still_shows_a_message
- tests/test_browser.py::test_detail_chart_draws_when_a_stock_has_a_holiday_gap_in_hist
- tests/test_browser.py::test_alerts_empty_state_does_not_inherit_the_generic_empty_rule
- tests/test_browser.py::test_alerts_more_hover_does_not_take_the_more_context_button_style

The 7 test_browser.py failures share one error: `OSError: [Errno 22] Invalid argument: '\\C:\\Users\\K..ytt..j..\\...\\demo.html'`
(a Windows path with non-ASCII characters turned into a bad path inside the tests). Pre-existing, not a line-ending issue, not fixed.

Skipped:
- tests/visual/test_visual.py (whole module, 1 skip): baselines were made on Linux, this is Windows. Baselines not regenerated.

## After Task 1 (line-ending fix, agent-file YAML fix, new tests/test_agent_files.py)

`7 failed, 1018 passed, 1 skipped in 351.72s (0:05:51)`

The 3 line-ending failures now pass and the new agent-file test passes. The remaining 7 failures are the test_browser.py path errors listed above, and the skip is the Linux-only visual baselines.

## Task 2: real-data check (2026-11-06)

Nightly run (main checkout, read only): `output/run.log` shows `exit code 0` at 00:16 on 2026-11-06. `run_meta.json`: asof 2026-11-05, universe 348, screened 345.

### Step 2: nightly data quality

- Screened 345 of 348. Not screened: BK, ROG.SW, AVB.
- `partial_bar`: 0 rows. Expected near 0, so this is as expected.
- Issue counts from `data_quality.csv` (24 rows): 5 error, 4 warn, 15 info.
  - error: `stale` 1 (AVB), `fetch_failed` 2 (BK, ROG.SW), `no_data` 2 (BK, ROG.SW)
  - warn: `fetch_failed` 1 (AVB), `lagging_vs_peers` 1 (AVB), `missing_values` 1 (AVB), `spike_revert` 1 (KNEBV.HE)
  - info: `crosscheck_ok` 5 (AJG, APH, BLK, CTAS, NOW), `empty_last_bar` 10 (AVB, plus 9 Helsinki `.HE` names: FORTUM, KNEBV, NDA-FI, NESTE, NOKIA, SAMPO, STERV, UPM, WRT1V; the 9 have their last bar on 2026-11-04 and AVB's last bar is 2026-08-14)
- Coverage: bars 346/348, fundamentals 346/348, earnings 346/348.

### Step 3: verify_universe (full run, 348 tickers)

Command: `scripts/verify_universe.py --out output/universe_verified.csv` in the worktree, exit 0. Output is git-ignored. No ticker was removed or changed.

| status | count |
|---|---|
| ok | 315 |
| under_20b | 19 |
| name_mismatch | 11 |
| no_bars | 1 |
| stale | 1 |
| fetch_error | 1 |

Flagged tickers (33). Market cap is today's value, not point-in-time.

- **fetch_error:** ROG.SW
- **no_bars:** BK
- **stale:** AVB
- **under_20b (19):** UPM.HE, STERV.HE, WRT1V.HE, TEL.OL, MOWI.OL, YAR.OL, CHTR, LULU, GIS, AKZA.AS, SOLB.BR, GALP.LS, TELIA.ST, VNA.DE, SKF-B.ST, DEMANT.CO, COLO-B.CO, CA.PA, RED.MC
- **name_mismatch (11, expected for brand vs legal names):** AMD, IBM, UPS, SLB (Schlumberger vs SLB N.V.), BMW.DE, MUV2.DE, RMS.PA, BBVA.MC, ITX.MC, SEB-A.ST, AIG

Borderline caps: TELIA.ST is 19.99B USD (19,986,072,082) and TEL.OL is 19.90B USD (19,897,546,953). Both sit right at the 20B line, so they can flip with a small price move.

### Step 4: the three failing tickers (yfinance, one at a time, no changes)

Raw output, with fetch times in UTC: `output/ticker_diagnosis.txt` (git-ignored). Each ticker was fetched on 2026-11-05 between 22:27:34 and 22:28:00 UTC, with an 8-second pause between tickers. Key lines:

- **BK** (fetched 22:27:34 UTC): `history(period=1y)` rows=0, nan_close=0. yfinance prints "$BK: possibly delisted; no price data found". `info`: quoteType EQUITY, exchange NYQ, longName None, currency None, marketCap None. The listing is known to Yahoo, but it has no price bars and no company details.
  - Proposal: keep BK in the universe for now and re-check in a few days? Yes / no.
- **AVB** (fetched 22:27:42 UTC): `history(period=1y)` rows=2, nan_close=1. Rows: `2026-08-14 ... 184.059998 ... Dividends 0.0000 Stock Splits 2.793` and `2026-10-05 ... NaN NaN NaN NaN 0 0.7025 0.000`. `info`: longName "AvalonBay Communities Inc", currency USD, marketCap 26283393024. The 2026-10-05 row has a dividend but no prices. The pipeline already skips AVB via the 4-trading-day rule.
  - Proposal: keep AVB in the universe as it is, since it is already skipped automatically? Yes / no.
- **ROG.SW** (fetched 22:27:51 UTC): HTTP 404 `"Quote not found for symbol: ROG.SW"`, then "$ROG.SW: No data found, symbol may be delisted". `history(period=1y)` rows=0, and `info` has no fields.
  - Proposal: replace ROG.SW with RO.SW in `config/universe.csv`? Yes / no. This is a ticker rename, which `common.md` forbids for agents, so it needs Iiro's explicit approval.
- **RO.SW** (not in `config/universe.csv`; fetched 22:28:00 UTC): `history(period=1y)` rows=251, nan_close=0, last bar `2026-11-05 ... Close 399.000000`. `info`: longName "Roche Holding AG", shortName "ROCHE I", quoteType EQUITY, exchange EBS, currency CHF, marketCap 317909598208.

### Decisions and concerns

- No config was changed and no ticker was removed or renamed.
- The brief lists RO.SW as failing, but it is not in the universe and its data is fine. The failing ticker in the universe is ROG.SW.
- The verify run took about 2 minutes 23 seconds (first verified_at 22:22:33 UTC, last 22:24:56 UTC). The `info` calls dominated the run time. The earlier "several hours" note was wrong.
- The nightly data-quality `partial_bar` result is 0. The brief describes a 16:37 run on 2026-11-05 with 345 `partial_bar` warnings, and that did not recur after the full close.
