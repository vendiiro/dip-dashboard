# Iiro's choices D1-D5 and the wave-2 answers

- Date: 2026-11-04
- Topic: ops
- Origin: handed over by the orchestrator 2026-11-04 (D1-D5, wave-2 answers); chosen by Iiro 2026-11-04. These are choices: not every item is built yet (for example D3, `scripts/raw_retention.py`, did not exist on 2026-11-04)

---

- 2026-11-04 (D1-D5, wave-2 answers): Iiro's decisions D1 B, D2 B, D3 A, D4 A, D5 A (docs/plans/decisions.md) and the wave-2 answers (docs/plans/wave-2/answers.md).

What each choice means (copied from the two files; they stay the source):
- D1 B: net margin > 0 must always pass, so a loss-making company is never labelled a quality dip. A definition, not a tested filter.
- D2 B: neutral label "Dip · passes 5 of 6 checks"; default sort by size of the drop.
- D3 A: keep every raw pull for 60 days, then the first pull of each week; move the rest into monthly archive files, never delete. The script runs as a dry run first.
- D4 A: flagged tickers are listed; nothing is removed until Iiro says yes per ticker.
- D5 A: Rule 4 "working in parallel" added to CLAUDE.md as written.

Wave-2 answers, as recorded in docs/plans/wave-2/answers.md:
- RES-2 distorted fundamentals are labelled "Dip, no fundamentals"; the stored score stays as computed (backtest untouched). A missing net margin is not a failure but is listed as missing.
- RES-4 reusing an out-of-sample period is recorded and printed as a note; the run is not blocked.
- FE-3 the page warns when the newest prices are more than 2 weekdays old.
- FE-7 on phones, show the first 10 cards and a "Show all N" button.
- OPS-10 one file per decision in `docs/decisions/`; `docs/decisions.md` becomes a generated topic index.
- DATA-10 one retry 20 minutes after exit code 2, then exit 2; keep `run.log` plus one `.1`; task time limit 1 h to 2 h.
- DATA-1 data sources are injected as one typed `Sources` bundle.
