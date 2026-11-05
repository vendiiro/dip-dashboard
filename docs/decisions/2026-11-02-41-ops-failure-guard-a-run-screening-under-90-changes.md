# Failure guard: a run screening under 90% changes nothing

- Date: 2026-11-02
- Topic: ops
- Origin: migrated, old entry 44 of 54 (text verbatim)

---

- 2026-11-02 (M5) FAILURE GUARD, found by testing and changed: a run that screens fewer than `[data] min_screened_fraction` of the universe exits with code 2, leaves the dashboard, digest, quality log and history
  byte-for-byte untouched, and writes `data_quality.failed.csv` (removed again by the next good run). I first set the minimum at 50%. A half-dead network (my test) screened 33 of 60 stocks and passed, replacing a 59-stock
  dashboard with a 33-stock one. A normal night screens 59 of 60 (only Roche is missing), so the default is now 90% (54 of 60). My first attempt at the test did not cut the network at all (I overrode only the uppercase proxy
  variables); the second attempt did, and the final run with the 90% guard failed as it should with all six files unchanged. All writes are now atomic (temp file, then swap), so a crash cannot leave a half-written dashboard.
