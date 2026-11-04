# RES-1 · the digest keeps its backtest caveat

**Owner:** integrator · **Reviewers:** wording-guard (caveat text), stats-reviewer (does not overstate) · **Skills:** `engineering:testing-strategy`, `design:ux-copy` · **Size:** S
**Planned 2026-11-04 (plan only; nothing changed yet).** Baseline: `pytest -q tests/test_digest.py tests/test_dashboard.py` → 66 passed.

## Understanding
`latest_backtest_line` (digest.py:37-51) sorts `backtests/*/results.csv` by path, so `2026-11-04_forecast` wins. Forecast folders
have no `spec.json`, feature folders write `spec_features.json`, and only event backtests write `spec.json` (backtest_run.py:128).
So the 4 Nov digest printed "could not be read" and lost its standing "no out-of-sample edge" line.

## Steps
1. digest.py: `_is_event_backtest(folder)`: `spec.json` exists, parses, and has `primary_cell` and `variants`. Only those folders
   qualify, newest by name; `_forecast` and `_features` folders are ignored even with a `results.csv`.
2. digest.py: a constant `STANDING_CAVEAT`, printed every time, whether or not a backtest line exists. Draft for wording-guard:
   "So far no tested version of this screen has shown an out-of-sample edge that the sample can separate from noise (see
   docs/decisions.md). A flag is not a sign of a later rebound; treat the list as a place to start reading."
3. tests/test_digest.py: existing tests (~172-187) also write a minimal `spec.json`; new
   `test_backtest_line_ignores_forecast_and_feature_siblings` (folders `X`, `X_features`, `X_forecast` → names `X`),
   `test_backtest_line_skips_folder_with_unrelated_spec_json`, `test_standing_caveat_always_present` (no backtests, unreadable, valid).

## Verification
`pytest -q tests/test_digest.py tests/test_ownership.py`; `python -m dipdash --demo --out <tmp>/dashboard.html`, then the caveat is in digest.md.

## Reviewer checks
wording-guard: neutral, plain, no "rebound expected", true even when the backtest line is missing.
stats-reviewer: matches docs/decisions.md (the dip-rule and feature results); picking by spec cannot quote a feature or non-primary result.

## Risks
Structure-based detection breaks if `primary_cell` is renamed (a `kind` field would be sturdier; see request). A fixed "no edge"
sentence goes stale if a later primary interval excludes zero.

## Requests to other owners
backtest-analyst (optional): add `"kind": "event_backtest"` to spec.json, `"kind": "features"` to spec_features.json, and a spec file for forecast runs.

## Open questions for Iiro
1. Fixed caveat forever, or switch off automatically if a future primary out-of-sample interval excludes zero?
2. Should spec files carry an explicit `kind` (sturdier than detecting by structure)?

**Decision-log line (if adopted):** 2026-11-04: the digest quotes only folders whose spec.json describes an event backtest, and always
prints a fixed out-of-sample caveat.
