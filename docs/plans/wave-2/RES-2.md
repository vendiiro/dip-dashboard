# RES-2 · quality score honesty: "scored on n/6", `distorted`, `must_pass` (+ RES-11 follow-on)

**Owner:** screen-logic · **Reviewers:** stats-reviewer, wording-guard · **Skills:** `backtest-hygiene`, `data:statistical-analysis`, `engineering:testing-strategy` · **Size:** M
**Planned 2026-11-04 (plan only; nothing changed yet).** Iiro: D1 = B (net margin > 0 must pass), D2 = B (label "Dip · passes 5 of 6 checks", sort by size of the drop).

## Understanding
The quality score is "passed / checks that had data", so missing data shrinks the denominator: negative-equity companies (ROE and D/E empty) reached 100 on four checks (MCD, ABBV, PM, BKNG on 4 Nov), and 26 of 31 dips were "Quality dip". RES-2 makes thin or odd evidence visible and enforces D1. Both are **definitions, not tested filters**: free fundamentals are not point-in-time and nothing here is backtested.

## Steps (my files: quality.py, screen.py, settings.toml, tests)
1. quality.py: new `quality_detail(fund, q, fx, sector) -> QualityResult` (frozen dataclass: `score, checks, scored, applicable, passed, status, distorted_why, must_failed, must_missing`). `quality()` stays and returns `(score, checks)` unchanged, so dashboard.py:85 and backtest keep working.
2. Counts: `applicable` = 6 minus not-applicable checks (Financials: 4); `scored` = applicable checks with data; shown as "scored on n/6" (`applicable` kept so a bank reads "4 of 4 applicable").
3. `distorted` (never for a not-applicable check): ROE > `distorted_roe_above` (1.0, i.e. above 100%; exactly 100% is not), or ROE and D/E both missing for a sector where D/E applies (suggests negative equity).
4. `must_pass`: named rules, not the 6 checks (the 6 use margin >= 8%; D1 is margin > 0). Table in quality.py: `net_margin_positive` (profitMargins > 0), `fcf_positive` (freeCashflow > 0, ready for D1 option C, unused). Unknown name raises `ValueError`. Missing or NaN value is not a failure; it is listed in `must_missing`.
5. `status` precedence: `no_data` (score None) > `distorted` > `thin` (scored < applicable) > `ok`.
6. screen.py: `setup_label(dip, knife, q_score, settings, q_ok=True)`; order: not dip, knife, score None, **distorted -> Dip, no fundamentals**, **must_pass failed -> Dip, low quality**, score < min_score -> low quality, else Quality dip. `classify`/`classify_prev` take the same flag (default True keeps all current callers and the 20-case truth table valid).
7. settings.toml `[quality]`: `must_pass = ["net_margin_positive"]`, `distorted_roe_above = 1.0`. The raw score `q` is **not** altered, so the backtest's V3 input is untouched (see Q1).

## Known-answer tests (tests/test_quality.py, test_screen.py)
- All six pass, full data: 100, scored 6, status ok. Existing quality tests pass unchanged (back-compat of `quality()`).
- Negative-equity profile (ROE, D/E missing; margin 0.2, FCF+, growth+, cap big): raw 100 on 4/6, status `distorted`, setup is **not** Quality dip.
- ROE 1.5 -> distorted; ROE 1.0 -> not; Financials with ROE missing -> not distorted, scored of 4 applicable.
- INTC-like (margin -0.05, other five pass): score 80 yet setup Dip, low quality; margin 0.0 fails; margin 0.01 passes must-pass (fails the 8% check only).
- `must_pass = ()` reproduces today's labels; unknown rule name raises; NaN/inf margin = missing, not failed; 3 checks with data = thin, 2 = no_data/None.
- Truth table: the 20 cases times q_ok in {True, False}; q = 0 still a score.

## Label counts on the 4 Nov snapshot (description only)
At build time, recompute from the stored `q`/`qchecks` values with a throwaway script in the scratchpad, and report: dips by label before and after (31 dips; 26 were Quality dip), which tickers move (INTC expected; MCD, ABBV, PM, BKNG only if they were dips), and the same on `--demo`. Worded "this changes how many are labelled, it does not show the new labels are better". No test asserts these counts.

## RES-11 follow-on (after RES-4; needs this plan merged)
- **screen-logic (me):** `setup_text(setup, passed, applicable)` -> "Dip · passes 5 of 6 checks"; enum names stay the stable key. Tests for every label and the Financials case ("passes 3 of 4").
- **integrator:** payload `setup_text`; default order by size of drop; digest/alerts wording ("Quality dip" at digest.py, 3 places); config fields.
- **ui-builder:** template shows `setup_text`, default sort by drop (6 "Quality dip" mentions, `setupOf` parity test), footer definitions for scored n/6, distorted, must-pass.
- wording-guard reviews all text; stats-reviewer checks the "What testing found" box claims.

## Payload fields this adds (integrator: document in docs/payload.md, per row)
`q_scored` int, `q_applicable` int, `q_passed` int, `q_status` ("ok"|"thin"|"distorted"|"no_data"), `q_why` str|null (distorted reason), `q_must_failed` list[str], `q_must_missing` list[str]. Top level `settings.quality` gains `must_pass`, `distorted_roe_above`. Existing `q`, `qchecks`, `setup` keep their meaning (`setup` can now differ for the same `q`). RES-11 later adds `setup_text`.

## Open questions
1. A distorted stock gets which label? (a) **Dip, no fundamentals** (recommended: honest "cannot be verified", no new enum, RES-11 rewords) (b) Dip, low quality (inaccurate) (c) new label (touches template, digest, tests).
   Also: keep `q` as computed (recommended; backtest V3 unchanged; backlog's "cannot reach 100" becomes "cannot be labelled quality") or set `q` to None when distorted (changes V3 input).
2. Negative-equity signal needs "positive debt", but `totalDebt` is not fetched (data.py FUND_KEYS). (a) use ROE and D/E both missing only (recommended now; over-flags data gaps, which is the safe direction) (b) data-engineer adds `totalDebt` and a cache bump first (c) (a) now, (b) later.
3. Margin missing under must_pass: (a) **not a failure, listed in `must_missing`** (recommended; consistent with "no data is not a fail", n/6 shows the gap) (b) treated as failed (stricter, more "low quality") (c) blocks the label only for stocks with q status thin.

## Requests to other owners
- integrator: `QualitySettings` gets `must_pass: tuple[str, ...] = ("net_margin_positive",)` and `distorted_roe_above: float = 1.0` in config.py (defaults equal the toml, tests/test_config.py:22 compares them); dashboard.py:85 calls `quality_detail`, passes `q_ok` to `classify`; payload fields above in docs/payload.md.
- backtest-analyst: confirm `V3_quality_indicative` (backtest.py:147) is unaffected; RES-3 later shares one function.
- ui-builder / docs-steward: footer and data-dictionary text for scored n/6, distorted, must-pass (RES-11).

## Verification
`pytest -q tests/test_quality.py tests/test_screen.py tests/test_config.py tests/test_digest.py tests/test_dashboard.py`, then the full suite; demo payload compared before/after on `(ticker, setup)`.

## Handoff (when built)
1 Done · 2 Checked · 3 Not checked (live fundamentals run on Iiro's PC) · 4 Requests · 5 Decision-log line.
**Decision-log line (proposed):** 2026-11-04: quality labels now require net margin > 0 (D1 B) and exclude distorted fundamentals; the score is shown as "scored on n/6"; these are definitions, not tested filters.
