---
description: Run the dip-rule event-study backtest with the hygiene checklist
---
Follow CLAUDE.md Rule 1 first (state the plan and which skills you will use; `backtest-hygiene` is mandatory,
`data:statistical-analysis` and `data:validate-data` if available). Then:

1. Restate the rule and universe from `config/settings.toml` and freeze them before running.
2. Pull at least 5 years of daily data; run the data validation from `openbb-data-pull`.
3. Build the event study (signal at close t, entry next open/close, cooldown, costs, baselines, time split).
4. Produce `output/backtests/<date>/report.md` with charts, plus a trial log.
5. Have a second pass review the work for look-ahead, survivorship and leakage (use `data:validate-data`
   or a fresh subagent that did not write the code).
6. Summarise in plain language, including "How much to trust this".
