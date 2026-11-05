# New per-row payload fields (sector, dip, why, setup, s200_falling)

- Date: 2026-11-02
- Topic: dashboard
- Origin: migrated, old entry 10 of 54 (text verbatim)

---

- 2026-11-02 (M1): Added fields to each row: `sector`, `dip`, `why` (which rules fired), `setup`, `s200_falling`, and per-check `value`.
  The v0 template ignores them; M3 uses them. Verified: demo output equals the seed's on all 60 rows and every original field.
