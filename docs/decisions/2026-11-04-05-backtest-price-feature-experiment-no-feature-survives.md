# Price-feature experiment: no feature survives Holm

- Date: 2026-11-04
- Topic: backtest
- Origin: migrated, old entry 53 of 54 (text verbatim)

---

- 2026-11-04 (price-feature experiment, family `features_2026-11-04`, spec 2190157755c9916b) Pre-registered cheap test on the 171-stock history (parent backtest spec 8583ea959c7ce228; V1 OOS 21d events reproduced: 4,409). Six price-only features at signal close (volume ratio, 12-1 momentum, vol-scaled 1d drop, days since 52w high, 60d realised vol, drawdown from 52w high) vs 21d forward return minus the same-day universe mean; in-sample (4,492 events) fixes the sign only; out-of-sample Spearman rho with 90% month-clustered bootstrap, Holm across 6 at 0.10.
  RESULT: no feature survives Holm (all adjusted p = 1.0; OOS |rho| <= 0.017, every 90% interval includes zero). Minimum detectable rho about 0.05 to 0.09, so a smaller association cannot be resolved here. Conclusion: no tested price feature shows detectable out-of-sample signal in this sample; the dashboard stays a listing and monitoring tool.
  Caveats: survivorship (today's constituents), events cluster in months, no costs (rank correlation), same-day universe mean only removes market and period effects. Code `src/dipdash/feature_experiment.py`, `scripts/run_feature_experiment.py`; output `output/backtests/2026-11-04_features/`; trial log `output/backtests/trials_features.csv` (new file because trials.csv holds mean excess returns with a `primary` flag and does not fit rank correlations).
