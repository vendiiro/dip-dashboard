# OPS-5 (= FE-9, part 1) · the payload as a documented, tested contract

**Owner:** integrator · **Reviewer:** ui-reviewer (reads it as the page's consumer) · **Skills:** `engineering:architecture`, `engineering:testing-strategy`, `openbb-data-pull` · **Size:** S-M (with RES-1, about 250 lines of doc and tests)
**Planned 2026-11-04 (plan only; nothing changed yet).**

## Understanding
Write `docs/payload.md` (every field: type, unit, can it be null, meaning) and `tests/test_payload_contract.py`, pinned to the real
CLI payload including `alerts`, so the page and the Python side can change independently and a rename is caught.

## What the doc will say (fields found by running the demo through the CLI)
- **Units:** moves are fractions (−0.04 means −4%), not percent. `price` is the adjusted close in local currency `ccy`.
- **alerts:** added in cli.py:199 after `build_payload`. Absent = no alert step ran; `null` = the step failed; `[]` = a quiet day
  (matches template.html:486-490).
- **Top level:** generated, tz, demo, rows, data_quality, fx_to_usd (USD per unit), indices, issues, settings (dip, quality, knife), alerts.
- **Row:** moves r1, r5, r21, dd20, dd52, vs200, x5, res1, res5; price, rsi (0-100), z5, volx, res5z, beta, beta_raw; flags
  s200_falling, knife, partial, dip; series spark (last 90 closes) and hist {d, c, s, h}; prev; asof, idx, idx_sym, idx_why,
  beta_side, res_why; earn; t, name, region, sector; q and qchecks; fpe, tpe, ccy; news; why; setup (one of five labels).
- In the demo the residual, beta, earnings and index-reason fields are always null; their types come from the code.

## Tests (tests/test_payload_contract.py)
- Top-level keys and types from a CLI demo run (payload captured, `alerts` a list).
- Every row has exactly the documented keys with documented types or allowed nulls; nested shapes match.
- The doc tables and the test's spec agree (parsed from docs/payload.md).
- The template reads only documented fields (`DATA.x`, `r.x` minus a small allowlist, `.earn.x`, `.prev.x`).
- A planted rename (`r1` → `ret1`) in a copy of the payload and of the template makes the checks fail.
- Alerts semantics: no key without the alert step; `null` when the alert step is forced to fail.

## Verification
`pytest -q tests/test_payload_contract.py tests/test_dashboard.py tests/test_ownership.py`; the planted-rename check by hand once.

## Risks
The `r.x` regex can give false positives as the template grows (allowlist upkeep). The CLI demo run in tests takes 1-3 s and writes
alert state inside tmp_path only.

## After this lands
FE-14 (smaller payload) and RES-9 (beta labels) change the payload through this contract; ui-builder lists its DOM hooks in
`docs/frontend-contract.md` (FE-13).
