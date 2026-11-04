# Data dictionary: `data/stocks.csv` (one row per screened stock, data date 2026-11-04)

Returns and drops are fractions (0.05 = 5%), in the stock's own currency. "Own index" is the stock's country index where one is configured, otherwise the regional index.

| Column | Meaning |
|---|---|
| `ticker`, `name`, `region`, `sector`, `currency` | Identity. Region is US, Europe or Nordic. Tickers use Yahoo format (`ASML.AS`, `NESTE.HE`, `BRK-B`). |
| `asof` | Date of the stock's last bar (US stocks 2026-11-03, European stocks 2026-11-04 mid-session). |
| `price` | Last adjusted close. |
| `ret_1d`, `ret_5d`, `ret_1m` | 1-day, 5-trading-day and 21-trading-day returns. |
| `below_20d_high`, `below_52w_high` | Close versus the highest close of the last 20 and 252 bars (negative = below the high). |
| `vs_200d_avg` | Close versus its 200-day simple average. |
| `rsi14` | 14-day Relative Strength Index (0 to 100; under 30 means a fast fall relative to recent moves). |
| `volume_ratio` | Last volume divided by the average of the previous 20 days. |
| `z_5d` | The 5-day move in standard deviations of that stock's usual 5-day moves. |
| `index`, `index_symbol` | The index this stock is compared with. |
| `ret_5d_vs_index` | `ret_5d` minus the index's 5-day move. |
| `beta_raw`, `beta`, `beta_side` | Sensitivity to the index: OLS slope of daily returns over the previous 252 days (excluding the last 5). `beta` is clipped to 0..3; `beta_side` is `floor` or `cap` when clipping happened. |
| `resid_1d`, `resid_5d` | Market-adjusted move: stock return minus `beta` times the index return. |
| `resid_5d_z` | `resid_5d` divided by the residual's usual 5-day spread. A ranking aid, not a p-value. |
| `quality_score` | Share (0 to 100) of the applicable quality checks that passed: ROE at least 12%, net margin at least 8%, debt/equity at most 150% (300% for Utilities and Real Estate), positive free cash flow, positive revenue growth, market cap at least 20B USD. Banks and insurers skip the debt and free-cash-flow checks. |
| `quality_checks_scored`, `quality_checks_passed` | How many checks had data and applied, and how many passed. Fewer than 6 means the score rests on less evidence. |
| `forward_pe`, `trailing_pe` | Valuation context from a free source (current only, not point-in-time). |
| `setup` | Screen label: `Quality dip`, `Falling knife`, `Dip, low quality`, `Dip, no fundamentals` or `No dip`. |
| `is_dip` | True if any dip rule is met: 1-day at most -4%, 5-day at most -7%, or at least 12% below the 20-day high (defaults; untested). |
| `falling_knife_condition` | True if below a falling 200-day average and at least 35% below the 52-week high. |
| `partial_bar` | True if the last bar is dated today (the session may still be open). |
| `earnings_label` | `reported_recently` (within 5 trading days), `reports_soon` (within 10) or `none`. `none` also covers stocks with no usable date. |
| `earnings_last`, `earnings_next`, `earnings_days_since`, `earnings_days_until` | Report dates from a free source (can be missing or a day off). Day counts exclude the data date. |
| `flagged_because` | The rules that flagged the stock, in words. |

## Other files

- `quality_checks.csv`: `ticker, check, label, passed (True/False/empty), value, not_applicable`.
- `prices_daily.csv.gz`: `ticker, date, close, volume`; adjusted closes; rows with missing closes (holidays) are already left out.
- `backtest_events_171stocks.csv.gz`: one row per stock-day that was a candidate event. `ev_V1_price_only` marks the price-only dip rule; `fwd5/21/63` are forward returns
  (entry at the next close); `ew*` is the mean forward return of all other stocks signalling on the same date; `idx*` is the regional index over the same window;
  `period*` is `IS` (in sample), `OOS` (out of sample) or `purged`; `suspect*` marks windows with suspicious data. Today's constituents only (survivorship bias).
- `features_results.csv`: `stat` is `spearman` (rank correlation with the 21-day forward return) or `tercile_top_minus_bottom`; `est, lo, hi` are the estimate and its 90%
  month-clustered interval; `p_holm` is the multiple-testing-adjusted p-value; `mde_80` is the smallest effect detectable with 80% power.
- `trials.csv`, `trials_features.csv`: the log of every variant tried (needed to judge multiple testing).
- `forecast_results.csv`: coverage of the 80% volatility range out of sample, by method. The range did not pass its criterion and is not shown on the dashboard.
