# Sample output (not part of the program)

These files were produced by the project on 2026-11-02 so you can look at the results without installing anything.

- `dashboard-demo.html`: the dashboard on **synthetic** data (open in a browser). Real tickers, made-up prices.
- `backtest/report.md` with `distribution.png` and `forest.png`: the dip-rule event study on real 2010-2026 history. `spec.json` is the frozen specification, `results.csv` has all 108 cells, `trials.csv` logs every cell of every run.
- `digest_example_midsession_2026-11-02.md`: a real nightly digest. It was made at 10:23 Helsinki time **during** the Nordic session, so 26 European stocks carry still-forming bars; the digest says so. A scheduled 00:15 run does not have this problem.
- `daily_review_example_2026-11-02.md`: what `/daily-review` produces from the digest (written by hand, to the command's specification).

Everything is a screen result for research, not investment advice.
