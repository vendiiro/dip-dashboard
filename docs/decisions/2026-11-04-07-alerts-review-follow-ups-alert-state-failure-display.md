# Review follow-ups: alert state, failure display, earnings memory

- Date: 2026-11-04
- Topic: alerts
- Origin: migrated, review bullets 1-3 of 6 (text verbatim)

---

- Alerts are now evaluated once per data date: the first run saves the state as it was (`alerts_state.pre.json`) and later runs for the same date start from it. This replaced reuse and merge, which could keep alerts that had become false by the close.
- A failed alert step now shows as "unavailable" on the dashboard and in the digest and overwrites `alerts_latest.json` with count 0 and an error, so it never looks like a quiet day and the notifier cannot announce a stale file. `notify.ps1` also remembers what it announced (`output/alerts_notified.txt`).
- Alert state for `earnings_window` and `new_low` is kept for 15 days when a stock briefly leaves the evaluated set, so one earnings event does not announce itself repeatedly.
