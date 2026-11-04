# DATA-10 · nightly .bat: one retry after exit code 2, rotate run.log at about 5 MB

**Owner:** ops-runner · **Reviewer:** none required (no reader-facing wording); orchestrator merges · **Skills:** `engineering:deploy-checklist`, `openbb-data-pull` (exit 2 = too few stocks screened) · **Size:** S
**Planned 2026-11-04 (plan only; nothing changed yet).**

## Understanding
`scripts/run_daily.bat` runs the screen once and passes the exit code on. Exit 2 usually means a data source was down or
rate-limited, which often clears within minutes. Add exactly one retry 20 minutes after exit 2, and keep `output\run.log`
from growing without limit (TESTING.md:61, decisions.md:146). Exit 3 (setup) and crashes are never retried.

## Facts checked
- `run_daily.bat:16-19`: one run, `set RC=%errorlevel%`, `if not "%RC%"=="0" exit /b %RC%`; notify only after exit 0.
- `install_task.ps1:34-35`: `-ExecutionTimeLimit 1 hour`. A run plus a 20-minute wait plus a second run can pass 1 hour; the run time for 348 tickers is not measured. Task Scheduler would kill the retry.
- `tests/test_digest.py:351` already checks `install_task.ps1` text, so that file's flags are pinned by a test.
- `timeout /t` fails under Task Scheduler (no console input), so the wait must use `ping -n` or `powershell Start-Sleep`.

## Changes
1. `run_daily.bat`: move the run into a `:run` label. After it, `if "%RC%"=="2" if not defined RETRIED` then log `==== exit code 2, retrying in N s`, wait, set `RETRIED=1`, `goto run`. Log the final exit code of each attempt. Notify and exit logic unchanged for the final result.
2. `run_daily.bat`: before the first `start` line, rotate. If `output\run.log` is over the limit, `move /y` it to `run.log.1` (replacing the older `.1`; the previous log is kept, never edited), then start a fresh log with a "rotated" line.
3. Test hooks, both optional env vars: `DIPDASH_RETRY_WAIT=1200` (seconds), `DIPDASH_LOG_MAX=5242880` (bytes), and `DIPDASH_PYTHON` (path overriding `.venv\Scripts\python.exe`). Defaults are the real values, so the scheduled task needs no change.
4. `install_task.ps1`: raise `-ExecutionTimeLimit` to 2 hours (needs the lock added; the backlog lists only the .bat).
5. Update the header comment in the .bat (exit codes, retry, rotation).

## Offline checks (Linux sandbox)
1. A pytest that reads the .bat and asserts: one retry label guarded by `RETRIED`, retry only on 2, no `timeout`, rotation present, defaults 1200 and 5242880. Same style as `tests/test_digest.py:351`.
2. A `skipif(sys.platform != "win32")` pytest that runs the .bat with `DIPDASH_PYTHON` pointing at a stub that exits 2 then 0, `DIPDASH_RETRY_WAIT=1`, and asserts log lines and exit 0. It skips here; it runs on Iiro's PC.
3. `pytest -q` full suite. I cannot run `cmd.exe` here, so the real batch behaviour is unverified until Iiro runs it.

## Check once on Iiro's PC (PowerShell, in the repo folder)
```
$env:DIPDASH_PYTHON="$PWD\tests\stubs\exit2_then_0.cmd"; $env:DIPDASH_RETRY_WAIT="5"; $env:DIPDASH_LOG_MAX="2000"; cmd /c scripts\run_daily.bat; echo "exit $LASTEXITCODE"; Select-String "====" output\run.log | Select -Last 8; dir output\run.log*
```
Expect: exit 0; lines "exit code 2", "retrying in 5 s", a second "start", "exit code 0"; and `run.log.1` present. Then
`Remove-Item Env:DIPDASH_*`. The stub path needs the stub file from the test-engineer request below.

## Risks
Retry makes a bad night last about 20 minutes longer before notify. A stale `run.log.1` is overwritten at the second rotation (see open question 2). cmd `%errorlevel%` inside parenthesised blocks needs delayed expansion; use plain `goto` labels to avoid it.

## Open questions for Iiro
1. Retry wait: **A (recommended) fixed 20 min as in the backlog**; B 10 min; C 20 min only when the cause is a data-source outage (needs a new exit code, integrator).
2. Logs kept: **A (recommended) run.log plus one `.1`** (about 10 MB max); B keep three (`.1` to `.3`); C dated archive names.
3. If the retry also fails: **A (recommended) exit 2 as today, digest keeps yesterday's files**; B also show a toast via `notify.ps1` (new text, needs wording-guard).

## Follow-on only: D3 raw-data retention (answered A)
Not part of DATA-10. `DATA-9` (data-engineer, `scripts/raw_retention.py`) archives, never deletes: keep every pull 60 days, then the first of each week. Dry run by default. A later step could add one optional `--dry-run` call in the .bat; not planned now.

## Handoff request list
- test-engineer: add `tests/stubs/exit2_then_0.cmd` and the two tests; orchestrator: add them to `docs/agents/ownership.csv` and add `scripts/install_task.ps1` to this task's locks.

**Decision-log line:** 2026-11-04: nightly run retries once, 20 minutes after exit code 2 only; `run.log` rotates at 5 MB to one `.1` file (pending Iiro's answers).
