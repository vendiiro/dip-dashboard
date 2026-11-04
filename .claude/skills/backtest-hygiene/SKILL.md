---
name: backtest-hygiene
description: Use for any backtest, event study or claim that a dip/screening rule works. Enforces point-in-time data, costs, baselines, out-of-sample testing and honest reporting for long-only stock rules.
---

# Backtest hygiene (long-only dip rules)

Run this checklist before reporting any result. If an item cannot be satisfied, say so in the report.

## Design
1. **Write the rule first.** Thresholds, universe, holding horizons (5, 21, 63 trading days) are fixed
   before looking at results. Log every variant tried (a trial log in `output/backtests/trials.csv`).
2. **Event study, not a trading fantasy.** Signal day t from data known at the close of t.
   Enter at the next open or next close (state which), never at the signal bar's own price.
3. **De-duplicate signals.** Same stock signalling on consecutive days is one event: apply a cooldown
   (for example 21 trading days) and report event count after it.
4. **Point-in-time.** Prices only for the historical test. Free fundamentals are not point-in-time:
   do not use today's quality score to filter past events unless the report says this leaks information.
   A price-only version (dip + trend filter) is the clean test; a quality-filtered version is "indicative".
5. **Universe bias.** A current-constituent universe has survivorship bias (losers that were delisted are
   missing), which flatters dip-buying. Say so, and if possible add delisted names or discount results.
6. **Costs.** Apply round-trip cost per region (default 0.10% US/EU large caps, plus spread; make it a setting)
   and show sensitivity at 2x and 4x costs. Note taxes and FX are ignored.

## Evaluation
7. **Baselines.** Compare forward returns against (a) the same stocks on all other days, (b) the market index
   over the same window, (c) a random-date placebo with the same event count. Report excess return, not raw.
8. **Out-of-sample.** Split by time (for example fit/look on the first 60%, report the last 40% untouched).
   Optionally walk-forward. Never tune on the final period.
9. **Clustered uncertainty.** Events cluster in market-wide selloffs (2020, 2022). Report results ex-crash
   periods and use a block or date-cluster bootstrap for confidence intervals. Do not use naive t-stats.
10. **Multiple testing.** If more than a handful of variants were tried, say how many and treat the best as
    a candidate, not a finding (Deflated Sharpe / selection-bias caveat).
11. **Distribution, not just mean.** Report hit rate, median, 10th and 90th percentile, worst case, and
    maximum adverse move after entry. Dips that keep dropping matter more than averages.

## Reporting (what the user sees)
- Lead with: event count, period, universe, costs, and whether the result survives out-of-sample.
- One clear chart: forward-return distribution vs placebo. One table: by horizon and region.
- A "How much to trust this" box listing the remaining biases in plain language.
- Never write that a rule "works" or "will" profit. Use "historically, in this sample".
- Save code, config, trial log and report together so the result is reproducible.
