# Seed split into src/dipdash/; CLI keeps the seed's flags

- Date: 2026-11-02
- Topic: ops
- Origin: migrated, old entry 5 of 54 (text verbatim)

---

- 2026-11-02 (M1): Seed split into `src/dipdash/` (config, metrics, quality, screen, data, demo, dashboard, cli).
  `src/dip_screener.py` stays as a thin wrapper, so the commands in START_HERE.md are unchanged.
  Options considered for the CLI: subcommands (`run|demo|backtest`) vs the seed's flags. Kept the flags (`--demo`, `--out`, ...)
  because START_HERE and `run_daily.bat` already use them. A `backtest` subcommand is added in M4 if needed.
