# Daily run as built (run_daily.bat, install_task.ps1)

- Date: 2026-11-02
- Topic: ops
- Origin: migrated, old entry 40 of 54 (text verbatim)

---

- 2026-11-02 (M5) Daily run, as built: `scripts/run_daily.bat` (CRLF, no locale-dependent date slicing, exit code passed on) runs `src/dip_screener.py --out output\dashboard.html --history`.
  Outputs: `dashboard.html`, `digest.md`, `data_quality.csv`, and dated copies in `output\history\` named by the DATA date (so a market-holiday run does not pile up copies; a rerun on the same data date overwrites
  them and the digest says "same data date as the last saved run"). `scripts/install_task.ps1` registers Tuesday to Saturday 00:15 local time with StartWhenAvailable (catch-up after a missed start),
  RunOnlyIfNetworkAvailable, 1-hour limit, no overlapping runs; `-WakeToRun` and `-Remove` are options. The old START_HERE one-liner (`schtasks /SC DAILY`) ran seven days a week and could not set catch-up: replaced.
