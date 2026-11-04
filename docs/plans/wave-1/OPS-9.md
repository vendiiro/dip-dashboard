# OPS-9 + OPS-11 · stale numbers in docs; one canonical demo page

**Owner:** docs-steward · **Reviewer:** wording-guard · **Skills:** `engineering:documentation` · **Size:** S (about 18 edits, 5 files, no code)
**Planned 2026-11-04 (plan only; nothing changed yet).**

## Understanding
Several docs still give numbers from the 60-stock, ~270/390-test era. Replace them with wording that does not go stale (dated
figures only where a number is needed), name `docs/sample-output/dashboard-demo.html` as the canonical demo page, and link
`docs/AGENTS.md` and `docs/BACKLOG.md`.

## Facts checked
- `config/universe.csv`: 348 rows (US 227, Europe 87, Nordic 34). `pytest --collect-only -q`: 410 tests collected.
- ROG.SW is still in the universe. `cli.py:190` prints `FAILED: only {n} of {len(universe)} stocks could be screened`.
- The two demo pages differ: `docs/demo/` is the 49 KB M0 mock; `docs/sample-output/` is 713 KB, built from the template (2026-11-02).

## Changes (file:line, old → new)
- **README.md:12** "about 390 tests …" → "`pytest` runs the full suite offline; the browser tests need Playwright and a Chromium and skip without them. Setup: `TESTING.md`."
- **README.md** after :8: add "**Agents, owners, open work:** `docs/AGENTS.md`, `docs/BACKLOG.md`."; after :11: name the canonical demo page and call `docs/demo/` the frozen M0 mock.
- **docs/CLOUD.md:8** "about 390 tests" → "full suite, offline". **:18-19** add an AGENTS/BACKLOG bullet; "Agree who owns them." → "Owners are fixed in `docs/agents/ownership.csv` (checked by `tests/test_ownership.py`)." **:27** add both docs to "Where things are". **:31** date the "Playwright not installed" note (Iiro's PC, as of 2026-11-04).
- **docs/PLAN.md:3** add "Work after M5 is tracked in `docs/BACKLOG.md`; this file is the original build record." **:7** "~60" → "the blue chips in `config/universe.csv` (about 60 at M0; 348 on 2026-11-04)". **:55** date the `frontend-design` note.
- **TESTING.md:10** "for 60 stocks" → "for every stock in `config/universe.csv`". **:11, :21** mark the canonical demo. **:30** install line → `requirements-dev.txt` if OPS-4 lands first. **:34** "about 270 …" → "the full suite passes (browser tests skip unless Playwright and a Chromium are installed)". **:43** "about 59 of 60 … about a minute" → "nearly every stock; a few have no data at the source (for example ROG.SW) and are listed in `output/data_quality.csv`. Run time for the full universe is not measured yet". **:48** "only N of 60" → "only N of M".
- **docs/sample-output/README.md:3, :5**: say the examples are dated records of the 60-stock universe; name the canonical demo page.
- Left alone on purpose: `docs/decisions.md` (dated history), the dated backtest report and digest examples, START_HERE.md (nothing stale).

## Requests to other owners
- ui-builder: a one-line "M0 design mock" banner in `docs/demo/dashboard-demo.html`; rebuild `docs/sample-output/dashboard-demo.html` after FE-10.
- test-engineer: confirm the final requirements file name (OPS-4) for the TESTING.md install line.
- orchestrator: add `docs/sample-output/README.md` to this task's locks (done in BACKLOG.md).

## Verification
1. `grep -rnE "about (270|390)|of 60\b|60 stocks|~60 " README.md TESTING.md START_HERE.md docs/PLAN.md docs/CLOUD.md` → one hit (PLAN.md:7 "about 60 at M0").
2. `grep -c "AGENTS.md\|BACKLOG.md" README.md docs/CLOUD.md` → at least 2 each.
3. Every `docs/demo/dashboard-demo` mention calls it the M0 mock. Then `pytest -q tests/test_ownership.py`.

## Risks
TESTING.md:30 overlaps OPS-4 (order them). "Run time not measured" removes a claim; the 348-ticker run time needs a live run on Iiro's PC.

## Open question for Iiro
Keep the dated "348 on 2026-11-04" in PLAN.md:7, or only point to the CSV?

**Decision-log line:** 2026-11-04: `docs/sample-output/dashboard-demo.html` is the canonical demo page; `docs/demo/dashboard-demo.html` stays as the M0 design mock.
