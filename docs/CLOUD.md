# Working on this project in a cloud environment or with several agents

## Setup (Linux or macOS container)
```bash
uv venv && source .venv/bin/activate          # Python 3.11+
uv pip install -r requirements.txt            # openbb is large and optional for tests; yfinance is the working data source
export PYTHONPATH=src
pytest -q                                      # about 390 tests; tests/test_browser.py skips without Playwright
python -m dipdash --demo --out /tmp/demo.html  # synthetic data, no network
```
Live data (Yahoo through yfinance) needs outbound network access. Check the environment's network policy first; if Yahoo is blocked, use `--demo` and the files in `snapshots/`.
Browser checks: Chromium is usually pre-installed in cloud sandboxes (set `DIP_CHROMIUM` to its path for `scripts/screenshots.py`).

## What is Windows-only
`scripts/run_daily.bat`, `scripts/install_task.ps1` (Task Scheduler) and `scripts/notify.ps1` (desktop notification). The Python package itself is portable.
Do NOT set `PYTHONUTF8=1` on a machine whose user folder contains non-ASCII characters (curl then cannot read its certificate file): use `PYTHONIOENCODING=utf-8`.

## Rules that matter when several agents work at once
- One agent per file group; the files most often touched together are `src/template.html`, `src/dipdash/dashboard.py` and `src/dipdash/cli.py`. Agree who owns them.
- Never commit `.env`, `data/` or `output/` (they are git-ignored). Dated results worth keeping go under `snapshots/<date>/`.
- Every backtest or "this rule works" claim follows the skill in `.claude/skills/backtest-hygiene/` and is logged in `output/backtests/trials*.csv` (copy the log into a snapshot).
- A change to the dashboard is not done until it has been rendered (desktop 1280 px and phone 390 px, light and dark) and the console is clean.
- Output wording is neutral: no "buy", "sell" or "target"; a test scans the alert text.

## Where things are
`src/dipdash/` package (data, metrics, quality, screen, residual, earnings, alerts, backtest, dashboard, digest, cli) · `src/template.html` dashboard shell ·
`config/` universe, settings, alerts · `tests/` · `docs/decisions.md` dated decision log · `snapshots/` data and EDA.

## Open items (from the 2026-11-04 verification)
Earnings dates missing for 49 stocks (mostly European) · negative fitted betas floored at 0 for 49 stocks (is the S&P 500 the right single factor?) · 22 stocks under the 20B USD market-cap check ·
European bars are intraday when pulled before the close · raw price pulls in `data/raw/` have no retention rule · Playwright not installed in the local venv.
