# Decisions log

Record each decision with date, options considered, choice and reason. Claude: append here.

- 2026-10-30: Start from a yfinance-based seed (`src/dip_screener.py`). OpenBB provider coverage in V5 is unverified;
  verify before depending on it. (See docs/research-report.md for the background research.)
- 2026-10-30: Scope = US and European blue chips, long-only, daily refresh after the close.
- 2026-10-30: Screening thresholds in `config/settings.toml` are untested defaults.
- 2026-11-02: Up/down colours stay blue/red (always with a sign), approved by Iiro after the M0 demo. M0 plan and demo approved.
- 2026-11-02 (M1): Seed split into `src/dipdash/` (config, metrics, quality, screen, data, demo, dashboard, cli).
  `src/dip_screener.py` stays as a thin wrapper, so the commands in START_HERE.md are unchanged.
  Options considered for the CLI: subcommands (`run|demo|backtest`) vs the seed's flags. Kept the flags (`--demo`, `--out`, ...)
  because START_HERE and `run_daily.bat` already use them. A `backtest` subcommand is added in M4 if needed.
- 2026-11-02 (M1): Thresholds now come from `config/settings.toml`; the universe from `config/universe.csv`, which gained a hand-assigned
  `sector` column (approximate GICS-style groups, not an official feed). Unknown keys in settings are an error, so a typo cannot silently
  fall back to a default. `tests/test_config.py` checks that the code defaults equal the file.
- 2026-11-02 (M1): New rule from CLAUDE.md: tickers whose last bar is more than 4 weekdays old (`[data] max_stale_trading_days`)
  are skipped and listed in the payload's `data_quality`. Exchange holidays are not modelled, so a long holiday weekend can skip a
  ticker one day early. The CSV log (`output/data_quality.csv`) comes in M2.
- 2026-11-02 (M1): One intentional behaviour change: RSI of a completely flat price series is now missing (None) instead of 100.
  Not reachable with real data in practice, but 100 would read as "overbought".
- 2026-11-02 (M1): Fundamentals cache moved from `src/.fundamentals_cache.json` to `data/fundamentals.json` (gitignored), as in the target layout.
- 2026-11-02 (M1): Added fields to each row: `sector`, `dip`, `why` (which rules fired), `setup`, `s200_falling`, and per-check `value`.
  The v0 template ignores them; M3 uses them. Verified: demo output equals the seed's on all 60 rows and every original field.
- 2026-11-02 (M1): Tests are pure-function tests with analytic answers (no network, no randomness) plus a demo/CLI smoke test.
  Run: `python -m pytest` from the project root. `python -m dipdash` needs `src` on the path: `cd src && python -m dipdash --demo`.
- 2026-11-02 (M2) OpenBB provider check (openbb 5.0.0, default bundle, per `.claude/skills/openbb-data-pull`): V5 has no `obb.equity` tree; routes are
  per provider. Equity prices: `nasdaq.equity.historical` (US), `cboe.equity.historical` (US; one session behind), `nasdaq.nordic.historical`
  (Helsinki, Stockholm, Copenhagen), `tmx` (Canada). Nothing for Amsterdam, Xetra, Paris, Switzerland or Oslo. All return raw closes, not
  dividend-adjusted. Fundamentals: Nasdaq (US ratios), Nasdaq Nordic, SEC (blocked by network policy here). `openbb-yfinance` 2.1.0 exists on PyPI but
  was not installed or tested (it would wrap the same Yahoo source). Pinned `openbb==5.0.0` in requirements.txt because the V5 provider set is in flux.
- 2026-11-02 (M2) DECISION: **yfinance stays the primary price source; OpenBB is the verifier and the fallback**, not the other way round
  (CLAUDE.md says "OpenBB first"). Reasons: the screener needs dividend-adjusted closes, which no OpenBB provider in this bundle returns, and OpenBB
  covers only about half the universe. Fallback bars (used only if Yahoo returns nothing for a ticker) are unadjusted and logged as `price_source` warnings.
- 2026-11-02 (M2) Cross-check result (docs/m2-data-verification.md): 5 US + INTC vs Nasdaq: 63 days each, max difference 0.005%. 5 Nordic vs Nasdaq Nordic:
  64 days each, identical. Market caps agree within 0.07%. ROE and net margin differ by period (trailing vs last full year; JNJ and Ericsson differ most)
  but all 20 pass/fail outcomes at the 12% / 8% thresholds agree; Kone and Ericsson margins are within 1 point of the 8% line. Debt/equity is defined
  differently by the two sources and is not comparable. The daily run re-checks 5 random US/Nordic tickers (`--no-crosscheck` skips it).
