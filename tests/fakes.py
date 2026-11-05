"""A configurable fake Yahoo (plus OpenBB fallback) that plugs into dipdash.sources.Sources. No network, no randomness.

    fake = FakeYahoo({"AAA": synth.geometric(300, 0.001), "BBB.ST": ...}, fail={"BBB.ST"}, fallback={"BBB.ST": ...},
                     lag={"CCC": 6}, nan_tail={"DDD": 2}, fx={"SEK": 0.095}, index={"^GSPC": synth.flat(300)})
    src = fake.sources()          # a dipdash.sources.Sources
    fake.calls                    # [("prices", ("AAA", ...)), ("fallback", "BBB.ST"), ...]

Failure modes (each mimics what the real source does, not an idealised error):
  fail       primary returns an all-NaN close (what yf.download gives for a failed ticker); info, news and earnings raise.
  empty      primary returns a zero-length series.
  lag        {ticker: n}: the last n bars are missing, so the newest bar is n business days old.
  nan_tail   {ticker: n}: the last n closes are NaN (a partial / bad bar).
  no_currency  fundamentals come back without "currency".
  fx / index   a currency or index symbol not in the dict returns None (absent pair or index).
  down       the whole batch download raises (network down); the per-ticker fallback still runs.
  flaky      n: the first n download() calls raise (a rate-limited / dropped batch); later calls work.
  lag_heals  tickers in `lag` whose newest bars appear when they are asked for again (a re-fetch fixes the lag).
  fail_first tickers that come back all-NaN the first time and fine the second time.
  info_flaky {ticker: n}: the first n info() calls for that ticker raise (fundamentals retry).
  tz         a time zone such as "America/New_York": every series gets a tz-aware index, like Yahoo's history().
"""
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pandas as pd

from dipdash.data import fetch_fundamentals
from dipdash.sources import Sources

HEALTHY = {"returnOnEquity": 0.25, "profitMargins": 0.20, "debtToEquity": 50.0, "freeCashflow": 5e9,
           "revenueGrowth": 0.08, "marketCap": 200e9, "forwardPE": 20.0, "trailingPE": 22.0}
CURRENCY_BY_SUFFIX = {".ST": "SEK", ".HE": "EUR", ".CO": "DKK", ".OL": "NOK", ".AS": "EUR", ".DE": "EUR", ".PA": "EUR",
                      ".SW": "CHF", ".L": "GBp"}


class FakeNetworkError(RuntimeError):
    """What the fake raises where the real library would raise (HTTP error, timeout)."""


def _as_bars(v) -> tuple[pd.Series, pd.Series | None]:
    if isinstance(v, tuple):
        return v[0].copy(), (None if v[1] is None else v[1].copy())
    return v.copy(), pd.Series(100.0, index=v.index)


def currency_for(ticker: str) -> str:
    return next((c for s, c in CURRENCY_BY_SUFFIX.items() if ticker.endswith(s)), "USD")


