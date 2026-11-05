# Backtest design frozen in spec.json before any return

- Date: 2026-11-02
- Topic: backtest
- Origin: migrated, old entry 32 of 54 (text verbatim)

---

- 2026-11-02 (M4) Backtest design, frozen in `output/backtests/<date>/spec.json` BEFORE any return is computed (a test checks the spec exists even if the run crashes):
  price-only dip rule exactly as the dashboard applies it (a test compares the vectorised signals with `metrics.py` + `screen.py` bar by bar and checks they are causal),
  entry at the NEXT close, exit h = 5 / 21 / 63 bars later, 21-bar cooldown per stock, 0.10% round-trip cost with 2x and 4x sensitivity, 60/40 time split at 2020-02-06 with
  in-sample events whose window crosses the cutoff dropped, history from 2010-01-04 (bars from 2008-08 only as warm-up), 59 of 60 stocks (ROG.SW has no data).
  Variants: V1 price-only (primary), V2 without falling knives, V3 with today's quality score (INDICATIVE: today's fundamentals leak into the past).
  ONE pre-registered question: V1, 21 days, out of sample, all regions, excess over the same stock's non-dip days, before costs; supported only if the 90% month-clustered
  bootstrap interval excludes zero. Everything else is descriptive. 9 headline tests; every run is appended to `output/backtests/trials.csv`.
