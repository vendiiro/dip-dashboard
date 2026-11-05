# Verification: screenshots and browser tests

- Date: 2026-11-02
- Topic: dashboard
- Origin: migrated, old entry 30 of 54 (text verbatim)

---

- 2026-11-02 (M3) Verification: `scripts/screenshots.py` renders 1280 px and 390 px, light and dark, and fails on console errors or sideways scroll; run on demo and on a live run
  (59 stocks), all 8 combinations clean. `tests/test_browser.py` (15 tests: filters, sorting, row open/close, data-quality panel, HTML-injection, rule agreement) is skipped if no
  browser is available. Mutation check: 5 planted template bugs (any URL becomes a link, only the 5-day rule, yesterday = today, sort never toggles, text inserted as HTML) are all caught.
