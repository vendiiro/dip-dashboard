# Independent review of the backtest and what was done

- Date: 2026-11-02
- Topic: backtest
- Origin: migrated, old entry 38 of 54 (text verbatim)

---

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
