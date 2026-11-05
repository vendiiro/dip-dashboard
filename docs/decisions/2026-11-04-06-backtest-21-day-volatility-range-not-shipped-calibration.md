# 21-day volatility range not shipped (calibration failed)

- Date: 2026-11-04
- Topic: backtest
- Origin: migrated, old entry 54 of 54 (text verbatim)

---

- 2026-11-04 (21-day volatility range, NOT shipped) New `src/dipdash/forecast.py` (`range_forecast`, `range_label`, `all_ranges`), calibration `scripts/run_forecast_calibration.py`, results in `output/backtests/2026-11-04_forecast/`. Volatility range only: no direction, no price target (direction is not forecastable with ~80 independent OOS months).
  Method: GARCH(1,1)-t via `arch` 8.0.0 (installed into the project venv only, added to requirements.txt), zero conditional mean, filtered historical simulation (bootstrapped standardised residuals, 1000 paths), trailing 750 returns (min 400, else None with a reason); baselines EWMA 0.94 and naive 60-day vol x sqrt(21); non-convergence falls back to EWMA and is flagged `ewma_fallback`.
  Pre-stated criterion (in the module docstring before any result): overall OOS 80% coverage 0.80 +/- 0.04 AND dip-state 0.80 +/- 0.06; two attempts (raw, then one in-sample global scale factor).
  Result (170 stocks, 33,439 walk-forward origins every 21 days, OOS = last 40% of dates, 14,764 origins, 807 in a dip state, month-clustered bootstrap): attempt 1 overall 0.785 [0.759, 0.808] PASS, dip state 0.725 [0.623, 0.819] FAIL; attempt 2 (k = 0.956, in-sample, shrinks the range) overall 0.768 PASS, dip 0.714 FAIL. DECISION: the range does not ship on the dashboard. The model is too narrow after drops (and in 2020 and 2022: 0.759, 0.748); EWMA was closer in dip states (0.779) but was not the pre-stated primary and no third attempt is allowed. A smoke run on 6 stocks was looked at before the full run (plumbing check only; no change was made because of it).
  Limits: survivorship bias, correlated stocks (88 independent months), GARCH underreacts to jumps and earnings gaps, 2.6% of fits fell back to EWMA. Data note: ABI.BR has 70 zero/negative closes that `clean_bars` keeps; the calibration drops them (the backtest does not).
