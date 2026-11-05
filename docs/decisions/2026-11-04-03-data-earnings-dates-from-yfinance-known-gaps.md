# Earnings dates from yfinance; known gaps

- Date: 2026-11-04
- Topic: data
- Origin: migrated, old entry 51 of 54 (text verbatim)

---

- 2026-11-04 (earnings dates) New module `src/dipdash/earnings.py`, cache `data/earnings.json` (7 days, fetch time per ticker, atomic write, raw pulls kept in `data/raw/yfinance_earnings/`), thresholds in `[earnings]` (recent_days 5, soon_days 10).
  SOURCE TEST (yfinance 1.7.0, 2026-11-04, `Ticker.calendar` and `Ticker.get_earnings_dates(limit=12)`; OpenBB v5 has no calendar provider): AAPL, ASML.AS, NESTE.HE, EQNR.OL, NOVO-B.CO, JPM: both calls returned data.
  `calendar` holds only ONE upcoming date and goes stale after a report (ASML.AS 2026-10-14, NESTE.HE 2026-10-29, EQNR.OL 2026-10-28 were all already past while the next quarter was in `get_earnings_dates`), so `get_earnings_dates` is the primary source and `calendar` only a fallback.
  ROG.SW: `calendar` empty, `get_earnings_dates` returned one row from 2016 and Yahoo answered 404 on quoteSummary: no usable date, shown as missing with the reason. `get_earnings_dates` timestamps come in New York time
  (an ASML row reads 2026-07-13 20:00 -04:00), so they are converted to the exchange time zone; the date can still be a day off. Yahoo does NOT mark confirmed versus estimated dates: `estimated` is True only when `calendar` gives a date range (0 of 171 on the live run).
  A row counts as "reported" only when Reported EPS is filled in. Dates after the data date marked reported, last reports older than 140 days, and next dates in the past or over 200 days ahead are dropped with a written reason.
  LIVE (171 tickers, 4 threads, 51 s, 0 fetch errors, data date 2026-11-03, scratch dir): usable last date 144 (84%), usable next date 169 (99%); today reported_recently 54, reports_soon 30, none 87.
  KNOWN GAP: 27 tickers have no usable last date. Yahoo leaves Reported EPS empty on some past rows (WMT, HD, AMAT: the 2026-08 report has no EPS, so the last confirmed one is May, over 140 days old) and has little history for some Paris, Swiss and Dutch lines (MC.PA 1 row, ROG.SW, NESN.SW, OR.PA).
  These are treated as missing, not guessed. Data is current-only, not point-in-time: never use it as a backtest feature. No claim is made that earnings timing predicts anything.
