# Wave 2: Iiro's answers (2026-11-04)

Chosen by Iiro (all the recommended option):
- **RES-2** distorted fundamentals are labelled "Dip, no fundamentals"; the stored score stays as computed (backtest untouched). A missing net margin is not a failure but is listed as missing.
- **RES-4** reusing an out-of-sample period is recorded and printed as a note; the run is not blocked.
- **FE-3** the page warns when the newest prices are more than 2 weekdays old.
- **FE-7** on phones, show the first 10 cards and a "Show all N" button.
- **OPS-10** one file per decision in `docs/decisions/`; `docs/decisions.md` becomes a generated topic index.
- **DATA-10** one retry 20 minutes after exit code 2, then exit 2; keep `run.log` plus one `.1`; task time limit 1 h to 2 h.
- **DATA-1** data sources are injected as one typed `Sources` bundle.

Not asked (each plan's recommended default applies; change any of them by saying so): FE-13 shot count, fonts, diff tolerance; OPS-6/7
hook runner, scan scope, Makefile kept as a wrapper; RES-4 trial-log layout and token enforcement; RES-2 negative-equity signal (use ROE and
D/E both missing now, add totalDebt later); FE-7 error-catch scope and the r.setup rename.
