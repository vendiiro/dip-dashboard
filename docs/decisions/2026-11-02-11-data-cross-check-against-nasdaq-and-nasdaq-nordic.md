# Cross-check against Nasdaq and Nasdaq Nordic agrees

- Date: 2026-11-02
- Topic: data
- Origin: migrated, old entry 14 of 54 (text verbatim)

---

- 2026-11-02 (M2) Cross-check result (docs/m2-data-verification.md): 5 US + INTC vs Nasdaq: 63 days each, max difference 0.005%. 5 Nordic vs Nasdaq Nordic:
  64 days each, identical. Market caps agree within 0.07%. ROE and net margin differ by period (trailing vs last full year; JNJ and Ericsson differ most)
  but all 20 pass/fail outcomes at the 12% / 8% thresholds agree; Kone and Ericsson margins are within 1 point of the 8% line. Debt/equity is defined
  differently by the two sources and is not comparable. The daily run re-checks 5 random US/Nordic tickers (`--no-crosscheck` skips it).