- 2026-11-02 (M2) NOT verified: Amsterdam, Xetra, Paris, Swiss and Oslo lines (ASML.AS, SAP.DE, SIE.DE, NESN.SW, ROG/NOVN, MC.PA, OR.PA, AIR.PA,
  EQNR.OL, DNB.OL) have no independent source reachable from the build environment (Stooq and SEC are blocked by the network policy; every other
  keyless source I tried was US-only or needs an API key). They get the internal checks only. Free keys (Alpha Vantage, Twelve Data) in `.env` would
  allow a check; not set up. Dividend adjustment is not verified for any ticker.
- 2026-11-02 (M2) BUG FOUND in the seed: the "market cap >= 20B" check compared the raw number in local currency (SEK, DKK, NOK, CHF, EUR) with 20B.
  It now converts to USD with Yahoo FX rates (`fx.py`); a missing currency or rate gives "no data", never a guess. Label is now "Market cap >= 20B USD".
  No stock in today's universe changes result; it matters once mid-caps are added. Rates are saved in the payload (`fx_to_usd`).
- 2026-11-02 (M2) BUG FOUND: Yahoo's per-ticker `news` list returns empty and the seed swallowed that silently, so the dashboard would have shown no
  headlines. Now falls back to Yahoo search, and a `news_unavailable` warning is logged if no faller gets any headline. Still no headlines for 6 of 14
  fallers, all non-US: search by ticker finds nothing for them, and search by company name returns loosely related articles (the Siemens query returned an
  unrelated company), which could mislead. Left as is; revisit in M3 (e.g. keep only headlines that mention the company).
- 2026-11-02 (M2) OPEN: `ROG.SW` (Roche) returns "Quote not found" from Yahoo, so it is excluded and logged as an error. `RO.SW` works ("ROCHE I", CHF) but
  SIX has two Roche lines and I could not confirm it is the same security. Universe left unchanged pending Iiro's decision.
- 2026-11-02 (M2) Data-quality log: `output/data_quality.csv` is replaced each run (dated copies come with the daily run in M5). Checks: no data, duplicate or
  unsorted dates, non-positive prices, daily moves over 40%, gaps over 5 weekdays, >5% missing closes, stale bars, currency vs exchange suffix, duplicate
  company names, missing fundamentals. Raw price pulls go to `data/raw/<source>/<date>.csv.gz` (CSV, to avoid adding pyarrow) and are never overwritten;
  each fundamentals pull is kept in `data/raw/yfinance_fundamentals/`. Deferred to M5: marking a partial last bar (the run happens after the close).
- 2026-11-02 (M2) Live run: 59 of 60 tickers, all with bars dated 2026-10-30, about 70 s cold and 8 s with warm fundamentals cache. Largest move in the
  universe, INTC -28.6% on 2026-10-30, was confirmed against Nasdaq, so it is a real move and not a data error.
- 2026-11-02 (M3) Dashboard template rebuilt from the approved M0 demo (`docs/demo/dashboard-demo.html` stays as the design reference). It reads only the
  payload; no synthetic data in the template. The placeholder Backtest and Digest tabs were NOT carried over: a live dashboard should not show invented
  numbers. They come back with real content in M4 and M5.
- 2026-11-02 (M3) DEFAULT VIEW CHANGED from the demo: the demo defaulted to one window (5 days, -7%), which showed 3 dips on live data while the rule in
  CLAUDE.md (1-day <= -4% OR 5-day <= -7% OR >= 12% below the 20-day high) gives 11. The default is now "Default rules", driven by `settings.toml`
  (slider disabled, labelled "set in settings.toml"); the single-window options remain for exploring. A browser test ties the rows shown to the Python `dip`
  flag, and another uses one stock per rule, so a page that implements only one rule fails.
