# Trigger alerts are informational only

- Date: 2026-11-04
- Topic: alerts
- Origin: migrated, old entry 52 of 54 (text verbatim)

---

- 2026-11-04 (trigger alerts) New `src/dipdash/alerts.py`, `config/alerts.toml`, `scripts/notify.ps1`; state in `data/alerts_state.json` (atomic write). INFORMATIONAL ONLY: each alert says a research condition the user set became true; none says to act, and a test scans every generated string and these files for banned advice words.
  Conditions (daily closes up to the data date only, no intraday, no network): recovery (close back above the 20-day average, below it the day before), rsi_rebound (RSI(14) from below 30 to 30 or above, same Wilder seed as metrics.rsi14), new_low (close below the lowest close of the previous 60 days; shown as a caution),
  drop_continues (a further 1-day fall of 4% or more for a stock flagged at the previous close; caution), level_cross (user price level, up/down/both, own currency), earnings_window (from the earnings dict passed in, thresholds 5 and 10 trading days; never fetched, the row's own `earn` is ignored), newly_flagged / no_longer_flagged (vs row["prev"]["dip"]).
  Evaluated for flagged candidates plus the [[watch]] list (empty by default). Fire-once: last boolean per (ticker, condition) is stored; an alert is emitted only on false -> true. First run, or missing/corrupt state, is quiet: state is recorded and only one summary of newly flagged names is emitted.
  A stock leaving the evaluated set loses its state (fresh if it returns); stale bars or a missing earnings entry carry the old state over. Ranking: info before caution, quality score descending, then 5d residual (else 5d move) ascending. Notification: ONE balloon, count plus top 3 headlines; JSON file `output/alerts_latest.json` for the dashboard.
  Limits: thresholds are untested defaults, nothing here was backtested and no claim is made that any condition predicts anything; holidays are not modelled in "trading days"; earnings dates come from free, non-point-in-time data.
