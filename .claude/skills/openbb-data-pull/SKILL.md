---
name: openbb-data-pull
description: Use when fetching, caching or validating market data (prices, fundamentals, news) for the dip screener via OpenBB with yfinance fallback. Covers provider checks, caching, adjusted prices, currency and data-quality rules.
---

# Data pull conventions

## Provider check first (do not assume)
1. `pip list | findstr -i openbb` and run `openbb-build` after adding extensions.
2. In Python: `from openbb import obb`; list what is available (`dir(obb.equity.price)`, docs at docs.openbb.co).
   Identify which providers actually serve equity daily prices and fundamentals in the installed version.
   OpenBB's company status and V5 provider list were uncertain when this project started: verify, then record
   the result in `docs/decisions.md`.
3. If OpenBB has no usable price provider, use yfinance and say so in the digest footer.

## Fetch rules
- Daily adjusted close and volume, 1 year for screening, longer (5+ years) for backtests.
- Batch requests; cache raw pulls to `data/raw/<source>/<date>.parquet`; never overwrite raw files.
- Fundamentals cached 7 days (`data/fundamentals.json`); record fetch time per ticker.
- Respect rate limits with small thread pools and retries with backoff. Keys come from `.env`.

## Validation (run on every pull, log failures to `output/data_quality.csv`)
- Last bar date per ticker; flag if older than 4 trading days.
- Missing days, zero or negative prices, daily moves above 40% (check for split/adjustment errors).
- Currency per ticker (EUR, SEK, DKK, NOK, CHF, GBP, USD); never compare raw prices across currencies.
- Duplicate listings (for example ADR vs home line); keep one primary listing per company.
- Cross-check five random tickers per run against a second source; log differences above 1%.

## Output
A tidy DataFrame indexed by date with columns per ticker, plus a separate fundamentals table and a
`data_quality` table. Downstream code never calls the network.
