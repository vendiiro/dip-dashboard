# OpenBB 5.0.0 provider check; openbb pinned

- Date: 2026-11-02
- Topic: data
- Origin: migrated, old entry 12 of 54 (text verbatim)

---

- 2026-11-02 (M2) OpenBB provider check (openbb 5.0.0, default bundle, per `.claude/skills/openbb-data-pull`): V5 has no `obb.equity` tree; routes are
  per provider. Equity prices: `nasdaq.equity.historical` (US), `cboe.equity.historical` (US; one session behind), `nasdaq.nordic.historical`
  (Helsinki, Stockholm, Copenhagen), `tmx` (Canada). Nothing for Amsterdam, Xetra, Paris, Switzerland or Oslo. All return raw closes, not
  dividend-adjusted. Fundamentals: Nasdaq (US ratios), Nasdaq Nordic, SEC (blocked by network policy here). `openbb-yfinance` 2.1.0 exists on PyPI but
  was not installed or tested (it would wrap the same Yahoo source). Pinned `openbb==5.0.0` in requirements.txt because the V5 provider set is in flux.