- 2026-11-02 (M3) "New since yesterday" is stateless: each payload row carries `prev` (the same stock's metrics one bar earlier, same fundamentals), so it works on the very
  first run and cannot go stale if a run is skipped. The plan said "snapshots"; daily snapshots are deferred to M5, where the digest needs "no longer flagged".
- 2026-11-02 (M3) Prices are now downloaded for 2 years (screening still uses the last year; metrics are unchanged) so the detail chart can draw a full-length
  200-day average and rolling 52-week high. Payload is about 0.7 MB.
- 2026-11-02 (M3) Market context: S&P 500 (^GSPC), STOXX 600 (^STOXX), OMX Helsinki 25 (^OMXH25) in `settings.toml [[indices]]`. Answer to open question 3: Copenhagen works
  on Yahoo (^OMXC25); Stockholm (^OMXS30) returned a single bar and Oslo (^OSEBX) nothing, so those cannot be added from this source. All Nordic stocks (also
  Stockholm, Copenhagen) are compared with Helsinki, a rough benchmark. "5d vs index" is shown only if the stock and its index have the same last bar date.
- 2026-11-02 (M3) The page shows the data-quality issues, the cross-check results and the FX rates used. Demo runs write `data_quality.demo.csv` so they never overwrite a real log.
- 2026-11-02 (M3) Charts are drawn at the real available width so text keeps its size on a phone (a scaled-down viewBox gave about 7 px labels). Web fonts (IBM Plex) are an
  optional stylesheet link; offline the page falls back to system fonts. The page is otherwise self-contained.
- 2026-11-02 (M3) Headlines: Yahoo's search returns market-wide stories for some tickers (INTC's list had nothing about Intel's -28.6% day), so the panel says
  they may be about the wider market. Still none for 6 non-US fallers. Not a causal explanation; do not read it as one.
- 2026-11-02 (M3) Warnings from inside yfinance (pandas deprecations) are silenced after the yfinance import, because yfinance re-enables them when imported. Real messages remain.
- 2026-11-02 (M3) Verification: `scripts/screenshots.py` renders 1280 px and 390 px, light and dark, and fails on console errors or sideways scroll; run on demo and on a live run
  (59 stocks), all 8 combinations clean. `tests/test_browser.py` (15 tests: filters, sorting, row open/close, data-quality panel, HTML-injection, rule agreement) is skipped if no
  browser is available. Mutation check: 5 planted template bugs (any URL becomes a link, only the 5-day rule, yesterday = today, sort never toggles, text inserted as HTML) are all caught.
- 2026-11-02 (M3) OBSERVATION for M4, not changed: the quality score is a plain share of checks passed, so INTC (ROE -9.6%, net margin -20.1%) scores 67 and shows as a "Quality dip"
  because it passes debt, free cash flow, growth and size. The backtest should say whether this score separates anything, and the score may need weighting or must-pass checks.
- 2026-11-02 (M4) Backtest design, frozen in `output/backtests/<date>/spec.json` BEFORE any return is computed (a test checks the spec exists even if the run crashes):
  price-only dip rule exactly as the dashboard applies it (a test compares the vectorised signals with `metrics.py` + `screen.py` bar by bar and checks they are causal),
  entry at the NEXT close, exit h = 5 / 21 / 63 bars later, 21-bar cooldown per stock, 0.10% round-trip cost with 2x and 4x sensitivity, 60/40 time split at 2020-02-06 with
  in-sample events whose window crosses the cutoff dropped, history from 2010-01-04 (bars from 2008-08 only as warm-up), 59 of 60 stocks (ROG.SW has no data).
  Variants: V1 price-only (primary), V2 without falling knives, V3 with today's quality score (INDICATIVE: today's fundamentals leak into the past).
  ONE pre-registered question: V1, 21 days, out of sample, all regions, excess over the same stock's non-dip days, before costs; supported only if the 90% month-clustered
  bootstrap interval excludes zero. Everything else is descriptive. 9 headline tests; every run is appended to `output/backtests/trials.csv`.
- 2026-11-02 (M4) RESULT of the pre-registered question: NOT met. Out of sample 1,504 events averaged +0.3% over their own stocks' non-dip days at 21 days (90% interval -1.0% to +1.5%).
  In sample +0.8% (0.0% to +1.7%). Date-shift placebo p = 0.54. Excess over the other stocks the same day: 0.0% (-0.4% to +0.4%).
  Tally over all 27 cells (3 variants x 3 horizons x 3 region groups) against the stock's own non-dip days: 14 in-sample intervals exclude zero (the 5-day and 63-day horizons, most clearly
  Europe + Nordic, and V3 at 21 days), and 0 of 27 out of sample, also 0 of 27 with stress days removed; 0 of 27 out-of-sample date-shift p-values are below 0.05 (smallest 0.23).
  The cells overlap, so this is a tally and not 27 independent tests. Whatever looked positive in sample did not show up out of sample; this sample cannot say whether that is regime change or noise.
  The quality filter (V3) and the knife filter (V2) change nothing visible out of sample.
