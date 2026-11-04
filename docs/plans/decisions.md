# Decisions only Iiro can make

Each one blocks a backlog item. Reply with the letter you pick, or your own wording. Nothing here has been changed yet.
Facts quoted come from the 2026-11-04 audits and the 4 Nov snapshot (288 screened stocks then; 348 in the universe now).

## D1 · Which quality checks must always pass (unblocks RES-2)

**Why it matters.** The quality score is "share of the checks that have data and passed". Missing data drops out of the
denominator, so a company with negative equity (Yahoo leaves ROE and debt/equity empty) can score 100 on four checks:
MCD, ABBV, PM and BKNG did on 4 Nov. 263 of 288 stocks cleared the bar of 60, and 26 of 31 dips were labelled "Quality dip".
RES-2 adds "scored on n/6" and a `distorted` flag (ROE above 100%, or signs of negative equity) whatever you choose here.

| Option | Must pass | Effect |
|---|---|---|
| A | nothing (today's behaviour) | only the new n/6 and `distorted` labels |
| **B (suggested)** | net margin > 0 | a loss-making company is never labelled a quality dip (INTC on 4 Nov) |
| C | net margin > 0 and free cash flow > 0 | stricter; more "Dip, low quality" labels |

Whatever you pick is a **definition**, not a tested filter: free fundamentals are not point-in-time, so it cannot be backtested.
The before/after label counts will be reported as description only.

## D2 · A neutral label instead of "Quality dip"; no default sort by score (unblocks RES-11)

**Why it matters.** "Quality dip" and a list sorted best-score-first read like a recommendation, but the backtest found no
out-of-sample edge and the quality score is untested.

| Option | Label | Default sort |
|---|---|---|
| A | keep "Quality dip" | by setup, then score (today) |
| **B (suggested)** | "Dip · passes 5 of 6 checks" | by size of the drop |
| C | "Dip · quality checks passed" | alphabetical |

## D3 · Raw-data retention (unblocks DATA-9)

**Why it matters.** Every night saves two years of bars for every ticker (about 170,000 rows at 348 tickers) and nothing is
ever removed. Deleting is irreversible.

| Option | Policy |
|---|---|
| **A (suggested)** | keep every pull for 60 days, then the first pull of each week; move the rest into monthly archive files, never delete |
| B | keep everything (disk grows by a few hundred MB a year) |
| C | as A, but delete instead of archive |

The script always runs as a dry run first and prints what it would do.

## D4 · Tickers the checker flags (unblocks RES-10 and universe changes)

`scripts/verify_universe.py` (DATA-2) will list tickers with no data, stale data, a different company name, a wrong currency
or a market cap under 20B USD. Names to watch from the audit (unverified hunches): NSC, KDP, SOLB.BR, UNA.AS, DOW, HAL, EL, ADM.

| Option | What happens to a flagged ticker |
|---|---|
| **A (suggested)** | you see the list; nothing is removed until you say yes per ticker |
| B | remove tickers with no data automatically; ask about the rest |
| C | keep everything; flags only show in the data-quality badge |

## D5 · Approve this section for CLAUDE.md (unblocks OPS-8)

Proposed text, about 10 lines, added after Rule 3:

> ## Rule 4: working in parallel
> Several agents may work at once. Read `docs/AGENTS.md` first. Edit only files your agent owns
> (`docs/agents/ownership.csv`); ask the owner for anything else in your handoff. Never run two tasks that touch
> `src/template.html`, `src/dipdash/dashboard.py` or `src/dipdash/cli.py` at the same time. Every change goes to a reviewer
> that did not write it (ui-reviewer, stats-reviewer, wording-guard). End with the handoff in your agent file.
> Run the full test suite before handing back.

Options: **A** approve as written, **B** approve with your edits, **C** keep CLAUDE.md as it is (AGENTS.md still applies).
