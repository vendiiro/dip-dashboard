---
name: dashboard-design
description: Use when building or changing the dip-screener dashboard (HTML) or any chart in this project. Defines layout, visual and verification rules so the dashboard is clear, accessible and easy to scan. Pair with dataviz and frontend-design skills if available.
---

# Dashboard design rules

## Before building
Check whether the `dataviz`, `frontend-design` and `data:build-dashboard` skills are available; read the
ones that apply and follow them where they are more specific than this file.

## Structure (top to bottom)
1. **Header:** title, data date (last market close per region), generated time, data-quality badge
   (for example "3 tickers stale").
2. **Summary tiles:** dips meeting the check thresholds today, new since yesterday, falling-knife flags, market context
   (index move for S&P 500 and STOXX 600) so a market-wide selloff is not mistaken for stock-specific news.
3. **Controls:** window, minimum drop, minimum quality, region, search. Controls change the table live.
4. **Candidate table:** one row per stock; sortable; defaults to the most useful sort. Columns: stock,
   price, 1d / 5d / 1m, distance from 52w high, vs 200d, RSI, quality, setup badge, 90-day sparkline.
   Row click expands: quality checks, valuation context, headlines, longer chart with drop marked.
5. **Context charts below the table:** distribution of today's moves, sector breakdown of fallers.
6. **Footer:** definitions of each metric, data sources, caveats, "not investment advice".

## Visual rules
- One accent colour; red/green only for negative/positive numbers, and never the only cue
  (also use a sign, arrow or label). Check colour-blind safety.
- Tabular numerals, right-aligned numbers, consistent decimals (percentages 1 dp), units in headers.
- Light and dark mode through CSS variables; test both.
- Mobile first: no horizontal page scroll; the table may scroll inside its own container; tap targets >= 40px.
- Sparklines share a scale convention (per-row min-max) and say so in the footer.
- Empty and error states are written out in words ("No stocks match. Loosen the drop slider.").
- Avoid chartjunk: no 3D, no gradients on data, direct labels instead of heavy legends.
- Show the market-wide context next to stock-specific moves; explain badges with a tooltip or legend.
- Escape all external text (headlines) with `textContent`; only allow http(s) links with `rel="noopener noreferrer"`.

## Verify (mandatory)
Render with Playwright and look at screenshots: desktop 1280px and phone 390px, light and dark,
with demo data and with a real run. Check the browser console is free of errors. Fix and re-render
until it reads well at a glance in under 10 seconds: "what is the situation today, which names matter?"
