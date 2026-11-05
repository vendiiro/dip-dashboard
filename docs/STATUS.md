# Project status: Dip Screen (long-only, US + Europe)

**As of 2026-11-05.** Repo: https://github.com/vendiiro/dip-dashboard, branch `dashboard-brief-compact-table`.
Owner: Iiro. This is an educational research tool. It lists screen results (candidates to research). It never gives advice.
Read this first, then `docs/AGENTS.md` (who owns which file), `docs/BACKLOG.md` (task list) and `CLAUDE.md` (rules).

## In one paragraph
A static HTML dashboard and a markdown digest, rebuilt every night after the US close from daily bars of 348 US and
European blue chips. It flags sharp drops, shows how many of six quality checks each company passed, and marks
falling knives. A pre-registered backtest found **no out-of-sample edge** for the dip rules, so everything on the page
is a description, not a tested filter. The code, tests and page are in good shape on demo data and synthetic tests. A live
pull of the original 60 stocks worked on 2026-11-02 (59 had data). **The current code with all 348 names has not been run
live, and nothing has been run on Iiro's Windows PC.**

## What exists now
| Area | State |
|---|---|
| Page (`src/template.html`) | Done on demo data: brief, 4 tiles, filters, sortable table with phone cards, detail panel, two charts, definitions footer, stale/failure/empty states. Light and dark, desktop and phone. Last checks reported 0 console errors, 0 overflow, axe clean. |
| Wording | Neutral: "Dip · passes 3 of 4 scored checks (2 no data)", "Dips meeting the check thresholds", "Quality score", "Dip · data looks unreliable". Default sort is the size of the drop. No "buy", "sell", "top picks". A wording scan is set up in pre-commit and in the CI workflow. |
| Screening (`screen.py`, `quality.py`) | Dip rule, falling-knife flag, six-check quality score with "scored on n/6". Net margin above 0 must pass (D1 B). ROE above 100%, or ROE and debt/equity both missing, is "distorted". These are definitions, not tested filters. |
| Pipeline (`cli.py`, `data.py`, `sources.py`) | OpenBB first, yfinance fallback, typed `Sources` bundle, offline fake Yahoo for tests, data-quality checks, 4-trading-day stale rule. |
| Digest and alerts | `digest.md` with a fixed caveat; trigger alerts (neutral names such as "RSI back above 30"). |
| Research | Event-study backtest, pre-registered feature test, volatility forecast check. One registry for specs, trials and out-of-sample windows. Spec hashes pinned in tests. Result: no tested version beat chance on unseen data. |
| Scheduling | `scripts/run_daily.bat` (retry after exit code 2, `run.log` rotation) and `scripts/install_task.ps1`. Untested on Windows. |
| Tests and CI | Last full run (2026-11-05): 907 passed, 3 skipped. 12 pixel-diff baselines in `tests/visual/baseline` (made on Linux). GitHub Actions workflow written; no run is recorded in the repo. |
| Agents | 13 agents in `.claude/agents/`, one owner per file (`docs/agents/ownership.csv`, enforced by a test), 3 of them read-only reviewers (stats, wording, UI). One decision per file in `docs/decisions/`. |

## Decisions made (all by Iiro)
D1 net margin above 0 must pass. D2 neutral label, sort by size of drop. D3 raw pulls: keep 60 days, then weekly, archive and
never delete. D4 flagged tickers are only listed; nothing removed without a yes. D5 Rule 4 (working in parallel) added to
CLAUDE.md. 2026-11-05: the backtest does not get the sector input (disclosed in its report instead); the digest and page
wording above. Details: `docs/decisions.md` and `docs/plans/decisions.md`.

## Not verified (needs Iiro's PC or the network)
- A live Yahoo or OpenBB run of the current code with 348 tickers, and its run time (the 2026-11-02 live run covered 60).
- `run_daily.bat` and the scheduled task on Windows.
- GitHub Actions (first run may fail the visual job until baselines are regenerated on the runner).
- 59 US tickers added earlier are unchecked. Run `python scripts/verify_universe.py --limit 10`, then the full run.
- `python -m dipdash.registry backfill --root output/backtests`.
- The page with real data: the "distorted" and "no fundamentals" states have only been seen through forced test rows.

## What Iiro does next on his PC
1. Run the one-line PowerShell check from the DATA-10 note and re-register the task (`scripts\install_task.ps1`).
2. `python scripts/verify_universe.py --limit 10`, then the full run. Send back anything flagged.
3. After a first green CI run, make the "unit" and "browser" checks required in GitHub branch protection.
4. Decide whether `CLAUDE.md` line 1 ("quality-dip dashboard") and line 45 ("quality score") should be renamed.

## Known gaps and cleanup
- Waves 1 and 2 are done in `docs/BACKLOG.md` (updated 2026-11-05). Open there: RES-11 claims/digest/alerts parts, FU-1 to FU-6.
- D3 (raw-data retention) and D4 (universe check) were answered A on 2026-11-04. DATA-9 and RES-10 are unblocked but not started.
- Stale samples: `snapshots/2026-11-04/latest/digest.md` and `docs/sample-output/daily_review_example_2026-11-02.md`
  still use the old wording; the mid-session digest sample carries a dated note.
- Phone Filters summary says lowercase "quality ≥ N" (FU-2).
- Backtest quality score ignores sector-specific checks (disclosed in its report).

## Possible next steps, in order of value
**A. Make the first live run work (blocks everything else).** Run on the PC, fix what the real feeds break (symbols,
stale bars, rate limits), then DATA-3/DATA-6 (batched pulls, retries, atomic fundamentals cache) and DATA-4/5/8 (guards for
a missing FX rate or a whole exchange, coverage table per exchange).

**B. Page.**
- Table above the fold and a lighter file: the page is about 4 MB (77% is chart history) and builds a hidden desktop table
  on phone. FE-1, FE-2, FE-14.
- Collapse the definitions footer behind a "Definitions" toggle with anchors. It is about a third of the phone page today.
- Replace jargon: "5d resid." should read "5d move vs index (residual)" with a plain line; define "beta" once.
- Filters kept in the URL, print stylesheet, light/dark toggle, keyboard access to charts (FE-5/6/8).
- Split `template.html` into `src/web/` parts that still build one file (FE-11/12) before adding more features.

**C. Research honesty.**
- `docs/claims.md`, a written claims contract, and a generated "What testing found" box (RES-11).
- A forward ledger: every night record what was flagged, score it at 5/21/63 days. This is the only true holdout
  without survivorship bias, and it needs years to have power (RES-5).
- Survivorship stress bound with a delisted-names file (RES-10), and the raw-data retention script (DATA-9, dry run first). Pass the sector to the backtest only if wanted.
- Beta standard error and "not market-adjusted" labels (RES-9).

**D. Possible additions (not planned yet, each needs a decision from Iiro).**
- A "what changed since yesterday" view beyond the "new" tile (entered, left, got worse).
- Earnings dates for European names and a valuation-context column once fundamentals are cached.
- Personal watchlist and notes kept in the browser only.
- Phone or e-mail delivery of the digest.
- Sector-relative quality (compare each company with its own sector instead of fixed thresholds).

## Working rules in one place
Plan first, then work. Edit only files you own. Never run two tasks on `src/template.html`, `src/dipdash/dashboard.py`
or `src/dipdash/cli.py` at once. Every change goes to a reviewer that did not write it. Backtests need event count,
costs, a baseline, an out-of-sample period and confidence intervals. Render the page and look at it (desktop and phone,
light and dark) before calling it done. Run the full suite before handing back, and end with the handoff (Done, Checked,
Not checked, Requests, Decision-log line).