class FakeYahoo:
    def __init__(self, prices: dict, *, fail=(), empty=(), lag: dict | None = None, nan_tail: dict | None = None,
                 fallback: dict | None = None, fund: dict | None = None, no_currency=(), fx: dict | None = None,
                 index: dict | None = None, news: dict | None = None, earnings: dict | None = None,
                 down: bool = False, tz: str | None = None, flaky: int = 0, lag_heals=(), fail_first=(),
                 info_flaky: dict | None = None):
        self.prices = {t: _as_bars(v) for t, v in prices.items()}
        self.fail, self.empty, self.no_currency = set(fail), set(empty), set(no_currency)
        self.lag, self.nan_tail = dict(lag or {}), dict(nan_tail or {})
        self.fallback = {t: _as_bars(v) for t, v in (fallback or {}).items()}
        self.fund, self.fx, self.index = dict(fund or {}), dict(fx or {}), dict(index or {})
        self.news_items, self.earnings_data = dict(news or {}), dict(earnings or {})
        self.down, self.tz = down, tz
        self.flaky, self.lag_heals, self.fail_first = flaky, set(lag_heals), set(fail_first)
        self.info_flaky = dict(info_flaky or {})
        self._served: dict[str, int] = {}
        self.calls: list[tuple[str, object]] = []
        self._lock = threading.Lock()                   # fundamentals, earnings and news are fetched from thread pools

    # -- helpers -------------------------------------------------------------------------------------------------
    def _log(self, kind: str, arg) -> None:
        with self._lock:
            self.calls.append((kind, arg))

    def called(self, kind: str) -> list:
        return [a for k, a in self.calls if k == kind]

    def _tz(self, s: pd.Series | None) -> pd.Series | None:
        if s is None or not self.tz or s.index.tz is not None:
            return s
        s = s.copy()
        s.index = s.index.tz_localize(self.tz)
        return s

    def _primary_bars(self, t: str) -> tuple[pd.Series, pd.Series | None]:
        close, vol = self.prices[t]
        with self._lock:
            seen = self._served[t] = self._served.get(t, 0) + 1
        if t in self.fail or (t in self.fail_first and seen == 1):
            close = pd.Series(np.nan, index=close.index)
        if t in self.empty:
            close, vol = close.iloc[:0], (None if vol is None else vol.iloc[:0])
        n = 0 if (t in self.lag_heals and seen > 1) else self.lag.get(t, 0)
        if n:
            close, vol = close.iloc[:-n], (None if vol is None else vol.iloc[:-n])
        k = self.nan_tail.get(t, 0)
        if k:
            close = close.copy()
            close.iloc[-k:] = np.nan
        return self._tz(close), self._tz(vol)

    # -- the source callables ------------------------------------------------------------------------------------
    def download(self, tickers: list[str]) -> dict:
        """PriceSource: like data.fetch_prices on top of yf.download (unknown tickers are simply missing)."""
        self._log("prices", tuple(tickers))
        if self.down:
            raise FakeNetworkError("download failed: network unreachable")
        with self._lock:
            boom = self.flaky > 0
            self.flaky -= boom
        if boom:
            raise FakeNetworkError("download failed: 429 too many requests")
        return {t: self._primary_bars(t) for t in tickers if t in self.prices}

    def fallback_bars(self, ticker: str, start: str, end: str):
        self._log("fallback", ticker)
        b = self.fallback.get(ticker)
        if b is None:
            return None
        close, vol = b
        keep = (close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end))
        return close[keep], (None if vol is None else vol[keep])

    def info(self, ticker: str) -> dict:
        """Yahoo-style `Ticker(t).info`; used through data.fetch_fundamentals(fetch_info=...) so the real cache runs."""
        self._log("info", ticker)
        if ticker in self.fail:
            raise FakeNetworkError(f"404 for {ticker}")
        with self._lock:
            left = self.info_flaky.get(ticker, 0)
            if left:
                self.info_flaky[ticker] = left - 1
        if left:
            raise FakeNetworkError(f"429 for {ticker}")
        d = {**HEALTHY, "currency": currency_for(ticker), **self.fund.get(ticker, {})}
        if ticker in self.no_currency:
            d.pop("currency", None)
        return d

    def fundamentals(self, tickers: list[str], cache_path: Path, status: dict | None = None) -> dict:
        return fetch_fundamentals(tickers, cache_path, fetch_info=self.info, sleep=lambda s: None, pace=0, status=status)

    def fx_last(self, symbol: str) -> float | None:
        self._log("fx", symbol)
        ccy = symbol.removesuffix("USD=X")
        return self.fx.get(ccy, self.fx.get(symbol))

    def index_close(self, symbol: str) -> pd.Series | None:
        self._log("index", symbol)
        s = self.index.get(symbol)
        return None if s is None else self._tz(s.copy())

    def earnings(self, ticker: str) -> dict:
        self._log("earnings", ticker)
        if ticker in self.fail:
            raise FakeNetworkError(f"earnings unavailable for {ticker}")
        return self.earnings_data.get(ticker, {"rows": [], "cal": []})

    def news(self, ticker: str) -> list[dict]:
        self._log("news", ticker)
        if ticker in self.fail:
            raise FakeNetworkError(f"news unavailable for {ticker}")
        return list(self.news_items.get(ticker, []))

    def raw_closes(self, ticker: str, start: str, end: str) -> pd.Series | None:
        self._log("raw_closes", ticker)
        if ticker not in self.prices or ticker in self.fail:
            return None
        close = self.prices[ticker][0]
        return close[(close.index >= pd.Timestamp(start)) & (close.index < pd.Timestamp(end))].dropna()

    def sources(self) -> Sources:
        return Sources(prices=self.download, fallback_bars=self.fallback_bars, fundamentals=self.fundamentals,
                       fx=self.fx_last, index=self.index_close, earnings=self.earnings, news=self.news,
                       raw_closes=self.raw_closes, name="fake")


def yf_download_frame(bars: dict[str, tuple[pd.Series, pd.Series | None]], missing=()) -> pd.DataFrame:
    """The shape yf.download(group_by="ticker") returns: MultiIndex columns (ticker, field). A ticker in `missing`
    gets all-NaN columns, which is what Yahoo does for a symbol it could not fetch."""
    frames = {}
    for t, (close, vol) in bars.items():
        c = pd.Series(np.nan, index=close.index) if t in missing else close
        v = vol if vol is not None else pd.Series(np.nan, index=close.index)
        frames[t] = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": v})
    return pd.concat(frames, axis=1)
