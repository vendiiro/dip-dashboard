# Partial bars are reported, not dropped

- Date: 2026-11-02
- Topic: data
- Origin: migrated, old entry 45 of 54 (text verbatim)

---

- 2026-11-02 (M5) Partial bars (deferred from M2): a last bar dated today is reported as `partial_bar` (warning). My first manual run was at 10:13 Helsinki time on a Monday, with the Nordic exchanges open; it flagged 16 stocks
  and the candidate list differed from the later complete one (Nokia was a dip on a half-finished session). The scheduled 00:15 run never sees this. I did NOT make the code drop such bars: without exchange calendars and time zones it
  cannot know whether a session is over, and a PC outside Helsinki could then discard a finished day. START_HERE says not to run it by hand mid-session. Demo bars now end on the previous business day.
