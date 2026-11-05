# Daily dip screen (long-only research tool, US + Europe)

Screens US and European large caps every night after the close for sharp price drops in otherwise high-quality companies, and writes a dashboard,
a digest and trigger alerts. **Educational research only: it never gives investment advice.** Wording in all output: "screen results", "candidates",
"flagged because ...", "a condition became true".

- **Rules for any contributor or agent:** read `CLAUDE.md` first (plan before code, honest backtests, dashboard checks, wording).
- **Cloud / multi-agent setup:** `docs/CLOUD.md`.
- **Agents, owners, open work:** `docs/AGENTS.md`, `docs/BACKLOG.md`.
- **Plan, decisions, research:** `docs/PLAN.md`, `docs/decisions.md`, `docs/research-report.md`.
- **Latest data snapshot with an executed EDA notebook:** `snapshots/2026-11-04/` (see its `README.md`, `DATA_DICTIONARY.md`).
- **Run (Windows):** `scripts\run_daily.bat` (see `START_HERE.md`). **Demo, no network:** `python -m dipdash --demo` with `PYTHONPATH=src`.
  Canonical demo page (built from the real template, synthetic data): `docs/sample-output/dashboard-demo.html`. `docs/demo/` is the frozen M0 design mock.
- **Tests:** `pytest` runs the full suite offline; the browser tests need Playwright and a Chromium and skip without them. Setup: `TESTING.md`.

State of the findings so far (details in the snapshot README): the dip rule shows no out-of-sample edge that the sample can separate from noise,
no tested price feature shows detectable signal, and a forecast of how far prices usually move in a day did not match what actually happened in testing, so it is not used.
The dashboard is a listing and monitoring tool.
