---
description: Review today's screener output and write a short, plain-language summary
---
Follow CLAUDE.md Rule 1 first (state the plan and the skills you will use), then:

1. Read `output/digest.md`, `output/data_quality.csv` and the latest `output/dashboard.html` data.
2. Report data quality first: stale or failed tickers, anything suspicious.
3. Summarise market context (US and Europe index moves) so market-wide selloffs are distinguished
   from stock-specific drops.
4. List the quality-dip candidates, newest first. For each: what dropped, how much, the quality score,
   whether the headlines explain the move, and what would make it a falling knife instead of a temporary dip.
5. Say which names are new since yesterday and which dropped off.
6. End with 2-3 questions worth researching before any decision. No buy/sell wording, no price targets.
Keep it under 300 words. Save it to `output/review_<date>.md`.
