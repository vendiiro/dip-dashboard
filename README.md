# Daily quality-dip screen (long-only research tool, US + Europe)

Screens US and European large caps every night after the close for sharp price drops in otherwise high-quality companies, and writes a dashboard,
a digest and trigger alerts. **Educational research only: it never gives investment advice.** Wording in all output: "screen results", "candidates",
"flagged because ...", "a condition became true".

- **Rules for any contributor or agent:** read `CLAUDE.md` first (plan before code, honest backtests, dashboard checks, wording).
- **Cloud / multi-agent setup:** `docs/CLOUD.md`.
- **Plan, decisions, research:** `docs/PLAN.md`, `docs/decisions.md`, `docs/research-report.md`.
- **Latest data snapshot with an executed EDA notebook:** `snapshots/2026-11-04/` (see its `README.md`, `DATA_DICTIONARY.md`).
- **Run (Windows):** `scripts\run_daily.bat` (see `START_HERE.md`). **Demo, no network:** `python -m dipdash --demo` with `PYTHONPATH=src`.
- **Tests:** `pytest` (about 390 tests; the browser test needs Playwright and skips without it).

State of the findings so far (details in the snapshot README): the dip rule shows no out-of-sample edge that the sample can separate from noise,
no tested price feature shows detectable signal, and the volatility-range forecast failed its calibration check and is not wired in.
The dashboard is a listing and monitoring tool.

## Focus: themes and company size
The **Focus** panel at the top of the dashboard narrows the whole page (tiles, table and charts) to one or more themes,
such as *AI & cloud*, *Semiconductors* or *Pharma & biotech* (Eli Lilly, Novo Nordisk ...), and optionally to large companies only
(market cap ≥ $100B or ≥ $500B). Each theme card shows how many quality dips it has today and its median 5-day move.
Several themes can be on at once. The choice is remembered in the browser and kept in the link (`#focus=ai,pharma&size=100000000000`),
so a view can be bookmarked.

Themes live in `config/themes.toml`: add, rename or regroup them freely. Every ticker must be in `config/universe.csv`
(a test checks this). Themes are a browsing aid only: they never change whether a stock counts as a dip or how quality is scored.
