# Decisions log

Generated file, do not edit by hand. Each decision is its own file in `docs/decisions/`; this page is the topic index,
oldest first in each table (74 decisions). Source files cite this path, so it must keep existing.

## How to add a decision
1. Add a new file `docs/decisions/YYYY-MM-DD-NN-<topic>-<slug>.md`: NN is the next free number for that date, topic is one of
   data, screen, backtest, dashboard, alerts, ops, docs. Never rewrite an old decision; add a new file and say which one it replaces.
2. Layout: `# <one-line title>`, then the lines `- Date:`, `- Topic:`, `- Origin:` (backlog id or who decided), a `---` line,
   a blank line, then the decision text (date, options considered, choice and reason).
3. Rebuild this index: `python tests/test_decisions_index.py --write`. `pytest tests/test_decisions_index.py` fails while it is out of date.

Topics: [Data](#data) (17) · [Screen](#screen) (9) · [Backtest](#backtest) (13) · [Dashboard](#dashboard) (20) · [Alerts](#alerts) (2) · [Ops](#ops) (11) · [Docs](#docs) (2)

## Data

| Date | Decision |
|---|---|
| 2026-10-30 | [Start from a yfinance seed; OpenBB V5 coverage unverified](decisions/2026-10-30-01-data-start-from-a-yfinance-seed-openbb-v5-coverage.md) |
| 2026-11-02 | [Skip tickers whose last bar is more than 4 weekdays old](decisions/2026-11-02-04-data-skip-tickers-whose-last-bar-is-more-than-4.md) |
| 2026-11-02 | [Fundamentals cache moved to data/fundamentals.json](decisions/2026-11-02-06-data-fundamentals-cache-moved-to-data-fundamentals.md) |
| 2026-11-02 | [OpenBB 5.0.0 provider check; openbb pinned](decisions/2026-11-02-09-data-openbb-5-0-0-provider-check-openbb-pinned.md) |
| 2026-11-02 | [yfinance stays the primary price source; OpenBB verifies and falls back](decisions/2026-11-02-10-data-yfinance-stays-the-primary-price-source-openbb.md) |
| 2026-11-02 | [Cross-check against Nasdaq and Nasdaq Nordic agrees](decisions/2026-11-02-11-data-cross-check-against-nasdaq-and-nasdaq-nordic.md) |
| 2026-11-02 | [Not verified: Amsterdam, Xetra, Paris, Swiss and Oslo prices](decisions/2026-11-02-12-data-not-verified-amsterdam-xetra-paris-swiss-and.md) |
| 2026-11-02 | [Bug fixed: empty Yahoo news falls back to search](decisions/2026-11-02-14-data-bug-fixed-empty-yahoo-news-falls-back-to-search.md) |
| 2026-11-02 | [Open: ROG.SW not found on Yahoo; universe unchanged](decisions/2026-11-02-15-data-open-rog-sw-not-found-on-yahoo-universe.md) |
| 2026-11-02 | [Data-quality log checks; raw pulls never overwritten](decisions/2026-11-02-16-data-data-quality-log-checks-raw-pulls-never.md) |
| 2026-11-02 | [Live run: 59 of 60 tickers; INTC move confirmed](decisions/2026-11-02-17-data-live-run-59-of-60-tickers-intc-move-confirmed.md) |
| 2026-11-02 | [Prices downloaded for 2 years for the detail chart](decisions/2026-11-02-21-data-prices-downloaded-for-2-years-for-the-detail.md) |
| 2026-11-02 | [Headlines cleaned and marked untrusted](decisions/2026-11-02-40-data-headlines-cleaned-and-marked-untrusted.md) |
| 2026-11-02 | [Partial bars are reported, not dropped](decisions/2026-11-02-42-data-partial-bars-are-reported-not-dropped.md) |
| 2026-11-04 | [Earnings dates from yfinance; known gaps](decisions/2026-11-04-03-data-earnings-dates-from-yfinance-known-gaps.md) |
| 2026-11-04 | [Offline universe test and verify_universe.py; no ticker is removed](decisions/2026-11-04-12-data-universe-check-never-removes-a-ticker.md) |
| 2026-11-04 | [Exchange facts in one registry; .LS earnings in Lisbon time](decisions/2026-11-04-13-data-exchange-registry.md) |

## Screen

| Date | Decision |
|---|---|
| 2026-10-30 | [Scope: US and European blue chips, long-only, daily refresh](decisions/2026-10-30-02-screen-scope-us-and-european-blue-chips-long-only-daily.md) |
| 2026-10-30 | [Screening thresholds are untested defaults](decisions/2026-10-30-03-screen-screening-thresholds-are-untested-defaults.md) |
| 2026-11-02 | [Thresholds from settings.toml, universe from universe.csv; unknown keys are errors](decisions/2026-11-02-03-screen-thresholds-from-settings-toml-universe-from.md) |
| 2026-11-02 | [RSI of a flat price series is missing, not 100](decisions/2026-11-02-05-screen-rsi-of-a-flat-price-series-is-missing-not-100.md) |
| 2026-11-02 | [Bug fixed: market-cap check converts to USD](decisions/2026-11-02-13-screen-bug-fixed-market-cap-check-converts-to-usd.md) |
| 2026-11-02 | [Observation: plain-share quality score lets INTC score 67](decisions/2026-11-02-28-screen-observation-plain-share-quality-score-lets-intc.md) |
| 2026-11-04 | [Residual move against the stock's own index (descriptive only)](decisions/2026-11-04-02-screen-residual-move-against-the-stock-s-own-index.md) |
| 2026-11-04 | [Screener dd52 uses available history; the backtest needs 252 bars](decisions/2026-11-04-14-screen-dd52-uses-available-history.md) |
| 2026-11-05 | [V3 spec hash excludes must_pass and distorted_roe_above](decisions/2026-11-05-01-screen-v3-spec-hash-excludes-labelling-definitions.md) |

## Backtest

| Date | Decision |
|---|---|
| 2026-11-02 | [Backtest design frozen in spec.json before any return](decisions/2026-11-02-29-backtest-backtest-design-frozen-in-spec-json-before-any.md) |
| 2026-11-02 | [Result: the pre-registered question was not met](decisions/2026-11-02-30-backtest-result-the-pre-registered-question-was-not-met.md) |
| 2026-11-02 | [Changes after the first look (runs 1 and 2)](decisions/2026-11-02-31-backtest-changes-after-the-first-look-runs-1-and-2.md) |
| 2026-11-02 | [Survivorship makes absolute returns meaningless](decisions/2026-11-02-32-backtest-survivorship-makes-absolute-returns-meaningless.md) |
| 2026-11-02 | [Consequences for the project, open for Iiro](decisions/2026-11-02-33-backtest-consequences-for-the-project-open-for-iiro.md) |
| 2026-11-02 | [Independent review of the backtest and what was done](decisions/2026-11-02-35-backtest-independent-review-of-the-backtest-and-what-was.md) |
| 2026-11-02 | [Tests: 248 pass; what was not done](decisions/2026-11-02-36-backtest-tests-248-pass-what-was-not-done.md) |
| 2026-11-04 | [Price-feature experiment: no feature survives Holm](decisions/2026-11-04-05-backtest-price-feature-experiment-no-feature-survives.md) |
| 2026-11-04 | [21-day volatility range not shipped (calibration failed)](decisions/2026-11-04-06-backtest-21-day-volatility-range-not-shipped-calibration.md) |
| 2026-11-04 | [Review follow-ups: forecast and feature-experiment readings](decisions/2026-11-04-09-backtest-review-follow-ups-forecast-and-feature.md) |
| 2026-11-04 | [Digest quotes only event backtests and prints a fixed caveat](decisions/2026-11-04-15-backtest-digest-quotes-event-backtests-only.md) |
| 2026-11-04 | [Holm in numpy; review notes keyed by spec hash](decisions/2026-11-04-17-backtest-holm-in-numpy-notes-by-spec-hash.md) |
| 2026-11-05 | [Backtest report discloses that V3 ignores net-margin, distorted and sector rules](decisions/2026-11-05-04-backtest-report-discloses-v3-ignores-margin-and-sector-rules.md) |

## Dashboard

| Date | Decision |
|---|---|
| 2026-11-02 | [Up/down colours stay blue/red; M0 plan and demo approved](decisions/2026-11-02-01-dashboard-up-down-colours-stay-blue-red-m0-plan-and-demo.md) |
| 2026-11-02 | [New per-row payload fields (sector, dip, why, setup, s200_falling)](decisions/2026-11-02-07-dashboard-new-per-row-payload-fields-sector-dip-why-setup.md) |
| 2026-11-02 | [Template rebuilt from the M0 demo; no placeholder tabs](decisions/2026-11-02-18-dashboard-template-rebuilt-from-the-m0-demo-no-placeholder.md) |
| 2026-11-02 | [Default view follows the CLAUDE.md dip rules](decisions/2026-11-02-19-dashboard-default-view-follows-the-claude-md-dip-rules.md) |
| 2026-11-02 | [New since yesterday is stateless (prev on each row)](decisions/2026-11-02-20-dashboard-new-since-yesterday-is-stateless-prev-on-each.md) |
| 2026-11-02 | [Market context indices; Nordic stocks compared with Helsinki](decisions/2026-11-02-22-dashboard-market-context-indices-nordic-stocks-compared.md) |
| 2026-11-02 | [Page shows data-quality issues, cross-check and FX rates](decisions/2026-11-02-23-dashboard-page-shows-data-quality-issues-cross-check-and.md) |
| 2026-11-02 | [Charts drawn at real width; web fonts optional](decisions/2026-11-02-24-dashboard-charts-drawn-at-real-width-web-fonts-optional.md) |
| 2026-11-02 | [Headlines may be about the wider market](decisions/2026-11-02-25-dashboard-headlines-may-be-about-the-wider-market.md) |
| 2026-11-02 | [Verification: screenshots and browser tests](decisions/2026-11-02-27-dashboard-verification-screenshots-and-browser-tests.md) |
| 2026-11-02 | [Digest sections and the standing backtest line](decisions/2026-11-02-38-dashboard-digest-sections-and-the-standing-backtest-line.md) |
| 2026-11-02 | [New / no longer flagged stay stateless; snapshots dropped](decisions/2026-11-02-39-dashboard-new-no-longer-flagged-stay-stateless-snapshots.md) |
| 2026-11-04 | [Market context: per-country index, 5-day move on the stock's own date](decisions/2026-11-04-01-dashboard-market-context-per-country-index-5-day-move-on.md) |
| 2026-11-04 | [Review follow-up: embedded JSON escapes every <](decisions/2026-11-04-08-dashboard-review-follow-up-embedded-json-escapes-every.md) |
| 2026-11-04 | [Browser tests read stable hooks and derive counts from DATA](decisions/2026-11-04-10-dashboard-browser-tests-use-stable-hooks.md) |
| 2026-11-04 | [Payload documented in docs/payload.md and pinned by a test](decisions/2026-11-04-16-dashboard-payload-contract.md) |
| 2026-11-04 | [Page wrapper is a main landmark; '+N more' has a 32px hit area](decisions/2026-11-04-19-dashboard-main-landmark-more-hit-area.md) |
| 2026-11-05 | [Setup text counts scored checks; distorted rows read 'Dip · data looks unreliable'](decisions/2026-11-05-02-dashboard-setup-text-counts-scored-checks.md) |
| 2026-11-05 | [Neutral page and digest wording](decisions/2026-11-05-03-dashboard-neutral-page-and-digest-wording.md) |
| 2026-11-05 | [Default sort is size of drop](decisions/2026-11-05-05-dashboard-default-sort-is-size-of-drop.md) |

## Alerts

| Date | Decision |
|---|---|
| 2026-11-04 | [Trigger alerts are informational only](decisions/2026-11-04-04-alerts-trigger-alerts-are-informational-only.md) |
| 2026-11-04 | [Review follow-ups: alert state, failure display, earnings memory](decisions/2026-11-04-07-alerts-review-follow-ups-alert-state-failure-display.md) |

## Ops

| Date | Decision |
|---|---|
| 2026-11-02 | [Seed split into src/dipdash/; CLI keeps the seed's flags](decisions/2026-11-02-02-ops-seed-split-into-src-dipdash-cli-keeps-the-seed-s.md) |
| 2026-11-02 | [Tests are pure-function tests plus a demo smoke test](decisions/2026-11-02-08-ops-tests-are-pure-function-tests-plus-a-demo-smoke.md) |
| 2026-11-02 | [yfinance warnings silenced after import](decisions/2026-11-02-26-ops-yfinance-warnings-silenced-after-import.md) |
| 2026-11-02 | [New dependency matplotlib; 200-day label fixed](decisions/2026-11-02-34-ops-new-dependency-matplotlib-200-day-label-fixed.md) |
| 2026-11-02 | [Daily run as built (run_daily.bat, install_task.ps1)](decisions/2026-11-02-37-ops-daily-run-as-built-run-daily-bat-install-task.md) |
| 2026-11-02 | [Failure guard: a run screening under 90% changes nothing](decisions/2026-11-02-41-ops-failure-guard-a-run-screening-under-90-changes.md) |
| 2026-11-02 | [Verified: 283 tests, planted bugs, live dry run](decisions/2026-11-02-43-ops-verified-283-tests-planted-bugs-live-dry-run.md) |
| 2026-11-02 | [Not verified: Windows, unattended review, log rotation](decisions/2026-11-02-44-ops-not-verified-windows-unattended-review-log.md) |
| 2026-11-02 | [Small changes: minus sign, helpers moved to fmt.py](decisions/2026-11-02-45-ops-small-changes-minus-sign-helpers-moved-to-fmt-py.md) |
| 2026-11-04 | [Exact test pins in requirements-dev.txt; CI requires the browser tests](decisions/2026-11-04-18-ops-exact-test-pins-ci-requires-browser.md) |
| 2026-11-04 | [Iiro's choices D1-D5 and the wave-2 answers](decisions/2026-11-04-20-ops-iiro-choices-d1-d5-and-wave-2-answers.md) |

## Docs

| Date | Decision |
|---|---|
| 2026-11-04 | [Canonical demo page is docs/sample-output/dashboard-demo.html](decisions/2026-11-04-11-docs-canonical-demo-page.md) |
| 2026-11-04 | [One file per decision; docs/decisions.md is a generated index](decisions/2026-11-04-21-docs-one-file-per-decision.md) |
