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

## Known data limits

Three limits seen in the source cross-check (`docs/m2-data-verification.md`, produced by `scripts/verify_sources.py`) and in Iiro's first live run (2026-11-05). This is the one place they are written down.

1. **Fundamentals differ between free sources and are approximate.** The quality score uses the Yahoo numbers. In the cross-check, Yahoo (trailing twelve months) and Nasdaq (last full year) gave, for example: JNJ net margin 28.5% (Nasdaq) vs 16.2% (Yahoo); ERIC-B.ST return on equity 27.9% vs 18.1%. The two sources cover different periods, so only large gaps like these mean anything, but they show a quality check can pass on one source and fail on the other. Fundamentals are also not point-in-time, so they are used for current screening only, never as historical features in a backtest.
2. **A one-day difference against the Cboe copy of US closes is expected.** Its last bar is one trading day older than Yahoo's (for example 2026-10-29 vs 2026-10-30), so it has one fewer day to compare. It is not a data error.
3. **Continental European prices have no independent second source.** The price cross-check covers US names (Nasdaq and Cboe) and Nordic names (Nasdaq Nordic) only. For ASML.AS, SAP.DE, NESN.SW, MC.PA, AIR.PA, ROG.SW and RO.SW only the internal checks run (stale bars, gaps, large moves). The cross-check also compares unadjusted closes, so dividend adjustment is not verified for any name.

State of the findings so far (details in the snapshot README): the dip rule shows no out-of-sample edge that the sample can separate from noise,
no tested price feature shows detectable signal, and a forecast of how far prices usually move in a day did not match what actually happened in testing, so it is not used.
The dashboard is a listing and monitoring tool.