- 2026-11-02 (M4) CHANGES AFTER THE FIRST LOOK (run 1, spec 90205cfc, rows kept in trials.csv; run 2, spec 3a2020e8). Found by reading run 1's own numbers (1 lowers significance, 2 has no predictable direction, 3 is a data fix; the freeze was before run 1, which was a full run, so it is not before anyone saw a number):
  (1) the independent same-stock random-day placebo gave p = 0.002 next to an interval that included zero. It ignores that events share dates, so it understates noise (a test shows it rejecting far too often on
  synthetic data with a shared market factor and no effect); replaced by a date-shift placebo that moves all events together; the independent one stays in results.csv, labelled.
  (2) baseline days now need a computable signal (a stock's first year had counted as "non-dip"). (3) 92 zero-volume bars removed (91 holiday placeholders, 1 corrupt price: NOVO-B.CO 2010-05-14, price doubled, volume 0).
  The primary cell did not move (+0.27%, -1.01% to +1.50%, n = 1,504 in both runs).
- 2026-11-02 (M4) Survivorship makes absolute returns meaningless here: the same stocks' ordinary 21-day windows returned +1.5% (about +20% a year), because the universe is today's winners. Comparisons with their own
  ordinary days are the only informative ones. "Excess over the regional index" looks positive (+0.6%) mostly for that reason (+0.4% on ordinary days).
- 2026-11-02 (M4) Consequences for the project, not decided here: the screen's thresholds and the quality score show no measurable out-of-sample edge in this sample. The dashboard can still be useful as a way to list
  fallers, but the report gives no basis to describe flagged names as likely to recover. Open for Iiro: whether to test other definitions (these would be new trials and need a new pre-registered question),
  whether to add delisted names to the universe, and whether the quality score should use must-pass checks (INTC passes with negative ROE and margin).
- 2026-11-02 (M4) New dependency: matplotlib (report charts). Template label fixed: the 200-day average is compared with its value 20 bars earlier, shown as "vs 20 days ago".
- 2026-11-02 (M4) INDEPENDENT REVIEW (a separate agent that did not write the code; no HIGH findings). It recomputed signals and cooldown events for 5 tickers, 20 forward returns and the primary cell from the raw
  prices without my code: all matched (n = 1,504, excess +0.265954%, bootstrap interval within sampling noise of mine; quarter-length blocks give -1.04% to +1.68%, same verdict). No look-ahead found.
  What it found and what was done:
  (1) index baseline compares dividend-adjusted stocks with price-only indices, so it also carries the dividend yield: DISCLOSED in the report (not measured; not changed, the index column stays the weakest baseline).
  (2) survivorship still biases the "own non-dip days" excess, which I had called the fair/only informative comparison: WORDING CORRECTED in the report ("least distorted", bias stated).
  (3) KNEBV.HE 2025-07-29 (+29.6% then -24.1%, volume 0.3x) is a bad price the 40% and zero-volume checks miss; it makes one false out-of-sample event, moving the primary excess from +0.2660% to +0.2667%:
  left in the numbers (immaterial; removing it would be another trial) and DISCLOSED; a spike-and-revert check was added to the validator. My first version flagged real crash-day reversals (JPM 2008-09-19, many stocks 2020-03-13)
  because it ignored volume; it now needs thin volume (below 0.6x the 20-day median) when volume is known, and is worded "possible" when it is not. It now reports exactly KNEBV.HE (and the real NFLX +42% day).
  (4) spec.json was overwritten each run, so run 1's spec is lost (only its hash survives): specs are now archived by hash and never overwritten; the report states that run 1 was a full run, so this is a freeze before the first run, not before anyone saw a number.
  (5) "all in the more cautious direction" was overstated for the baseline fix: CORRECTED. Reruns 3 and 4 were identical reformatting runs: now explained in the report.
  (6) the trial count understated the family: the log now records every computed cell (108 per run), the report says 9 headline tests planned and 108 cells computed. The older 18-row headline logs are in trials_v1_headline_only.csv.
  While doing this I broke trials.csv by appending a new column layout to the old header (pandas could not read it). Repaired without loss; a layout change now sets the old file aside; a test covers it.
  (7) the date-shift placebo's null is "same stock at another time" and its p-value rests on about 660 distinct lags: p is now shown to two decimals with that note. Calibration was not tested by the reviewer; my synthetic test shows it is
  not anti-conservative on shared-factor data, but a full calibration study was not done. (8) in-sample lower bound is -0.03%, not "0.0%": bounds near zero now print with their sign. In and out of sample are not shown to differ (low power): stated.
  (9) trust list extended: ROG.SW missing, M2 cross-check coverage, flat costs, close-based worst-dip numbers, cooldown spacing of at least 22 bars.
- 2026-11-02 (M4) Tests: 248 pass (browser tests included). Planted-bug checks on the backtest code found and closed two real test gaps (spike-check boundaries, tie handling in the placebo). Not done: a calibration study of the date-shift placebo, a
  total-return index baseline, removal of the KNEBV tick, delisted names in the universe, any change to thresholds or the quality score.
- 2026-11-02 (M5) Daily run, as built: `scripts/run_daily.bat` (CRLF, no locale-dependent date slicing, exit code passed on) runs `src/dip_screener.py --out output\dashboard.html --history`.
  Outputs: `dashboard.html`, `digest.md`, `data_quality.csv`, and dated copies in `output\history\` named by the DATA date (so a market-holiday run does not pile up copies; a rerun on the same data date overwrites
  them and the digest says "same data date as the last saved run"). `scripts/install_task.ps1` registers Tuesday to Saturday 00:15 local time with StartWhenAvailable (catch-up after a missed start),
  RunOnlyIfNetworkAvailable, 1-hour limit, no overlapping runs; `-WakeToRun` and `-Remove` are options. The old START_HERE one-liner (`schtasks /SC DAILY`) ran seven days a week and could not set catch-up: replaced.
- 2026-11-02 (M5) Digest (`digest.py`): sections in the order `/daily-review` reads them (data quality, market context, quality-dip candidates with "flagged because", changes since the previous close, other flagged dips,
  headlines, how to read this). Plain screen wording; a test forbids advice phrases. It carries a standing line quoting the latest backtest (out of sample, interval includes zero) and says the backtest gives no basis for
  reading a flag as a sign of a later rebound. Repeated warnings are grouped (a finding shared by more than 3 stocks becomes one line), in the digest and in the dashboard panel.
- 2026-11-02 (M5) "New since the previous close" / "no longer flagged" stay stateless (each payload row carries the stock's own previous-close state): the snapshot files planned in M3 were not needed and are dropped.
- 2026-11-02 (M5) Headlines are third-party text read later by `/daily-review`: they are cleaned (one line, markup characters removed, capped at 110 characters, two per stock) and placed in a block labelled untrusted.
  A test feeds markup, a fake instruction and a markdown link and checks none survives as structure.
- 2026-11-02 (M5) FAILURE GUARD, found by testing and changed: a run that screens fewer than `[data] min_screened_fraction` of the universe exits with code 2, leaves the dashboard, digest, quality log and history
  byte-for-byte untouched, and writes `data_quality.failed.csv` (removed again by the next good run). I first set the minimum at 50%. A half-dead network (my test) screened 33 of 60 stocks and passed, replacing a 59-stock
  dashboard with a 33-stock one. A normal night screens 59 of 60 (only Roche is missing), so the default is now 90% (54 of 60). My first attempt at the test did not cut the network at all (I overrode only the uppercase proxy
  variables); the second attempt did, and the final run with the 90% guard failed as it should with all six files unchanged. All writes are now atomic (temp file, then swap), so a crash cannot leave a half-written dashboard.
- 2026-11-02 (M5) Partial bars (deferred from M2): a last bar dated today is reported as `partial_bar` (warning). My first manual run was at 10:13 Helsinki time on a Monday, with the Nordic exchanges open; it flagged 16 stocks
  and the candidate list differed from the later complete one (Nokia was a dip on a half-finished session). The scheduled 00:15 run never sees this. I did NOT make the code drop such bars: without exchange calendars and time zones it
  cannot know whether a session is over, and a PC outside Helsinki could then discard a finished day. START_HERE says not to run it by hand mid-session. Demo bars now end on the previous business day.
- 2026-11-02 (M5) VERIFIED: 283 tests pass (the browser ones need Playwright and a Chromium). Ten planted bugs in the new code (guard off, threshold too low, repeat not recognised, stale failure note, non-atomic write, no grouping,
  headline markup kept, everything marked new, yesterday's knife ignored, partial bar never flagged) are all caught. Live dry run of the exact nightly command: 59 stocks, about 70 s, 5-stock cross-check agreed. The digest's 9 candidates
  were recomputed from the raw price file (1-day and 5-day returns within the digest's 0.1% rounding, each meets the rule) and no dip in the data is missing from the digest. `/daily-review` was run by hand from the files
  (283 words, `output/review_2026-11-02.md`).
- 2026-11-02 (M5) NOT VERIFIED: anything on Windows (the batch file, the PowerShell installer, Task Scheduler, catch-up after a missed start, behaviour logged out or asleep, daylight-saving changes). `claude -p "/daily-review"`
  unattended (left commented out). `output\run.log` grows without limit (no rotation). Market holidays are not modelled: the run still happens and the digest flags the repeated data date. The first night's run should be checked by hand.
- 2026-11-02 (M5) Small changes made on the way: "flagged because" text uses the proper minus sign (dashboard detail panel too); `pct`/`interval` helpers moved to `fmt.py` so the nightly run does not import matplotlib.
- 2026-11-04 (market context) "5d vs index" was blank for 23 of 59 rows (every Europe/Nordic row whose latest Yahoo bar lagged). CAUSE: not the region mapping (every Europe/Nordic region had an index) and not currency, but a date mismatch.
  The batch Yahoo pull returned NaN for the latest day on most European lines (the stock's last real bar was 2026-11-02; Nasdaq Nordic cross-check already showed 11-03 existed), while each index is fetched on its own and had 11-03.
  `build_payload` demanded index asof == stock asof, so the cell fell back to "-". Second flaw: every Nordic stock (.ST/.CO/.OL too) was compared with the Helsinki index.
  FIX: (a) per-country mapping by ticker suffix (`suffixes` on an index entry; new `[[country_indices]]` and `[context] fallback_region`), order suffix -> region index -> Europe-wide fallback -> "-" with a written reason (`idx_why`);
  (b) the index's recent closes (12) ride in the payload and the index 5-bar move is taken ENDING ON THE STOCK'S OWN LAST BAR DATE, so a stock a day behind is still compared like for like (no number if that date is absent).
  Edits outside the agreed list, minimal and needed: `data.fetch_indices` (adds `closes`) and `cli.py` (fetches `settings.all_indices`, and the index_missing wording). Backups in the scratchpad `backup2/`.
  Retest on Yahoo 2026-11-04, 1y daily bars (n, last bar, gaps over 4 calendar days; all gaps seen are 5-6 day holiday weekends): ^GSPC 251, 11-03, none; ^STOXX 251, 11-03; ^STOXX50E 251, 11-03; ^OMXH25 251, 11-03;
  ^OMXC25 243, 11-03 (fewer bars: Danish holidays; no gap over 6 days); ^OMXS30 1 bar (UNUSABLE, as before); ^OSEBX 404 (UNUSABLE, as before); ^OMXSPI 251, 11-03 (USED for .ST); OSEBX.OL 251, 11-03 (USED for .OL);
  ^AEX 256, ^GDAXI 254, ^FCHI 256, ^SSMI 251, all 11-03 (USED for .AS .DE .PA .SW); EWD and EWN (USD ETFs) 251, 11-03 but NOT used: a USD ETF's % move contains the USD/SEK or USD/NOK move, so it is not the local market.
  No bar over 5.1% in a day in any kept index. OpenBB 5.0.0 default bundle has no index route (`obb.index` absent), so indices stay Yahoo-only. ^STOXX50E (large-cap Eurozone) fetched fine but is not mapped to anything.
  Currency: a stock's 5-day % move against a local index's 5-day % move is unitless and same-currency, so no FX step is needed. Caveats: ^GDAXI is a total-return index (dividends reinvested), the others price indices; ^OMXSPI and OSEBX.OL are
  all-share indices, not blue-chip ones; holidays differ per exchange so "5 bars" can span slightly different calendar days.
  Live run into the scratchpad (not output/): all 59 screened rows now have a value (before: 23 blank).
- 2026-11-04 (residual move) New `src/dipdash/residual.py`, `residual_move(stock_close, index_close)` -> res1, res5, res5z, beta, beta_raw, beta_clipped, n_obs, asof, reason. Market model: the stock's 1d/5d move minus beta times
  the move of ITS OWN mapped index (`pick_index`). DESCRIPTIVE ONLY: it shows how much of a move the index does not explain; it was NOT backtested and nothing here says it predicts a rebound or anything else.
  Choices: (1) beta = OLS slope with intercept on the last 252 daily returns, EXCLUDING the most recent 5 returns (the very move being measured, so it cannot contaminate beta or residual volatility; a test inserts a -40% crash
  in those bars and beta is unchanged); at least 120 returns or the result is None with a reason (no guess). (2) Stock and index closes are inner-joined on common dates before returns are taken (a missing day on either side becomes
  a multi-day return on both); the index must have a bar on the stock's own last date, else None, so a stock bar one day behind is compared with the index move ending on ITS date and never with a later index bar.
  tz-aware Yahoo index stamps are made naive dates first. (3) No winsorizing (a large daily move is real information here; bad prints are validate.py's job). (4) beta clipped to [0, 3] for the residual, raw value kept: a negative beta
  for a blue chip is estimation noise, not a hedge, and clipping to 0 means "no market adjustment"; beta > 3 is implausible for these names and would over-subtract the index. (5) alpha not subtracted (daily alpha is below its own noise).
  (6) res5z = res5 / (residual daily sd * sqrt(5)); assumes uncorrelated daily residuals and ignores fat tails, so use it to rank, not as a p-value. Residual sd uses the clipped beta.
  Data: `fetch_indices(..., history=dict)` now also fills {symbol: ~2y closes} for the beta fit; the payload rows still carry only the 12 closes. The default Yahoo index fetch changed from 1mo to 2y. Nothing is written to data/.
  Caveats: betas are estimated from one year of one index (all-share/total-return index differences, see the market-context entry); a single event (earnings gap) in the window moves beta; the estimate is wide for a single stock
  (roughly +/-0.2 to 0.3 at 95% for typical stocks with 252 days); the market model leaves out sector and size effects.
  Real run 2026-11-04 (170 stocks): beta median 0.71, min -0.69 (COP), max 3.34 (MU); about 13 stocks had negative raw beta (telecoms, staples, energy, tobacco) and 3 exceeded 3 (MU, AMD, INTC) and were clipped.
- 2026-11-04 (earnings dates) New module `src/dipdash/earnings.py`, cache `data/earnings.json` (7 days, fetch time per ticker, atomic write, raw pulls kept in `data/raw/yfinance_earnings/`), thresholds in `[earnings]` (recent_days 5, soon_days 10).
  SOURCE TEST (yfinance 1.7.0, 2026-11-04, `Ticker.calendar` and `Ticker.get_earnings_dates(limit=12)`; OpenBB v5 has no calendar provider): AAPL, ASML.AS, NESTE.HE, EQNR.OL, NOVO-B.CO, JPM: both calls returned data.
  `calendar` holds only ONE upcoming date and goes stale after a report (ASML.AS 2026-10-14, NESTE.HE 2026-10-29, EQNR.OL 2026-10-28 were all already past while the next quarter was in `get_earnings_dates`), so `get_earnings_dates` is the primary source and `calendar` only a fallback.
  ROG.SW: `calendar` empty, `get_earnings_dates` returned one row from 2016 and Yahoo answered 404 on quoteSummary: no usable date, shown as missing with the reason. `get_earnings_dates` timestamps come in New York time
  (an ASML row reads 2026-07-13 20:00 -04:00), so they are converted to the exchange time zone; the date can still be a day off. Yahoo does NOT mark confirmed versus estimated dates: `estimated` is True only when `calendar` gives a date range (0 of 171 on the live run).
  A row counts as "reported" only when Reported EPS is filled in. Dates after the data date marked reported, last reports older than 140 days, and next dates in the past or over 200 days ahead are dropped with a written reason.
  LIVE (171 tickers, 4 threads, 51 s, 0 fetch errors, data date 2026-11-03, scratch dir): usable last date 144 (84%), usable next date 169 (99%); today reported_recently 54, reports_soon 30, none 87.
  KNOWN GAP: 27 tickers have no usable last date. Yahoo leaves Reported EPS empty on some past rows (WMT, HD, AMAT: the 2026-08 report has no EPS, so the last confirmed one is May, over 140 days old) and has little history for some Paris, Swiss and Dutch lines (MC.PA 1 row, ROG.SW, NESN.SW, OR.PA).
  These are treated as missing, not guessed. Data is current-only, not point-in-time: never use it as a backtest feature. No claim is made that earnings timing predicts anything.
- 2026-11-04 (trigger alerts) New `src/dipdash/alerts.py`, `config/alerts.toml`, `scripts/notify.ps1`; state in `data/alerts_state.json` (atomic write). INFORMATIONAL ONLY: each alert says a research condition the user set became true; none says to act, and a test scans every generated string and these files for banned advice words.
  Conditions (daily closes up to the data date only, no intraday, no network): recovery (close back above the 20-day average, below it the day before), rsi_rebound (RSI(14) from below 30 to 30 or above, same Wilder seed as metrics.rsi14), new_low (close below the lowest close of the previous 60 days; shown as a caution),
  drop_continues (a further 1-day fall of 4% or more for a stock flagged at the previous close; caution), level_cross (user price level, up/down/both, own currency), earnings_window (from the earnings dict passed in, thresholds 5 and 10 trading days; never fetched, the row's own `earn` is ignored), newly_flagged / no_longer_flagged (vs row["prev"]["dip"]).
  Evaluated for flagged candidates plus the [[watch]] list (empty by default). Fire-once: last boolean per (ticker, condition) is stored; an alert is emitted only on false -> true. First run, or missing/corrupt state, is quiet: state is recorded and only one summary of newly flagged names is emitted.
  A stock leaving the evaluated set loses its state (fresh if it returns); stale bars or a missing earnings entry carry the old state over. Ranking: info before caution, quality score descending, then 5d residual (else 5d move) ascending. Notification: ONE balloon, count plus top 3 headlines; JSON file `output/alerts_latest.json` for the dashboard.
  Limits: thresholds are untested defaults, nothing here was backtested and no claim is made that any condition predicts anything; holidays are not modelled in "trading days"; earnings dates come from free, non-point-in-time data.
- 2026-11-04 (price-feature experiment, family `features_2026-11-04`, spec 2190157755c9916b) Pre-registered cheap test on the 171-stock history (parent backtest spec 8583ea959c7ce228; V1 OOS 21d events reproduced: 4,409). Six price-only features at signal close (volume ratio, 12-1 momentum, vol-scaled 1d drop, days since 52w high, 60d realised vol, drawdown from 52w high) vs 21d forward return minus the same-day universe mean; in-sample (4,492 events) fixes the sign only; out-of-sample Spearman rho with 90% month-clustered bootstrap, Holm across 6 at 0.10.
  RESULT: no feature survives Holm (all adjusted p = 1.0; OOS |rho| <= 0.017, every 90% interval includes zero). Minimum detectable rho about 0.05 to 0.09, so a smaller association cannot be resolved here. Conclusion: no tested price feature shows detectable out-of-sample signal in this sample; the dashboard stays a listing and monitoring tool.
  Caveats: survivorship (today's constituents), events cluster in months, no costs (rank correlation), same-day universe mean only removes market and period effects. Code `src/dipdash/feature_experiment.py`, `scripts/run_feature_experiment.py`; output `output/backtests/2026-11-04_features/`; trial log `output/backtests/trials_features.csv` (new file because trials.csv holds mean excess returns with a `primary` flag and does not fit rank correlations).
- 2026-11-04 (21-day volatility range, NOT shipped) New `src/dipdash/forecast.py` (`range_forecast`, `range_label`, `all_ranges`), calibration `scripts/run_forecast_calibration.py`, results in `output/backtests/2026-11-04_forecast/`. Volatility range only: no direction, no price target (direction is not forecastable with ~80 independent OOS months).
  Method: GARCH(1,1)-t via `arch` 8.0.0 (installed into the project venv only, added to requirements.txt), zero conditional mean, filtered historical simulation (bootstrapped standardised residuals, 1000 paths), trailing 750 returns (min 400, else None with a reason); baselines EWMA 0.94 and naive 60-day vol x sqrt(21); non-convergence falls back to EWMA and is flagged `ewma_fallback`.
  Pre-stated criterion (in the module docstring before any result): overall OOS 80% coverage 0.80 +/- 0.04 AND dip-state 0.80 +/- 0.06; two attempts (raw, then one in-sample global scale factor).
  Result (170 stocks, 33,439 walk-forward origins every 21 days, OOS = last 40% of dates, 14,764 origins, 807 in a dip state, month-clustered bootstrap): attempt 1 overall 0.785 [0.759, 0.808] PASS, dip state 0.725 [0.623, 0.819] FAIL; attempt 2 (k = 0.956, in-sample, shrinks the range) overall 0.768 PASS, dip 0.714 FAIL. DECISION: the range does not ship on the dashboard. The model is too narrow after drops (and in 2020 and 2022: 0.759, 0.748); EWMA was closer in dip states (0.779) but was not the pre-stated primary and no third attempt is allowed. A smoke run on 6 stocks was looked at before the full run (plumbing check only; no change was made because of it).
  Limits: survivorship bias, correlated stocks (88 independent months), GARCH underreacts to jumps and earnings gaps, 2.6% of fits fell back to EWMA. Data note: ABI.BR has 70 zero/negative closes that `clean_bars` keeps; the calibration drops them (the backtest does not).

## 2026-11-04: review follow-ups (alerts, forecast, experiment)
- Alerts are now evaluated once per data date: the first run saves the state as it was (`alerts_state.pre.json`) and later runs for the same date start from it. This replaced reuse and merge, which could keep alerts that had become false by the close.
- A failed alert step now shows as "unavailable" on the dashboard and in the digest and overwrites `alerts_latest.json` with count 0 and an error, so it never looks like a quiet day and the notifier cannot announce a stale file. `notify.ps1` also remembers what it announced (`output/alerts_notified.txt`).
- Alert state for `earnings_window` and `new_low` is kept for 15 days when a stock briefly leaves the evaluated set, so one earnings event does not announce itself repeatedly.
- The embedded dashboard JSON now escapes every `<`, not only `</`.
- Forecast: the reading of the dip-state result is "not shown to be calibrated" (95% interval [0.623, 0.819] contains 0.80), not "too narrow". The range still does not ship. The calibration's dip definition used two of the three dip rules.
- Feature experiment: "no detectable signal" must be read with the minimum detectable effect (rho about 0.05 to 0.09). Absence of a detected signal is not evidence of absence.
