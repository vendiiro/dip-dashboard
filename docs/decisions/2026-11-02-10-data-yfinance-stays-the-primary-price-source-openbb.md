# yfinance stays the primary price source; OpenBB verifies and falls back

- Date: 2026-11-02
- Topic: data
- Origin: migrated, old entry 13 of 54 (text verbatim)

---

- 2026-11-02 (M2) DECISION: **yfinance stays the primary price source; OpenBB is the verifier and the fallback**, not the other way round
  (CLAUDE.md says "OpenBB first"). Reasons: the screener needs dividend-adjusted closes, which no OpenBB provider in this bundle returns, and OpenBB
  covers only about half the universe. Fallback bars (used only if Yahoo returns nothing for a ticker) are unadjusted and logged as `price_source` warnings.
