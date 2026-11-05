# Changes after the first look (runs 1 and 2)

- Date: 2026-11-02
- Topic: backtest
- Origin: migrated, old entry 34 of 54 (text verbatim)

---

- 2026-11-02 (M4) CHANGES AFTER THE FIRST LOOK (run 1, spec 90205cfc, rows kept in trials.csv; run 2, spec 3a2020e8). Found by reading run 1's own numbers (1 lowers significance, 2 has no predictable direction, 3 is a data fix; the freeze was before run 1, which was a full run, so it is not before anyone saw a number):
  (1) the independent same-stock random-day placebo gave p = 0.002 next to an interval that included zero. It ignores that events share dates, so it understates noise (a test shows it rejecting far too often on
  synthetic data with a shared market factor and no effect); replaced by a date-shift placebo that moves all events together; the independent one stays in results.csv, labelled.
  (2) baseline days now need a computable signal (a stock's first year had counted as "non-dip"). (3) 92 zero-volume bars removed (91 holiday placeholders, 1 corrupt price: NOVO-B.CO 2010-05-14, price doubled, volume 0).
  The primary cell did not move (+0.27%, -1.01% to +1.50%, n = 1,504 in both runs).
