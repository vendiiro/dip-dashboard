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
  - info: `crosscheck_ok` 5 (AJG, APH, BLK, CTAS, NOW), `empty_last_bar` 10 (AVB and 9 Nordic/Euronext names whose last bar is 2026-11-04)
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

Borderline caps: TELIA.ST 20.0B and TEL.OL 19.9B USD sit right at the 20B line, so they can flip with a small price move.

### Step 4: the three failing tickers (yfinance, one at a time, no changes)

- **BK** (Bank of New York Mellon): `history(period=1mo)` returns 0 rows and yfinance says "possibly delisted; no price data found". `Ticker.info` still returns quoteType EQUITY, exchange NYQ, currency USD, so the listing exists but has no price bars.
  - Proposal: keep BK in the universe for now, and re-check in a few days? Yes / no.
- **AVB** (AvalonBay): `history(period=1y)` returns 2 rows: 2026-08-14 with a close of 184.06, and 2026-10-05 with only a dividend and NaN prices. The pipeline already skips AVB via the 4-trading-day rule.
  - Proposal: keep AVB in the universe as it is, since it is already skipped automatically? Yes / no.
- **ROG.SW** (Roche): Yahoo returns HTTP 404 "Quote not found for symbol: ROG.SW" and 0 rows.
- **RO.SW** (not in `config/universe.csv`): `history(period=1y)` returns 251 bars with no NaN closes, last bar 2026-11-05, close 399.00 CHF. `info` says longName "Roche Holding AG", shortName "ROCHE I", quoteType EQUITY, exchange EBS, currency CHF, marketCap about 317.9B CHF.
  - Proposal: replace ROG.SW with RO.SW in `config/universe.csv`? Yes / no. This is a ticker rename, which `common.md` forbids for agents, so it needs Iiro's explicit approval.

### Decisions and concerns

- No config was changed and no ticker was removed or renamed.
- The brief lists RO.SW as failing, but it is not in the universe and its data is fine. The failing ticker in the universe is ROG.SW.
- The verify run took several hours of network time under Yahoo's rate limit. The `info` calls with retries dominated the run time.
- The nightly data-quality `partial_bar` result is 0, so the 2026-11-05 "partial bar" concern from `STATUS.md` does not recur after a full close.
