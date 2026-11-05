# Data-quality log checks; raw pulls never overwritten

- Date: 2026-11-02
- Topic: data
- Origin: migrated, old entry 19 of 54 (text verbatim)

---

- 2026-11-02 (M2) Data-quality log: `output/data_quality.csv` is replaced each run (dated copies come with the daily run in M5). Checks: no data, duplicate or
  unsorted dates, non-positive prices, daily moves over 40%, gaps over 5 weekdays, >5% missing closes, stale bars, currency vs exchange suffix, duplicate
  company names, missing fundamentals. Raw price pulls go to `data/raw/<source>/<date>.csv.gz` (CSV, to avoid adding pyarrow) and are never overwritten;
  each fundamentals pull is kept in `data/raw/yfinance_fundamentals/`. Deferred to M5: marking a partial last bar (the run happens after the close).
