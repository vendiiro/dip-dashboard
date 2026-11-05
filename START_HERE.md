# Start here

**Where things stand (2026-11-05, see `docs/STATUS.md`).** The universe has 348 tickers (`config/universe.csv`). A live run on 2026-11-02 covered the original 60 tickers (59 had data). The current code with all 348 names has not run live, and nothing has been run on your Windows PC yet. The last full test suite run: 907 passed, 3 skipped.

**Next steps for Iiro on Windows (none done yet):**
1. Re-register the scheduled task: `powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1` (not done).
2. `python scripts/verify_universe.py --limit 10` to check the 59 US tickers added earlier (not done).
3. Full live run of all 348 names: `python src/dip_screener.py --out output/dashboard.html --open`; read `output/data_quality.csv` first and send back anything flagged (not done).
4. `python -m dipdash.registry backfill --root output/backtests` (not done).

## 1. Set up (about 10 minutes)
1. Unzip this folder somewhere permanent, for example `C:\Users\<you>\Documents\dip-dashboard`.
2. Install Python 3.11+ and Claude Code if you have not already.
3. In a terminal inside the folder:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   openbb-build
   ```
   If `pip install openbb` fails or has no equity price provider, that is fine: the seed works with yfinance.
4. Check the seed works without network: `python src/dip_screener.py --demo --out output/demo.html`
5. Check live data: `python src/dip_screener.py --out output/dashboard.html --open`
6. After a live run, read `output/data_quality.csv` first (stale or missing tickers, cross-check results). `--no-crosscheck` skips the second-source check; `python -m pytest` runs the tests.
7. The dip-rule backtest: `python scripts/run_backtest.py` (about 25 seconds with cached history; `--refresh` downloads a new history). It writes `output/backtests/<date>/report.md`, with `spec.json` frozen before any result is computed and a running `output/backtests/trials.csv`.
8. To look at the dashboard in all four variants (desktop and phone, light and dark): `python scripts/screenshots.py output/dashboard.html --out output/screens` (needs `playwright install chromium` once).

## 2. Start Claude Code in this folder
```
cd path\to\dip-dashboard
claude
```
Claude Code reads `CLAUDE.md` automatically. It will begin each task by explaining the plan and
which skills it will use, because that is a rule in `CLAUDE.md`.

## 3. First prompt (copy and paste)
> Read CLAUDE.md, docs/research-report.md and src/. Following Rule 1, start by explaining your
> plan and which skills you will use. Then work through these milestones, one at a time, and
> stop after each so I can review:
> 1. Refactor the seed into the target structure, with pytest tests on synthetic data.
> 2. Add an OpenBB data layer with yfinance fallback; verify five US and five European tickers
>    against a second source and tell me what you find.
> 3. Redesign the dashboard using dashboard-design (and dataviz / frontend-design if present).
>    Screenshot it at desktop and phone width, light and dark.
> 4. Build the event-study backtest of the dip rules with backtest-hygiene and show me the report
>    and how much to trust it.
> 5. Add the daily run: `scripts/run_daily.bat`, a digest in `output/digest.md`, and Task Scheduler setup.

## 4. Daily updates after the close (Windows)
After milestone 5 works by hand, schedule it. In a PowerShell window in the project folder:
```
powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1
```
That registers a task named `DipDashboard` that runs `scripts\run_daily.bat` **Tuesday to Saturday at 00:15 local time** (after the US and
European closes, so it covers the Monday to Friday sessions). If the PC was off or asleep at that time, Windows runs it as soon as possible
after the next start. Options: `-Time 00:30`, `-WakeToRun` (wake the PC from sleep), `-Remove` (delete the task). It runs only while you are
logged in. Check it by hand with `Start-ScheduledTask -TaskName DipDashboard` and read `output\run.log`.

Each run refreshes `output\dashboard.html` and `output\digest.md`, writes `output\data_quality.csv`, and keeps dated copies in
`output\history\` (named by the *data* date, so a run on a market holiday does not pile up copies). If a run cannot screen at least half of the
stocks (for example the network was down) it exits with code 2, leaves yesterday's files untouched and writes `output\data_quality.failed.csv`.
Do not run it by hand in the middle of a trading day: the latest bars are still forming, and the digest warns about it.

Optional: let Claude write a plain-language review. Try `/daily-review` by hand first; then remove the `REM` in front of the
`claude -p` line in `scripts\run_daily.bat`. The review reads `digest.md`, which contains third-party headlines (cleaned and marked as untrusted text).

## 5. Useful commands inside Claude Code
- `/daily-review` reviews today's output and writes a short summary.
- `/backtest` runs the backtest workflow with the hygiene checklist.
- Ask "which skills are available and which fit this task?" any time.

## Reminders
- Thresholds are untested defaults until the backtest says otherwise.
- Free data (especially fundamentals) can be stale or wrong. Verify before acting on anything.
- This is an educational tool, not investment advice.
