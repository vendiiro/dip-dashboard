# New since yesterday is stateless (prev on each row)

- Date: 2026-11-02
- Topic: dashboard
- Origin: migrated, old entry 23 of 54 (text verbatim)

---

- 2026-11-02 (M3) "New since yesterday" is stateless: each payload row carries `prev` (the same stock's metrics one bar earlier, same fundamentals), so it works on the very
  first run and cannot go stale if a run is skipped. The plan said "snapshots"; daily snapshots are deferred to M5, where the digest needs "no longer flagged".
