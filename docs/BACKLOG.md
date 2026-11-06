# Backlog

Built on 2026-11-04 from four read-only audits (front end, data pipeline, research, tests/docs). Owners and rules are in
`docs/AGENTS.md`. Each wave gives each owner at most one task, and no two tasks in a wave lock the same file. Tasks
marked **pair** cross an ownership line: the first owner builds, the second wires it in, in that order within the wave.

Status values: `todo`, `doing`, `review`, `done`, `blocked: <reason>`. Size: S < half a day, M about a day, L more.
IDs keep the audit prefix: FE front end, DATA data, RES research, OPS tests/docs/ops. Merged duplicates are noted.

![Who works on what, wave by wave](agents/backlog-waves.png)

State when written: `pytest` gives 8 failed, 399 passed. The failures are 3 stale browser tests, 4 tests needing `statsmodels`
(not listed in requirements) and 1 test needing `arch`. Wave 1 brings it to green.

## Wave 1: green suite, two real bugs, first contracts

| ID | Task | Owner | Locks | Size | Check | Status |
|---|---|---|---|---|---|---|
| FE-10 (= OPS-1) | Fix the 3 stale browser tests: derive counts from `DATA` instead of 60/18, open "+N more" before reading tile chips, add stable `data-testid` hooks | ui-builder | tests/test_browser.py, template.html (attributes only) | S | browser suite 18/18 green | done 2026-11-04 |
| RES-1 | **Bug:** the digest picks `2026-11-04_forecast/` instead of the backtest folder, so the standing "no out-of-sample edge" caveat disappears (seen in the 4 Nov snapshot digest). Select by spec type; always print a fixed caveat | integrator | digest.py, tests/test_digest.py | S | new test with sibling folders `X`, `X_features`, `X_forecast`; the caveat sentence is always present | done 2026-11-04 |
| OPS-5 (= FE-9, part 1) | Write `docs/payload.md` (every top-level and row field: type, unit, null meaning) and a contract test: the demo payload, through the CLI path including `alerts`, matches it, and every `DATA.x` the template reads exists | integrator | docs/payload.md, tests/test_payload_contract.py | S-M | the test fails when a planted field rename is made | done 2026-11-04 |
| OPS-2 + RES-7 | Tests skip cleanly without `statsmodels`/`arch`, with an explicit test of the EWMA fallback. Remove hand-typed numbers from the backtest report ("+0.2660%", "59 of 60", "about 660 lags") and derive them from the spec | backtest-analyst | tests/test_feature_experiment.py, tests/test_forecast.py, backtest_report.py | S | suite green with and without the extras; report test on a synthetic universe | done 2026-11-04 |
| OPS-4 (= DATA-11) + OPS-3 | Add `statsmodels` to requirements and split runtime from `requirements-dev.txt` (exact pins; yfinance pinned to the verified version). Add GitHub Actions CI: offline unit job on Python 3.11 and 3.13, plus a browser job with Chromium | test-engineer | requirements*.txt, .github/ | M | CI green on the branch | done 2026-11-04 (workflow written; no GitHub run seen yet) |
| DATA-2 (offline part) | `tests/test_universe.py` (known suffixes, region matches suffix, sector list, share-class format, no duplicate names) and `scripts/verify_universe.py` (needs network; writes `config/universe_verified.csv` with status per ticker: no bars, stale, not equity, name mismatch, currency, under 20B USD) | universe-curator | tests/test_universe.py, scripts/verify_universe.py | M | offline test green now; Iiro runs the script once on his PC | done 2026-11-04 (offline test and script; Iiro still runs the script once on his PC) |
| DATA-7 | One exchange registry (`exchanges.py`: tz, close time, currency, OpenBB provider, index) replacing 4 suffix tables. Fixes Lisbon earnings times being converted in New York time | data-engineer | exchanges.py, validate.py, earnings.py, openbb_source.py | S | old tables equal the derived views; every universe suffix is covered | done 2026-11-04 |
| RES-13 (part) + RES-12c | Merge `classify`/`classify_prev` into one function; test `dd52` with 60-251 bars | screen-logic | screen.py, metrics.py, tests/test_screen.py, tests/test_metrics.py | S | existing tests plus the new ones | done 2026-11-04 (shared `setup_label`; `classify_prev` kept as a wrapper; dd52 short-history test added) |
| OPS-9 + OPS-11 | Fix stale docs: "60 stocks", "about 390/270 tests", PLAN.md status and skills note. Say which demo page is canonical | docs-steward | README.md, TESTING.md, docs/PLAN.md, docs/CLOUD.md, docs/sample-output/README.md | S | a grep shows only intended hits | done 2026-11-04 |

