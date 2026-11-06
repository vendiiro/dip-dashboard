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

Fixed (task 1b): not the non-ASCII folder itself. Two test helpers did `Path(unquote(urlparse(uri).path))`, which gives `C:...` on Windows; now `url2pathname`. Test-only change, production code unaffected; tests/test_browser.py 74 passed.

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

## Task 11: null calibration of the primary cell (RES-12a)

Test: `tests/test_backtest.py::test_primary_cell_false_positive_rate_near_nominal` (runs only with `DIP_SLOW=1`). 200 seeded synthetic null universes (seeds 5000-5199; 14 stocks, 1100 bars, `r = beta * f + e`, common factor, no dip effect) through the real V1 path (`build_days`, `add_events`, `add_peer_returns`, `add_periods`, `summarize`), cell V1_price_only / 21 days / All / OOS, 500 bootstrap draws, 90% interval. `placebo_draws` was set to 20, the lowest the path needs, because only the `ex_own` interval is used.

| Item | Value |
|---|---|
| Replicates (usable) | 200 (200) |
| Share of 90% `ex_own` intervals excluding zero | 11.5% (nominal 10%) |
| Accepted band (95% binomial around 10%, n=200) | 5.8% to 14.2%: inside, test passes |
| Run time | about 62 s for the 200 replicates (about 0.3 s each; the CPU was shared with other agents) |
| OOS events per replicate (mean) / months with events | 49.8 / 12.5 |
| Mean interval width / mean half-width | 0.0478 / 0.0239 |
| Mean estimate / SD of estimate across replicates | +0.0048 / 0.0138 |

Second case at the real run's scale (`test_primary_cell_false_positive_rate_at_real_scale`: 59 stocks, 4500 bars, 100 replicates, seeds 5000-5099, band upper bound 15.9%; run time 209 s):

| Item | Value |
|---|---|
| Share of intervals excluding zero | 3.0% (lower above zero 3.0%, upper below zero 0.0%) |
| Mean estimate / SD across replicates | +0.02 pp / 0.43 pp |
| Mean half-width / (1.645 x SD of estimates) | 1.40 |
| OOS events / months with events (mean) | 1,139 / 76.4 |

Small case, per tail: lower bound above zero 9.5%, upper bound below zero 2.0%; half-width / (1.645 x SD) = 1.05.

Plain meaning: the test passes, but for the wrong reason. The lower bound was above zero in 9.5% of replicates and the upper bound below zero in 2.0% (nominal 5% each). The estimate is biased upward (mean +0.48 pp, about 5 SE). Without that bias the intervals exclude zero in only about 6.5%, so they are also too wide. A two-sided rate cannot detect bias: shifting every estimate down by 1 pp still passes. Cause (synthetic experiments in the Task 11 review): the own baseline is the stock's mean over the same out-of-sample window, which includes the drop that triggered each event. It is not Jensen, the factor, beta or the cooldown. The bias shrinks roughly as 1/(out-of-sample length). This setup has 320 out-of-sample bars, against about 1,680 in the real run. At the real length (59 or 171 stocks, 4500 bars) the null bias is about +0.08 to +0.15 pp at 21 days and about +0.2 pp at 63 days. There, coverage depends on the volatility model: intervals exclude zero in 1.7-3.5% of replicates with constant volatility (too wide) and 7-10% with volatility regimes. For the published primary cell (+0.27%, -1.0% to +1.5%) this means a bias-adjusted estimate of about +0.1 to +0.2% and the same conclusion (no out-of-sample edge shown); the wider-than-needed interval lowers power, so a modest real edge could hide inside it. In the same null runs, ex_index averaged +0.21% and excluded zero 43% of the time, so the published index-excess interval is not evidence of an edge. Nothing in the method was changed; the question for Iiro is whether to fix the baseline (for example by using the stock's mean excluding the event windows) in a new, pre-registered spec. The real-scale case here (constant volatility, 3.0%, ratio 1.40) agrees with that: a low rate means too-wide intervals, which costs power.

Limits: the universe is synthetic, so this shows the method's behaviour under this model only (independent daily returns, one factor, 14 stocks, 1100 bars), not on real data. It says nothing about fat tails, volatility clustering or the real event counts. Not tuned; nothing in the method was changed.
