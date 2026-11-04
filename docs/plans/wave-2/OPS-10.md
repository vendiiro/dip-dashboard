# OPS-10 · decision log that parallel appends cannot conflict on (+ OPS-8 done, + wave-1 line backlog)

**Owner:** docs-steward · **Reviewer:** wording-guard (wording), test-engineer (the "exactly once" test) · **Skills:** `engineering:documentation` · **Size:** M (docs only, one small test)
**Planned 2026-11-04 (plan only; nothing changed yet).**

## Understanding
`docs/decisions.md` is one 203-line file where every agent's line goes at the end, so two parallel appends touch the same lines and conflict.
Make new entries land in separate places, add a topic index so a reader finds a decision in one look, and append the wave-1 lines that
were handed back but never written down.

## OPS-8: DONE
Rule 4 "working in parallel" is in `CLAUDE.md:36` (Iiro chose D5 A on 2026-11-04). Mark OPS-8 done in `docs/BACKLOG.md` (orchestrator edits it).

## Facts checked
- `docs/decisions.md`: 203 lines, 54 top-level entries starting `- 20..` (checked with `grep -c "^- 20"`), plus 6 undated bullets under the last heading (lines 197-203).
- `docs/agents/ownership.csv:97-98` already gives docs-steward both `docs/decisions.md` and `docs/decisions/*`, so no ownership change.
- Source files cite `docs/decisions.md` by name (`digest.py:38`, `forecast.py:5`, `residual.py:4`, `alerts.py:6`): that path must keep existing.
- Existing entries use only M1-M5 and dated headings; no topic labels. Topics to use: data, screen, backtest, dashboard, alerts, ops, docs.

## Plan (recommended option A below)
1. Create `docs/decisions/YYYY-MM-DD-<topic>-<slug>.md`, one per existing dated entry (54) plus one per review-follow-up bullet group (6 → 3 files by topic). Body copied verbatim, no rewording.
2. Rewrite `docs/decisions.md` as an index only: one table per topic (date, one-line title, link), newest last. Keep the title line and a "how to add a decision" paragraph (new file, never edit the index by hand).
3. `scripts/build_decision_index.py` (stdlib only) regenerates the index from the file names and first lines. Agents add a file; docs-steward runs the script once per merge.
4. `tests/test_decisions_index.py`: every file in `docs/decisions/` appears once in the index; the count of migrated entries equals 54 + 6 bullets; a checksum of the concatenated old text equals the new files' text (so "every old entry present exactly once").
5. Update the one line in `.claude/agents/docs-steward.md` ("append ... newest last") and `docs/AGENTS.md:50-57` to say "new file in `docs/decisions/`"; both are other owners' files, see Requests.

## Backlog of lines still to append (as separate files, dated 2026-11-04, verbatim)
Found in the repo (wave-1 plans; each says "if adopted", so confirm it was adopted before appending):
- FE-10: browser tests read stable `data-testid` / `data-k` hooks and derive expected counts from `DATA`, not fixed demo numbers.
- OPS-2: Holm adjustment is implemented in numpy in `feature_experiment.py`; statsmodels is a dev-only dependency for a parity test. (Holm in numpy is in the code; check the statsmodels half.)
- OPS-4: tests and CI use the exact pins in `requirements-dev.txt` (no openbb; numpy 2.4.6 and scipy 1.17.1 so Python 3.11 works); the live run keeps `requirements.txt` with openbb==5.0.0. (`requirements-dev.txt` exists.)
- OPS-9: `docs/sample-output/dashboard-demo.html` is the canonical demo page; `docs/demo/dashboard-demo.html` stays as the M0 design mock.
- RES-1: the digest quotes only folders whose spec.json describes an event backtest, and always prints a fixed out-of-sample caveat.
- RES-13: the screener's dd52 keeps using available history (60-251 bars) while the backtest needs 252; documented, not aligned (a younger stock keeps its falling-knife warning).
- DATA-2, DATA-7, OPS-5 plans carry no decision-log line; the orchestrator confirms "none".
NOT in the repo: the lines in the wave-1 agents' actual handoffs and in the wave-1 review fixes. I cannot see them, and I will not reconstruct them.
The orchestrator pastes them verbatim into the docs-steward task; each becomes its own file, in handoff order.

## Verification
1. `ls docs/decisions | wc -l` equals the expected count; `pytest -q tests/test_decisions_index.py tests/test_ownership.py`.
2. `grep -rn "docs/decisions.md" src scripts tests` paths still resolve; then the full `pytest -q`.
3. wording-guard scan of the new files for banned advice words (text is copied, so expect no new hits).

## Risks
Migration touches every old entry: a copy error changes history (the checksum test covers it). A script-built index can drift if someone edits it by hand (the test fails).

## Open questions for Iiro
1. Structure. **A (recommended):** one file per decision plus a generated topic index. B: keep one file, add a topic index at the top and per-topic sections (still conflicts when two agents add under the same topic). C: keep as is and mark `docs/decisions.md merge=union` in `.gitattributes` (cheapest, but the repo is not under git here and order is not guaranteed).
2. Old entries. **A (recommended):** split all 54 by script with the checksum test. B: leave the old file as `docs/decisions-archive.md`, new files from today only (less risk, two places to look).
3. Backlog lines. **A (recommended):** append only lines confirmed adopted, mark the rest "proposed, not adopted". B: append all as written.

## Requests to other owners
- orchestrator: mark OPS-8 done in `docs/BACKLOG.md`; paste the missing wave-1 handoff and review-fix lines; confirm which "if adopted" lines were adopted.
- orchestrator (owner of `.claude/agents/docs-steward.md` and `docs/AGENTS.md`): change "append ... newest last" to "add a file in `docs/decisions/`".
- test-engineer: review `tests/test_decisions_index.py` (docs-steward does not own `tests/`; confirm who writes it, or add it to the ownership CSV).

## Handoff
1. **Done:** `docs/plans/wave-2/OPS-10.md` (this plan only).
2. **Checked:** `grep -c "^- 20" docs/decisions.md` → 54; `grep -n "Rule 4" CLAUDE.md` → line 36; ownership.csv lines 97-98.
3. **Not checked:** actual wave-1 handoff and review-fix lines (not in the repo); whether FE-10, OPS-2 (statsmodels part), RES-1, RES-13 were adopted.
4. **Requests to other owners:** see above.
5. **Decision-log line:** 2026-11-04: each decision is its own file in `docs/decisions/`; `docs/decisions.md` is a generated topic index (if Iiro picks option A).