Reviews: stats-reviewer on RES-1 and RES-7; wording-guard on the RES-1 caveat text; ui-reviewer on FE-10 if markup changes.

## Wave 2: foundations other work builds on

| ID | Task | Owner | Locks | Size | Check | Status |
|---|---|---|---|---|---|---|
| DATA-1 (**pair**, first) | Typed source contracts (`sources.py`: `Bars`, `PriceSource`, `FundamentalsSource`, `FxSource`, `IndexSource`) and `tests/fakes.py` (a fake Yahoo that can fail, lag or return NaN) | data-engineer | sources.py, tests/fakes.py, data.py, openbb_source.py, fx.py | M | fakes drive `pull_prices` and `fetch_indices` offline | done 2026-11-05 |
| DATA-1 (**pair**, second) | `cli.main(..., sources=)`; end-to-end offline test of the live branch: raw files, `data_quality.csv`, exit code 2 guard | integrator | cli.py, tests/test_pipeline_live.py | M | live branch tested offline for the first time | done 2026-11-05 |
| FE-3 + FE-4 + FE-7 | Stale-data banner ("data is from Fri 31 Oct; the nightly run may have failed"); visible error message plus `<noscript>` if drawing fails; small bugs (end dot always red, `.foot` unstyled in detail, brief claims to follow all filters, chart width on resize, currency on chart axis) | ui-builder | template.html | M | browser tests with an old payload and a broken row; 4 screenshots | done 2026-11-05 |
| FE-13 | Visual-regression screenshots: default, detail, filters, empty, stale, print states, with font routing and a pixel diff against baselines; `docs/frontend-contract.md` listing the DOM ids tests depend on | ui-builder (after FE-3) | scripts/screenshots.py, tests/visual/, docs/frontend-contract.md | M | a planted colour change is flagged | done 2026-11-05 (baselines are Linux only; first CI run may need them remade) |
| RES-4 | One pre-registration and trial registry (`registry.py`: register before computing, one trial schema, a ledger of periods already viewed); all three runners use it | backtest-analyst | registry.py, backtest_run.py, scripts/run_feature_experiment.py, scripts/run_forecast_calibration.py | M | a runner that computes before registering fails a test | done 2026-11-05 |
| RES-2 | Quality score honesty: show "scored on n/6"; add a `distorted` status (ROE above 100%, or ROE and D/E both missing with positive debt, which suggests negative equity); add a `must_pass` list in settings, empty until Iiro chooses | screen-logic | quality.py, config/settings.toml [quality], tests/test_quality.py | M | known-answer tests: negative equity cannot reach 100; label counts on the snapshot reported as descriptive only | done 2026-11-05: steps 1-3 done (D1 answered; `must_pass` default `net_margin_positive`); RES-11 page part done: neutral label, sort by size of drop, "Dips meeting the check thresholds" |
| OPS-6 + OPS-7 | `tasks.py` (stdlib, Windows and Linux): `demo`, `test`, `test-browser`, `shots`, `check`. Pre-commit guards: a wording scan (buy now, sell, price target, will recover) and a block on staged `data/`, `output/`, `.env` | test-engineer | tasks.py, .pre-commit-config.yaml, scripts/check_wording.py | S-M | `python tasks.py check` green; a planted "buy now" is rejected | done 2026-11-05 |
| OPS-10 + OPS-8 | Topic index for `docs/decisions.md` (or one file per decision) so parallel appends stop conflicting; a short "working in parallel" section in CLAUDE.md pointing to AGENTS.md | docs-steward | docs/decisions*, CLAUDE.md | M | every old entry present exactly once | done 2026-11-05 (D5 A approved 2026-11-04; Rule 4 is in CLAUDE.md) |
| DATA-10 | `run_daily.bat`: one retry 20 minutes after exit code 2; rotate `run.log` at about 5 MB | ops-runner | scripts/run_daily.bat | S | Windows only: Iiro runs it once | done 2026-11-05 (retry and rotation present in the .bat; Windows run still Iiro's) |

## Wave 3: structure that makes later changes cheap

| ID | Task | Owner | Locks | Size | Check | Status |
|---|---|---|---|---|---|---|
| FE-11 + FE-12 (**pair**, first) | Split `template.html` into `src/web/` (tokens, layout, components CSS; one JS file per section) that build into the same single self-contained file. Remove duplicate dark tokens, colliding class names and dead code | ui-builder | src/template.html, src/web/ | M | rendered DOM identical for the demo payload; visual diff clean; axe 0 | done 2026-11-05 (commit 0e838af). Page source is the `src/web/` parts; `src/template.html` is generated by `src/web/assemble.py` and committed. FE-12 cleanups: duplicate dark tokens removed, 2 redundant CSS rules merged, helpers moved. The two class-name clashes (`.more`, `.empty`) are being fixed now |
| FE-11 (**pair**, second) | `render_html` inlines `src/web/` parts, keeps one `__DATA__` and the `</` escape | integrator | dashboard.py (render_html only) | S | test_dashboard green | dropped 2026-11-05: not needed, because `template.html` is generated and committed, so `render_html` keeps reading it as before |
| DATA-3, then DATA-6 | Price pull in batches of about 60 with retry and backoff; re-fetch lagging tickers; OpenBB fallback in a small thread pool. Fundamentals fetch: retry, atomic cache, `stale` flag, refreshes spread over the week | data-engineer | data.py | M | fake tests: a failed batch is retried; a lagging .PA ticker is re-fetched; the cache is never half-written | done 2026-11-05 (5ac8ada: batched pulls, retry, lag re-fetch, threaded fallback, atomic fundamentals cache) |
| RES-6 + RES-8 | Provenance in every spec (code hash, package versions, settings hash per section, seeds from settings). One shared out-of-sample split and one dip-state function for all experiments | backtest-analyst | backtest_run.py, feature_experiment.py, the 3 run scripts | M | editing `[news]` no longer changes the backtest hash; all runners give the same cutoff | review (commits 1778031..c86866e, overnight 2026-11-06): provenance in every spec, one shared split and dip state. The next real backtest and features run get one new spec hash each |
| RES-3 | Dashboard and backtest share one `score_universe`; sector rules move into settings so a change shows in the spec hash | screen-logic (after RES-2) | quality.py, settings.toml [quality] | S-M | V3 quality equals dashboard quality for the same inputs | review (1778031, overnight 2026-11-06) |
| OPS-13 | Windows smoke job in CI: demo run through the `.bat` path and a PowerShell syntax check of `install_task.ps1` | test-engineer | .github/ | M | Windows job green | todo |

## Wave 4: page and data-quality features

| ID | Task | Owner | Locks | Size | Check | Status |
|---|---|---|---|---|---|---|
| FE-1 + FE-2 | Table above the fold (desktop filters on one row, compact phone tiles, shorter brief on phone); sticky table header; first 25 rows plus "Show all N"; skip building the hidden desktop table on phone (21,900 DOM nodes today) | ui-builder | src/web/ | M | first row under 900 px on desktop and under 844 px on phone; screenshots | done 2026-11-05 (5e7213d, 1a3ba93). Measured, demo page: DOM nodes desktop 1934 -> 1053, phone 2258 -> 647. The 21,900-node figure was not reproduced |
| FE-14 (**pair**) | Smaller payload: one shared date axis instead of 252 dates per stock (the page is 4 MB; 77% is chart history) | integrator, then ui-builder | dashboard.py, src/web/ chart | M | file size before and after; chart screenshots unchanged | done 2026-11-05 (18abec6). Measured, demo page: 4.10 -> 2.26 MB |
| DATA-4 + DATA-5 + DATA-8 | Guards: missing FX rate, a whole exchange missing, fundamentals coverage. Partial bars judged by each exchange's close time; "lagging" versus peers. A coverage table per exchange in the digest and `run_meta.json` | data-engineer (validate.py, coverage.py), integrator wires cli and digest (**pair**) | validate.py, coverage.py, then cli.py, digest.py | M | fake runs drop an FX rate or a suffix; Issues, banner and exit code asserted | done 2026-11-05: first half 51fb6f6 (guards, exchange-time partial bars, coverage table); second half 336b6cf, 056ed5b, 3ed2a50 (findings reach badge, digest and `data_quality.csv`; `run_meta.json`; stale-fundamentals warnings; run-health thresholds in settings) |
| DATA-12 + DATA-14 | Cross-check sample includes at least 1 Nordic name; reasons for every failed fetch; fix `verify_sources.py` crashes; index fetch with retry and naive dates | data-engineer (after DATA-4) | crosscheck.py, openbb_source.py, scripts/verify_sources.py, data.py index part | S | seeded sample tests | review (cf62161, overnight 2026-11-06; fetch reasons and verify_sources fixes were done earlier) |
| RES-9 | Beta standard error; floored or uncertain betas labelled "not market-adjusted" instead of "5d resid."; one named "vs index" definition. Any shrinkage chosen by a pre-registered, return-free criterion | screen-logic, then integrator and ui-builder | residual.py, then dashboard.py, src/web/ detail | M | synthetic test: the SE covers the true beta about 95% of the time | review (08a707a, 977dd82; overnight 2026-11-06). BETA_SE_UNCERTAIN = 0.25 is a judgement call, untested on real returns |
| RES-12a | Calibrate the bootstrap and the placebo on null universes with a common factor (about 200 replicates, slow marker) | backtest-analyst | tests/test_backtest.py | M | false-positive rate near nominal | review (227676d, d524264; overnight 2026-11-06). Finding: the interval is biased on null data, see the findings file |
| FE-5 + FE-6 + FE-8 | Chart details by keyboard and touch (click a sector to filter); print stylesheet; filters kept in the URL; light/dark/auto toggle | ui-builder (after FE-1) | src/web/ | M | keyboard test; print PDF looked at; filters survive a reload | todo. FE-8 needs the forced-dark token rule re-added: the unused :root[data-theme=dark] copy was removed in the split (decision 2026-11-05) |

## Wave 5: honest claims and long-run research

| ID | Task | Owner | Locks | Size | Check | Status |
|---|---|---|---|---|---|---|
| RES-11 | A written claims contract (`docs/claims.md`): neutral setup labels such as "Dip, passes 4 of 5 scored checks"; default sort never by score; a generated "What testing found" box; more banned phrases ("likely", "rebound", "undervalued"). Then integrator (digest, alerts ranking) and ui-builder (page) apply it | docs-steward, then integrator and ui-builder | docs/claims.md, digest.py, alerts.py, src/web/ | M | tests assert the box matches the registry and the default sort is not by score | D2 decided B; page part done 2026-11-05; claims.md, digest and alerts parts open |
| RES-5 | Forward ledger: every night appends what was flagged (spec and universe hash); a script scores matured rows at 5/21/63 days. A true holdout without survivorship; needs years for power, stated plainly | backtest-analyst (ledger module, scorer), integrator (nightly hook) | ledger.py, scripts/score_ledger.py, then cli.py | M | append-only and idempotent tests; synthetic matured row | review (4e4c82d..1dc80ff; overnight 2026-11-06). Code is ready; recording starts only after the merge, because the nightly task runs from the main checkout |
| RES-10 | Survivorship: `config/delisted.csv` where history can be found, plus a pre-registered stress bound (how much loser removal would cancel the estimate) | backtest-analyst, universe-curator | config/delisted.csv, scripts/run_backtest.py, backtest_report.py | L | spec lists the delisted names; bound matches a hand computation todo (unblocked: D4 A answered 2026-11-04) |
| DATA-9 | Raw-data retention script (dry run by default; archive, never delete without approval) | data-engineer | scripts/raw_retention.py | S-M | tmp_path test keeps the newest 60 days untouched | review (447485a..9e78793; overnight 2026-11-06). Dry run only on real file names; --apply never run on real data |
| DATA-13 | Earnings coverage for European names: per-exchange coverage report; optional manual overrides file, never used in a backtest | data-engineer | earnings.py, config/earnings_overrides.csv | S-M | override load, expiry and precedence tests | todo |
| OPS-12 | One shared browser helper for tests and screenshots; CI uploads the screenshot set | test-engineer, then ui-builder | tests/browser_util.py, then test_browser.py, screenshots.py | M | CI artifact has the PNGs | todo |

## Decisions needed from Iiro

- **D1 (RES-2):** which quality checks must pass, whatever the share. For example "net margin above 0". This is a definition, not a tested filter, because free fundamentals are not point-in-time. **Answered B 2026-11-04** (net margin above 0 must pass).
- **D2 (RES-11): decided B** (closed). Neutral label "Dip, passes n of m checks"; candidates not sorted by score by default.
- **D3 (DATA-9):** raw-data retention policy, for example keeping every pull for 60 days and then one per week, archived rather than deleted. **Answered A 2026-11-04** (60 days, then first pull of each week, archived, never deleted).
- **D4 (DATA-2):** what to do with tickers `verify_universe.py` flags (delisted, renamed, under 20B USD). Nothing is removed without your yes. **Answered A 2026-11-04** (flagged tickers are only listed).
- **D5 (OPS-8): closed.** Option A approved 2026-11-04; the section is Rule 4 in CLAUDE.md.

## Follow-ups after RES-2 (added 2026-11-05)

| ID | Task | Owner | Status |
|---|---|---|---|
| FU-1 | Regenerate stale samples: `docs/sample-output/digest_example_midsession_2026-11-02.md` (old headings, quality column, old caveat at line ~84), `snapshots/2026-11-04/latest/digest.md` and `daily_review_example_2026-11-02.md` | ops-runner | todo |
| FU-2 | Phone Filters summary says lowercase "quality ≥ N" at `template.html` ~640 and prose at ~625: use "quality score". Phone baselines must be remade | ui-builder | done 2026-11-05 |
| FU-3 | `docs/payload.md` lines ~76/89/90/180 reader-facing wording; enum values untouched | integrator | done 2026-11-05 (38b55e7) |
| FU-4 | `TESTING.md` ~line 63 still describes the old plain-share Intel 67 example; reword after confirming RES-2 behaviour | docs-steward | done 2026-11-05 (TESTING.md line 63 describes the current behaviour) |
| FU-5 | Optional: pass sector to V3 only if Iiro asks (decided 2026-11-05: keep disclosure only) | screen-logic / backtest-analyst | parked |
| FU-6 | `CLAUDE.md` line 1 and line 45 still say "quality-dip dashboard" / "quality score": needs Iiro's approval | docs-steward | blocked: Iiro approval |
| FU-7 | Task 1: `tests/test_web_build.py` calls the private `assemble._lf`; `tests/test_agent_files.py` uses `split("---")[1]`; untracked `.pytest_*` logs and folders in the worktree (`rm -rf` was refused) | test-engineer | todo |
| FU-8 | Task 3: sector names in `[quality.not_applicable]` and `[quality.debt_to_equity_max_by_sector]` are not checked against the universe, so a typo silently disables the rule | screen-logic | todo |
| FU-9 | Task 3: `score_universe` also scores tickers that are later skipped; `QualitySettings` is no longer hashable | screen-logic | todo |
| FU-10 | Task 4: features test hides `oos_fraction` and `start_date` behind the cutoff; backtest converse test skips the quality section; the `start_date` check exists only at `build_data_meta` level | backtest-analyst | todo |
| FU-11 | Task 5: `backtest_run` still calls `split_cutoff` on the calendar (same value); feature report says "last 40%" as fixed text; ABI.BR bad bars are treated differently in forecast and backtest | backtest-analyst | todo |
| FU-12 | Task 6: `missing_columns` sits inside the same `try` as the append and could misreport; the ledger score text prints the 85 to 91% coverage sentence from a synthetic simulation that was not re-run | backtest-analyst, integrator | done (70e2fb5..d5f4ecd: `missing_columns` moved out of the append `try` in 13ba591; the 85 to 91% sentence removed in 70e2fb5) |
| FU-13 | Task 8: the z-score row has no "not market-adjusted" label (kept narrow on purpose) | ui-builder | todo |
| FU-14 | Task 9: the create and fsync failure branches of `apply_moves` have no test | data-engineer | todo |
| FU-15 | Task 10: a `None` from `fetch` skips the retry and misnames the error; `NORDIC_SUFFIXES` differs from `openbb_source` (.OL has no provider); no test for a sample of size 1 | data-engineer | todo |
| FU-16 | Task 13: `CARDS_FIRST = 10` on phone while the ruling said 25 cards; "90 days" is off-screen in More columns by design (cue shown); contrast ratios computed by hand, not by a scanner; the `STOCK_LEVEL` list in `header.js` (status pill) is a judgement call | ui-builder | todo |
| FU-17 | Final review (Important): the forecast `ship_text` opens with "RANGE MAY SHIP" and the console output lacks the definition-change sentence; `score_ledger.py` prints the unreproduced "85 to 91%" as if measured | backtest-analyst | done (verdict now opens with "Descriptive re-check (amended dip rule)"; console prints the definition change; the ledger caveat no longer quotes percentages) |
| FU-18 | Final review (Minor): cli ledger import and an unbound name in an `except`; version copies hold only three settings sections; a test builds the bias in; the Task 11 findings text says the real-scale case "agrees" more strongly than it shows; the brief script path and sector rules; the "Quality dip only" wording; `start_date` held by value in the features spec | various | partly done (70e2fb5..d5f4ecd): cli ledger import guard (13ba591), brief script path and sector rules (d5f4ecd), neutral section name and wording. Still todo: version copies with three settings sections, the bias built into one test, the "agrees" wording, `start_date` held by value |
| FU-19 | Commit trailers on tasks run by Haiku (7, 9, 10) name Haiku 5.5, not the Opus 5.5 line in `common.md` | none | cosmetic |
| FU-20 | Merge blocker: the main checkout has an untracked copy of `docs/plans/2026-11-06-overnight-7h.md`, which the branch also adds. Remove or move it before merging | Iiro | todo |

## Overnight 2026-11-06 (added 2026-11-06)

All items below are on the worktree branch `overnight-2026-11-06` (`git log --oneline f14d55c..HEAD`). Nothing is merged.
They are `review`, not `done`: Iiro has not looked at them. Details: `docs/plans/overnight-findings-2026-11-06.md`.

| Work | Backlog IDs | Commits | Status |
|---|---|---|---|
| Test fixes (line endings, agent-file YAML, Windows file URI in browser tests) | OPS | 3d46794, 98b1c3e | review |
| Real-data check of the 00:15 run, ticker diagnosis (BK, AVB, ROG.SW) | DATA-2 | 7ce33a3..fd9f6be | review (3 yes/no questions open) |
| Shared quality scoring, sector rules in settings | RES-3 | 1778031 | review |
| Provenance in every spec, one shared split and dip state, forecast criterion amendment | RES-6, RES-8 | c275d8d..c86866e | review |
| Forward ledger and scoring script | RES-5 | 4e4c82d..1dc80ff | review (records only after merge) |
| Beta standard error and "not market-adjusted" label (module, payload, page) | RES-9 | 08a707a, 977dd82 | review |
| Raw-data retention script | DATA-9 | 447485a..9e78793 | review |
| Nordic name in the cross-check sample, index fetch retry | DATA-12, DATA-14 | cf62161 | review |
| Null-universe calibration of the primary cell (slow tests) | RES-12a | 227676d, d524264 | review |
| Dashboard look review, ten fixes (list below) | Task 13 (new) | d310bfe..13197d1 | review |
| Research brief 2026-11-06 | Task 14 (new) | 0df91ff, 043a40c | review |

Task 13 dashboard items (all in `src/web/`, template regenerated):
1. Sort chooser visible on phone, plus the line "Sorted by size of drop".
2. Partial-pass setup badge is neutral (no red cross); badge may wrap.
3. Scroll-sideways cue when the table overflows in More columns.
4. Header "5d beyond market (beta-adj.)", clearer definition and rough-beta note.
5. Tile caption ties to the table ("74 of the 92 dips meet the check thresholds ...").
6. Brief ends with "This describes the latest close; it is not a forecast."
7. Status pill neutral for stock-level notes; red at max(5, 5% of rows plus skipped) or an empty region.
8. Phone opened card: flagged because, quality checks and key numbers before chart and headlines.
9. 12 px minimum for small tags and labels, darker secondary ink.
10. 8 px more right padding in the histogram.
Skipped by ruling: item 12 of the reviewer's list. Visual baselines (Linux) need regeneration on Linux.

Task 14: `docs/research/research-brief-2026-11-06.md` (built by `docs/research/build_brief_2026-11-06.py`). A reading list of screen candidates and of large companies with their past volatility, drawdown and beta. It is not advice and not a tested filter.

Not done overnight: FE-5, FE-6, FE-8 (keyboard access to charts, print stylesheet, filters in the URL, theme toggle) stay `todo`; RES-10, RES-11 and DATA-13 were not started.

## Not verified by the audits
Anything needing Yahoo or OpenBB (the sandbox is blocked), Windows behaviour, runtime for 348 tickers, and the ticker
hunches in DATA-2 (NSC, KDP, SOLB.BR, UNA.AS, DOW, HAL, EL, ADM).
