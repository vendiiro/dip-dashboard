# Build plan: daily quality-dip dashboard

Status: M0 approved 2026-11-02. M1 approved. M2 approved. M3 approved. M4 approved. M5 done and awaiting Iiro's review. All five milestones are built; Windows scheduling is untested.
Every milestone ends with a stop: I show the result, you give feedback, then I continue.

## 1. The idea in one paragraph
Every night after the US close (00:15 Helsinki, Tue-Sat), a script pulls daily prices for ~60 US, European and
Nordic blue chips. It flags stocks that fell sharply (1-day, 5-day or from their 20-day high). It then sorts those
flags by a simple quality score built from fundamentals (ROE, margin, debt, free cash flow, growth, size). It also
warns when a drop looks like a "falling knife" (long downtrend, far below the 52-week high). The result is a single
self-contained `dashboard.html` plus a short `digest.md`. It answers "what is the situation today, and which names are
worth researching?" in under 10 seconds. A separate event-study backtest checks how stocks behaved historically after
the same kind of dip, against baselines and with honest uncertainty, so the thresholds stop being guesses.
It is a research shortlist, not a signal: no buy/sell wording anywhere.

## 2. What the finished product looks like
| Piece | What you get | Where |
|---|---|---|
| Dashboard | Header with data date + data-quality badge, 4 summary tiles (quality dips, new since yesterday, falling knives, market context), live filters, sortable candidate table with sparklines, expandable rows (1-year chart, quality checks, valuation, headlines, falling-knife checklist), context charts (today's move distribution, fallers by sector), definitions footer | `output/dashboard.html` + `output/history/` |
| Daily digest | Plain-language markdown: data quality, market context, candidates, new / dropped since yesterday | `output/digest.md` |
| Data-quality log | Stale / failed / suspicious tickers per run | `output/data_quality.csv` |
| Backtest report | Event count, costs, baselines, out-of-sample, bootstrap CIs, "How much to trust this" box | `output/backtests/<date>/report.md` + charts |
| Scheduler | `run_daily.bat` + Task Scheduler command | `scripts/` |

## 3. Target code structure
```
config/  universe.csv (+ sector column), settings.toml
src/dipdash/
  config.py      load settings + universe (typed dataclasses)
  data.py        provider layer: OpenBB first, yfinance fallback, caching to data/raw/, validation
  metrics.py     returns, drawdowns, SMA200 slope, RSI, z-score, volume spike (pure functions)
  quality.py     quality checks + score
  screen.py      dip / falling-knife / setup logic, "new since yesterday" via saved snapshot
  dashboard.py   build JSON payload, inject into template.html
  digest.py      write digest.md
  backtest.py    event study (milestone 4)
  cli.py         `python -m dipdash run|demo|backtest`
src/template.html  dashboard shell (from the approved demo)
tests/            pytest on synthetic series (known answers)
```
`src/dip_screener.py` stays as a thin wrapper so `--demo` keeps working at every step.

## 4. Milestones (one at a time, stop after each)
| # | Milestone | Skills used | Verified by |
|---|---|---|---|
| **M0** | **Plan + clickable demo of the target dashboard (this step)** | dashboard-design, dataviz, artifact design | You review the demo; screenshots desktop/phone, light/dark |
| M1 | Refactor seed into `src/dipdash/`, settings read from TOML, universe from CSV, pytest tests on synthetic data (RSI, drawdowns, SMA slope, dip/knife/quality rules, stale-bar skip) | engineering:testing-strategy | `pytest` green; `--demo` output unchanged in substance |
| M2 | Data layer: check what OpenBB V5 actually serves; yfinance fallback; raw cache; validation (stale bars, >40% jumps, currency, duplicates); cross-check 5 US + 5 European tickers against a second source | openbb-data-pull, data:validate-data | Written findings + `data_quality.csv`; decision logged |
| M3 | Real dashboard: turn the approved demo into `template.html`, wire to real payload, add "new since yesterday" snapshots, market context indices | dashboard-design, dataviz | Playwright screenshots (1280 / 390 px, light / dark) with demo and live data; console clean |
| M4 | Event-study backtest of the price-only dip rule (plus an "indicative" quality-filtered variant), costs 1x/2x/4x, three baselines, 60/40 time split, date-clustered bootstrap CIs, trial log | backtest-hygiene, data:statistical-analysis, data:validate-data (+ independent review pass) | Report with "How much to trust this" |
| M5 | Daily run: `run_daily.bat`, `digest.md`, history copies, Task Scheduler instructions, optional `/daily-review` | — | Dry run end to end; log output |

## 5. Skills: chosen and skipped
- **Use:** `dashboard-design` (project rules for layout and verification), `dataviz` (chart forms, colour, hover), `backtest-hygiene` (mandatory for M4), `openbb-data-pull` (M2), `data:validate-data` and `data:statistical-analysis` (M2, M4), `engineering:testing-strategy` (M1).
- **Skipped:** `data:build-dashboard` (we already have a template shell and stricter project rules); TextToQuant (your plan covers crypto only, so it can't backtest equities); `frontend-design` (not installed in this session).

## 6. Decisions I need from you (answer while reviewing the demo)
1. **Colour for up/down.** The demo uses blue = up and red = down, always with a +/− sign. That pair is safer for colour-blind readers than red/green. Keep it, or switch to classic green/red?
2. **Default view.** The demo opens on "All dips", with quality dips sorted to the top and falling knives still visible but badged. Alternative: open on "Quality dips only".
3. **Market context indices.** The demo shows S&P 500, STOXX 600 and OMX Helsinki 25. Add OMX Stockholm 30 / Copenhagen 25?
4. **Where it runs.** I build and test in a Linux cloud container. The `.bat` and Task Scheduler parts (M5) can only be dry-run here, so you'll need to test them once on your Windows machine.
5. **Network.** M2 needs Yahoo/OpenBB reachable from this container. I'll check it at the start of M2; if it's blocked, I'll tell you and we'll decide together.

## 7. Known limits (stated up front)
- Free fundamentals are current-only (not point-in-time). They are used for today's screen, never as a historical filter, except in a clearly labelled "indicative" variant.
- The universe is today's blue chips, which gives survivorship bias and flatters dip-buying in any backtest.
- Thresholds in `settings.toml` are untested defaults until M4.
- Educational research tool, not investment advice.
