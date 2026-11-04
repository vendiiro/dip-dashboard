# OPS-2 + RES-7 · clean test runs without extras; no hand-typed report numbers

**Owner:** backtest-analyst · **Reviewer:** stats-reviewer (wording-guard glances at new fallback sentences) · **Skills:** `backtest-hygiene`, `engineering:testing-strategy` · **Size:** OPS-2 S (about 1 h); RES-7 S-M (about 3 h, mostly tests)
**Planned 2026-11-04 (plan only; nothing changed yet).** Baseline: `pytest tests/test_feature_experiment.py tests/test_forecast.py tests/test_backtest*.py -q` → 5 failed, 64 passed.

## Understanding
- **OPS-2:** `feature_experiment.holm` imports `statsmodels` (not installed, not listed): 4 failures. `arch` is optional and
  missing, so a forecast test gets the EWMA fallback instead of GARCH: 1 failure.
- **RES-7:** `backtest_report.render_report` hard-codes numbers and review text from one run (spec 79288caaa97d33b1), although its
  docstring says nothing is typed by hand.

## Recommendation: replace statsmodels with about 8 lines of numpy Holm
Holm is a fixed textbook formula (sort p-values, adjusted = running max of min(1, (m − i + 1)·p), map back, reject where ≤ alpha).
It is the only statsmodels use in the repo; a 30 MB dependency is not worth it. Correctness: hand-computed known answers plus a
parity test against statsmodels that is skipped when statsmodels is absent. statsmodels then goes in `requirements-dev.txt` only.

## Steps
1. `feature_experiment.py:100-104`: numpy Holm, same signature.
2. `tests/test_feature_experiment.py`: `test_holm_known_answers` (ties, m = 1, all p = 1, unsorted input, reject flags) and
   `test_holm_matches_statsmodels` (importorskip). The 4 failing tests then pass with no skip.
3. `tests/test_forecast.py`: split the method check (accepts GARCH or EWMA; a separate GARCH test is importorskip("arch")); add
   `test_missing_arch_falls_back_to_ewma`; mark the GARCH loops that silently test the fallback when arch is missing.
4. `backtest.py:228-258`: the placebo also returns how many distinct date-shift lags it used (`shift_lags`); carried into results.csv, not the spec hash.
5. New `src/dipdash/backtest_notes.py`: per-spec-hash notes (revisions, independent review, data notes). `REVISIONS` moves there;
   still excluded from the hash. An unknown hash prints "No review is recorded for spec X" and never inherits old text.
6. `backtest_run.py:150`: compute the history of the primary cell across runs from trials.csv.
7. `backtest_report.py`: every hard-coded figure derived instead:
   "about 660 distinct lags" → `shift_lags`; "+0.2660%, n = 1,504" → primary result, with "identical in every run" only if true;
   KNEBV / NOVO-B review text → notes; "59 of 60 stocks: ROG.SW" → from `n_series`, universe size and `missing_tickers`;
   "21 days", "90%", "3 × 3 × 3", "4 periods", "back to 2010", "21-bar cooldown" → from the spec and settings.
8. `tests/test_backtest_run.py` on a synthetic universe: none of the old literals appear; the synthetic numbers do; any note that
   quotes the primary value matches it; unknown hash prints the "no review" line; editing a note does not change the spec hash.

## Verification
The research tests without statsmodels and arch (0 failed, only importorskip skips), then in a scratch venv with both installed;
the full suite; `grep -nE "0\.2660|1,504|660 distinct|ROG\.SW|KNEBV|NOVO-B" src/dipdash/backtest_report.py` → nothing.

## Stats-reviewer checks
Holm against statsmodels and the textbook (ties, p = 1); every derived report number against results.csv and spec.json; the
caveats still cover survivorship, CI level, event count and costs; moving review text to notes does not hide the "not acted on"
disclosure; `shift_lags` is the right statement of the placebo's resolution.

## Requests to other owners
test-engineer (OPS-4): `statsmodels` in requirements-dev only (for the parity test); install `arch` in one CI job so the GARCH path runs.

## Risks
The published sample report changes wording only after a live re-run (needs the raw pull on Iiro's PC). Moving `REVISIONS` wrongly
could change the hash (guarded by a test).

## Open questions for Iiro
1. Holm in numpy (suggested) or keep statsmodels? 2. Notes as a Python dict (suggested) or one TOML file per spec?
3. Later: compute the KNEBV sensitivity as a results column instead of storing it as a note (that is a new trial)?

**Decision-log line (if adopted):** 2026-11-04: Holm adjustment is implemented in numpy in feature_experiment.py; statsmodels is a
dev-only dependency for a parity test.
