# OPS-4 + OPS-3 · pinned test dependencies and a CI workflow

**Owner:** test-engineer · **Reviewer:** stats-reviewer is not needed; docs-steward updates the install lines · **Skills:** `engineering:testing-strategy`, `engineering:deploy-checklist` · **Size:** M (about 3-4 h, mostly the first CI run)
**Planned 2026-11-04 (plan only; nothing changed yet).**

## Understanding
`requirements.txt` stays the runtime file for Iiro's PC (keeps `openbb==5.0.0`). A new `requirements-dev.txt` holds exact pins for
tests and CI (no openbb) and adds the missing `statsmodels`. A GitHub Actions workflow runs offline: a unit job on Python 3.11 and
3.13, and a browser job with Chromium.

## Findings (fresh venvs, `git archive HEAD` copy, 2026-11-04)
- With the pins below the unit suite gives 392 passed on Python 3.11 and 3.13 (about 117 s each), and still 392 with the network
  pointed at a dead port, so it runs offline.
- numpy 2.5 and scipy 1.18 need Python 3.12+, so the pins use the newest versions that support 3.11.
- Browser tests before FE-10: 3 failed, 15 passed (the stale tests FE-10 fixes).
- Chrome still tried fonts.googleapis.com 4 times despite the route stub; no test failed. Possibly a preconnect link (unconfirmed).

## Steps
1. Write `requirements-dev.txt` (below); runtime `requirements.txt`: add `statsmodels>=0.14`, yfinance `>=1.7.0,<2`, move pytest and playwright out.
2. `tests/conftest.py`: when `DIP_REQUIRE_BROWSER=1`, a skip in tests/test_browser.py becomes a failure (otherwise a runner without Chromium shows green).
3. `.github/workflows/ci.yml` (below). Pin `ubuntu-24.04`.
4. Check locally on 3.11 and 3.13, offline, then the browser tests; `tests/test_ownership.py` on the real tree.
5. Push the branch and read the run with `gh run watch`. Done = both jobs green.

## requirements-dev.txt (draft)
```
pandas==3.0.5
numpy==2.4.6
yfinance==1.7.0
scipy==1.17.1
statsmodels==0.15.0
arch==8.0.0
matplotlib==3.11.2
pytest==9.1.1
playwright==1.63.0
```

## ci.yml (draft)
```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
env:
  PYTHONIOENCODING: utf-8
  PYTHONPATH: src            # for python -m dipdash and scripts/ outside pytest
  DIP_REQUIRE_BROWSER: "1"   # conftest hook: a skipped browser test fails the run
jobs:
  unit:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    strategy:
      fail-fast: false
      matrix:
        python: ["3.11", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - run: python -m pytest -q --ignore=tests/test_browser.py
  browser:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - run: python -m playwright install --with-deps chromium
      - run: python -m pytest -q -rs tests/test_browser.py
      - name: Screenshots of the demo page
        if: always()
        run: |
          python -m dipdash --demo --out output/demo.html
          python scripts/screenshots.py output/demo.html --out output/screens
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: screenshots
          path: output/screens/
          retention-days: 14
          if-no-files-found: warn
```

## Order with other wave-1 items
FE-10 is now merged, so the browser job should be green. OPS-2 makes the suite skip cleanly without extras; then a third job
"unit-minimal" (pandas, numpy, pytest, yfinance only) can be added. Make CI a required check only after the first green run.

## Risks
About 5 min wall clock per run. Chromium install uses apt and can break on a new runner image (hence the pin). Yahoo changes can
force yfinance upgrades. Not checked: whether `openbb==5.0.0` resolves with pandas 3 and numpy 2.4 on Iiro's PC (live install needed).
Action versions (`setup-python@v5`, `upload-artifact@v4`) should be checked before merging.

## Requests to other owners
docs-steward: install lines in TESTING.md and docs/CLOUD.md use `requirements-dev.txt` for tests; replace "about 270/390 tests" with the real counts.
backtest-analyst (OPS-2): statsmodels is dev-only after Holm moves to numpy; arch installed in one CI job.

## Open questions for Iiro
1. Runtime yfinance `==1.7.0` or `>=1.7.0,<2`? 2. Make "unit" and "browser" required checks (GitHub settings, Iiro only)?

**Decision-log line (if adopted):** 2026-11-04: tests and CI use the exact pins in requirements-dev.txt (no openbb; numpy 2.4.6 and scipy
1.17.1 so Python 3.11 works); the live run keeps requirements.txt with openbb==5.0.0.
