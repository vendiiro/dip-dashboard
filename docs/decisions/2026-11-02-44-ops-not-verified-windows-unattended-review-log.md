# Not verified: Windows, unattended review, log rotation

- Date: 2026-11-02
- Topic: ops
- Origin: migrated, old entry 47 of 54 (text verbatim)

---

- 2026-11-02 (M5) NOT VERIFIED: anything on Windows (the batch file, the PowerShell installer, Task Scheduler, catch-up after a missed start, behaviour logged out or asleep, daylight-saving changes). `claude -p "/daily-review"`
  unattended (left commented out). `output\run.log` grows without limit (no rotation). Market holidays are not modelled: the run still happens and the digest flags the repeated data date. The first night's run should be checked by hand.
