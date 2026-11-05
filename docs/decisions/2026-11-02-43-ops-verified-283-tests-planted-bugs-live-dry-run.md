# Verified: 283 tests, planted bugs, live dry run

- Date: 2026-11-02
- Topic: ops
- Origin: migrated, old entry 46 of 54 (text verbatim)

---

- 2026-11-02 (M5) VERIFIED: 283 tests pass (the browser ones need Playwright and a Chromium). Ten planted bugs in the new code (guard off, threshold too low, repeat not recognised, stale failure note, non-atomic write, no grouping,
  headline markup kept, everything marked new, yesterday's knife ignored, partial bar never flagged) are all caught. Live dry run of the exact nightly command: 59 stocks, about 70 s, 5-stock cross-check agreed. The digest's 9 candidates
  were recomputed from the raw price file (1-day and 5-day returns within the digest's 0.1% rounding, each meets the rule) and no dip in the data is missing from the digest. `/daily-review` was run by hand from the files
  (283 words, `output/review_2026-11-02.md`).
