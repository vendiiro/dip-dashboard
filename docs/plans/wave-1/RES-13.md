# RES-13 (part) + RES-12c · one setup-label function; dd52 known-answer test

**Owner:** screen-logic · **Reviewer:** stats-reviewer · **Skills:** `backtest-hygiene`, `engineering:testing-strategy` · **Size:** S (about 15 lines in screen.py, 2 docstring lines, 60 lines of tests)
**Planned 2026-11-04 (plan only; nothing changed yet).**

## Understanding
`classify` (screen.py:43-51) and `classify_prev` (:69-80) each write out the same five-label precedence. Make both call one
function and prove with an exhaustive test that nothing changes. For RES-12c: `metrics.dd52` (metrics.py:49) uses whatever
history exists down to 60 bars, while `backtest.signals` (backtest.py:41, 47) needs a full 252. Pin this with a known-answer
test and decide whether to align or document. No threshold changes.

## Steps
1. screen.py: add `setup_label(dip, knife, q, settings) -> str` (the body of lines 45-51). `classify` and `classify_prev` call it;
   public names and signatures stay, so dashboard.py:112 and digest.py:130 are untouched.
2. tests/test_screen.py: the truth-table and equivalence tests below.
3. tests/test_metrics.py: the dd52 known-answer tests below.
4. RES-12c: **document, don't align** (docstring at metrics.py:49 and in `compute_metrics`; no behaviour change).

## Truth table (Python `setup_label` = JS `setupOf`, template.html:449-457)
| dip | knife | q | label | JS rank |
|---|---|---|---|---|
| no | any | any | No dip | 0 |
| yes | yes | any (also None, 100) | Falling knife | 1 |
| yes | no | None | Dip, no fundamentals | 2 |
| yes | no | ≥ min_score (60) | Quality dip | 4 |
| yes | no | < min_score (also 0) | Dip, low quality | 2 |

JS parity holds only with the window control on "Default rules" and the quality slider at 60 (JS treats `undefined` like None).

## Tests to add
- `test_setup_label_truth_table`: dip × knife × q ∈ {None, 0, 59, 60, 100}, all 20 cases (q = 0 guards against an `if not q` bug).
- `test_classify_and_classify_prev_agree` on the same grid; `classify_prev(None)` and `({})` give None; a custom min_score is respected.
- `test_dd52_uses_all_history_when_shorter_than_a_year`: n ∈ {60, 61, 150, 199, 200, 220, 221, 251, 252} on a steady −1%/day
  series: dd52 = 0.99^(n−1) − 1; vs200 None below 200 bars; 200-day average "falling" only from 221 bars; at 253 bars the window caps at 252.

## Why document instead of align
- Making the screener return no dd52 below 252 bars would silence the falling-knife warning for recent listings and spin-offs
  (221-251 bars), the less cautious mistake for a warning. For a stock listed under a year ago, "the high since listing" is meaningful.
- Making the backtest accept partial years changes its event set (backtest-analyst's file, a rule change needing review) with no
  benefit to the screen. Instead, state plainly that the backtest says nothing about stocks with fewer than 252 bars.

## Does anything flagged change?
No. In the 4 Nov snapshot, 0 of 288 rows have fewer than 252 bars (31 dips, 16 knives); every demo stock has 460 bars. After the
edit, compare `(ticker, setup, dip, knife)` on the demo payload before and after, and re-classify the snapshot rows from their stored values.

## Verification
`pytest -q tests/test_screen.py tests/test_metrics.py tests/test_backtest.py tests/test_dashboard.py tests/test_digest.py`
(baseline for screen + metrics + backtest: 95 passed), then the full suite.

## Stats-reviewer checks
Identical labels on all 20 cases; that "document" is right (a shorter history can only make the drawdown shallower or equal, so
fewer knife flags, never more); the backtest-coverage caveat wording.

## Requests to other owners
- ui-builder: a browser parity test of `setupOf` over the 20 cases.
- backtest-analyst: assert `signals(...).valid` is False below 252 bars, and the report says stocks under one year are outside the sample.
- docs-steward: one line in the data dictionary on dd52 with short history.

## Open question
Should the payload carry the bar count, so the page can say "52-week high uses N bars"? (integrator's call)

**Decision-log line (proposed):** 2026-11-04: the screener's dd52 keeps using available history (60-251 bars) while the backtest
needs 252; documented, not aligned, because the backtest does not cover stocks under one year old and hiding their falling-knife
warning would be less cautious.
