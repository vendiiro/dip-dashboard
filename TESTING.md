# Testing guide

You have the **Quality-Dip Screen**: a daily dashboard that flags sharp price drops in large US, European and Nordic companies,
a backtest of that rule, and the scheduled run that refreshes it. It is an educational research tool. It gives screen results,
never advice. Please try to break it.

## What you are testing, in one minute
| Piece | What it does | Where to look |
|---|---|---|
| Screener | Pulls daily prices for every stock in `config/universe.csv`, flags dips (1 day ≤ −4%, 5 days ≤ −7%, or ≥ 12% below the 20-day high), scores quality from six fundamentals checks, marks falling knives | `src/dipdash/` |
| Dashboard | One self-contained HTML page: filters, sortable table, row details with a 1-year chart, context charts, data-quality panel | `output/dashboard.html` after a run, or the canonical demo page `docs/sample-output/dashboard-demo.html` (`docs/demo/` is the frozen M0 mock) |
| Digest | Plain-language daily summary: data quality first, market context, candidates with "flagged because", what changed | `output/digest.md`, example in `docs/sample-output/` |
| Backtest | Event study of the rule on 2010-2026 history with costs, baselines, an untouched out-of-sample period and clustered confidence intervals | `python scripts/run_backtest.py`, report in `docs/sample-output/backtest/report.md` |
| Nightly run | `run_daily.bat` + Task Scheduler (Tue-Sat 00:15) | `scripts/`, `START_HERE.md` section 4 |

**The most important result:** the backtest did **not** find that flagged stocks beat their own ordinary days out of sample
(+0.3% at 21 days, 90% interval −1.0% to +1.5%, which includes zero). Fourteen of 27 in-sample cells looked positive; none did out of sample.
The report lists why you should also doubt the *positive* readings (survivorship, one sample, low power). Read it critically.

## Level 1: look only (5 minutes, nothing to install)
1. Open `docs/sample-output/dashboard-demo.html` in a browser (the canonical demo page, synthetic data). Click rows, change filters, sort columns, resize to phone width, switch your system to dark mode.
2. Read `docs/sample-output/backtest/report.md` (charts are next to it). Read "How much to trust this" and "Changes after the first look" first.
3. Read `docs/sample-output/digest_example_midsession_2026-11-02.md` and `docs/decisions.md` (every decision, correction and known gap, dated).

## Level 2: run it (15 minutes, no network needed)
Python 3.11+. In a terminal in this folder:
```
python -m venv .venv
.venv\Scripts\activate            (Windows)   or   source .venv/bin/activate   (macOS/Linux)
pip install pandas numpy pytest yfinance matplotlib
python -m pytest -q
python src/dip_screener.py --demo --out output/demo.html --history
```
Expected: the full suite passes (browser tests skip unless Playwright and a Chromium are installed), then `output/demo.html`, `output/digest.md`, `output/data_quality.demo.csv`, and dated copies in `output/history/`.
`requirements.txt` also lists `openbb` (about 1 GB, only used for the second-source price cross-check) and `playwright` (browser tests and screenshots). Both are optional:
without `openbb` the live run prints "Cross-check skipped" and carries on (the digest then says no cross-check was run).

## Level 3: live data (needs internet)
```
python src/dip_screener.py --out output/dashboard.html --history --open
python scripts/run_backtest.py
```
Expected: nearly every stock; a few have no data at the source (for example Roche, `ROG.SW`) and are listed in `output/data_quality.csv`. Run time for the full universe is not measured yet; the backtest takes about 25 seconds with cached history (`--refresh` downloads a new one).
**Run the screener after the market close.** Run mid-session it uses still-forming bars for open exchanges and the digest warns about it.

## What I most want you to try to break
1. **Wrong numbers.** Pick three flagged stocks in the digest and check their 1-day and 5-day moves against another source (your broker, any finance site). Differences of more than rounding are bugs or data problems.
2. **Failure handling.** Switch the network off partway through a live run, or run with a broken connection. Expected: the run exits with code 2, prints `FAILED: only N of M stocks could be screened`, and **yesterday's dashboard, digest, data-quality log and history are left exactly as they were**. A run that quietly replaces good files with a half-empty dashboard is a bug.
3. **The dashboard.** Keyboard only (Tab, Enter, Space); phone width; light and dark; search for nothing; set filters so nothing matches; a very long company name. Anything clipped, unreadable, or not reachable by keyboard is a bug.
4. **Wording.** Does anything read like advice ("buy", "sell", a price target, "will recover")? It should not. Is anything the screener says stronger than its data supports?
5. **The backtest.** Look for look-ahead (anything from after the signal day used to decide a signal, filter, baseline or the in-sample/out-of-sample split), selection after seeing results, and survivorship. `output/backtests/<date>/spec.json` is what was frozen; `events.csv` lists every event with its returns, so you can recompute a few by hand (entry is the *next* close after the signal day).
6. **Windows scheduling (untested by the author, so please test it):** `powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1`, then `Start-ScheduledTask -TaskName DipDashboard`, then read `output\run.log`. Also: does it catch up after the PC was off at 00:15? Does it run when you are logged out? (It is designed to run only while logged in.)
7. **Prompt injection.** The digest contains third-party headlines that `/daily-review` (a Claude command in `.claude/commands/`) reads. They are cleaned and marked as untrusted. Try to get a headline-like string to change the digest's structure or the review's behaviour.

## Known gaps (already in `docs/decisions.md`, so no need to rediscover them)
- Nothing has been run on Windows. The `.bat` and the PowerShell installer have only been checked by reading and by static tests.
- Prices for Amsterdam, Frankfurt, Paris, Swiss and Oslo lines were not checked against an independent source. US and Helsinki/Stockholm/Copenhagen samples agreed with exchange data.
- Roche (`ROG.SW`) returns nothing from Yahoo; `RO.SW` exists but may be a different share line, so it was not swapped in.
- Headlines come from a free search and are often about the wider market; non-US stocks usually have none.
- The quality score is a plain share of six checks passed. A company with negative return on equity and margin can still score 67 (Intel did).
- `output/run.log` is never rotated. Market holidays are not modelled.
- The backtest universe is today's large companies (survivorship bias), costs are one flat figure, and the index baseline mixes dividend-adjusted stocks with price-only indices.

## How to report what you find
For each finding: what you did, what you expected, what happened (paste the message or attach a screenshot), and the file. A short list is more useful than a long one.
Please say which of the three levels you ran, your operating system, and your Python version.

*Screen results for research. Not investment advice.*
