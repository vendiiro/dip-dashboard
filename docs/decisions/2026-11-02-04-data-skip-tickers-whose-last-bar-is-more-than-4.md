# Skip tickers whose last bar is more than 4 weekdays old

- Date: 2026-11-02
- Topic: data
- Origin: migrated, old entry 7 of 54 (text verbatim)

---

- 2026-11-02 (M1): New rule from CLAUDE.md: tickers whose last bar is more than 4 weekdays old (`[data] max_stale_trading_days`)
  are skipped and listed in the payload's `data_quality`. Exchange holidays are not modelled, so a long holiday weekend can skip a
  ticker one day early. The CSV log (`output/data_quality.csv`) comes in M2.
