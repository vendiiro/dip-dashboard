"""Live data via yfinance (OpenBB comes in milestone 2). Network access lives only in this module."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

FUND_KEYS = [
    "returnOnEquity", "profitMargins", "debtToEquity", "freeCashflow",
    "revenueGrowth", "marketCap", "forwardPE", "trailingPE", "currency",
]


def fetch_prices(tickers: list[str], period: str = "2y", start: str | None = None) -> dict:
    """2 years of daily adjusted bars: {ticker: (close, volume)}. Tickers without data are omitted.
    Screening uses the last year; the second year lets the chart draw a full-length 200-day average.
    With `start` (ISO date) the history runs from that date instead (used by the backtest)."""
    import yfinance as yf

    kw = {"start": start} if start else {"period": period}
    df = yf.download(tickers, interval="1d", auto_adjust=True, group_by="ticker", threads=True, progress=False, **kw)
    out = {}
    for t in tickers:
        try:
            sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
            out[t] = (sub["Close"], sub["Volume"] if "Volume" in sub else None)
        except Exception:
            continue
    return out


def pull_prices(tickers: list[str], primary: Callable[[list[str]], dict],
                fallback: Callable[[str], tuple | None] | None = None) -> tuple[dict, dict[str, str]]:
    """Primary pull, then the fallback for each ticker the primary did not return (or returned empty).

    Returns (prices, source_by_ticker). Source is "primary" or "fallback"; fallback bars are unadjusted.
    """
    prices = {t: v for t, v in primary(tickers).items() if v is not None and v[0] is not None and len(v[0].dropna())}
    source = {t: "primary" for t in prices}
    if fallback:
        for t in (t for t in tickers if t not in prices):
            got = fallback(t)
            if got is not None:
                prices[t], source[t] = got, "fallback"
    return prices, source


def fetch_indices(specs, fetch_close: Callable[[str], pd.Series | None] | None = None,
                  history: dict[str, pd.Series] | None = None) -> list[dict]:
    """Latest level and 1d / 5d move for each configured index. An index that cannot be fetched is left out.
    If `history` (a dict) is passed, it is filled with {symbol: full close series} (about 2 years) for the beta fit in
    residual.py. The long series never goes into the returned rows, so the dashboard payload stays small."""
    from dataclasses import asdict

    from .metrics import index_move

    fetch_close = fetch_close or _yahoo_index_close
    out = []
    for spec in specs:
        try:
            close = fetch_close(spec.symbol)
            mv = index_move(close)
        except Exception:
            mv = None
        if mv:
            if history is not None:
                history[spec.symbol] = close.dropna()
            c = close.dropna().iloc[-12:]       # recent closes by date, so a stock whose last bar is a day behind is compared on ITS date
            out.append({**asdict(spec), **mv, "closes": {str(d)[:10]: float(v) for d, v in c.items()}})
    return out


def fetch_index_history(symbols: dict[str, str], start: str) -> dict[str, pd.Series]:
    """{group: close series} for the backtest's market baselines, e.g. {"US": "^GSPC"}."""
    import yfinance as yf

    out = {}
    for g, sym in symbols.items():
        c = yf.Ticker(sym).history(start=start)["Close"].dropna()
        c.index = pd.DatetimeIndex(c.index).tz_localize(None).normalize()      # Yahoo returns exchange-local timestamps; compare by date
        out[g] = c
    return out


def _yahoo_index_close(symbol: str) -> pd.Series | None:
    import yfinance as yf

    return yf.Ticker(symbol).history(period="2y")["Close"]


def fetch_raw_closes(ticker: str, start: str, end: str) -> pd.Series | None:
    """Yahoo closes without dividend adjustment (split-adjusted only), for comparing with raw exchange prices."""
    import yfinance as yf

    try:
        df = yf.download(ticker, start=start, end=end, interval="1d", auto_adjust=False, progress=False)
        close = df["Close"]
        close = close.iloc[:, 0] if isinstance(close, pd.DataFrame) else close
        return close.dropna()
    except Exception:
        return None


def fetch_fundamentals(tickers: list[str], cache_path: Path, max_age_days: int = 7) -> dict:
    import yfinance as yf

    cache: dict = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
        except Exception:
            cache = {}
    now = time.time()
    todo = [t for t in tickers if t not in cache or now - cache[t].get("ts", 0) > max_age_days * 86400]

    def get(t):
        try:
            info = yf.Ticker(t).info
            d = {k: info.get(k) for k in FUND_KEYS}
            return t, ({"ts": now, "d": d} if any(v is not None for v in d.values()) else None)
        except Exception:
            return t, None

    if todo:
        print(f"Fetching fundamentals for {len(todo)} tickers (cached for {max_age_days} days)...")
        with ThreadPoolExecutor(8) as ex:
            for t, v in ex.map(get, todo):
                if v:
                    cache[t] = v
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache))
        save_raw_fundamentals({t: cache[t] for t in todo if t in cache}, cache_path.parent / "raw" / "yfinance_fundamentals")
    return {t: cache.get(t, {}).get("d", {}) for t in tickers}


def save_raw_fundamentals(pulled: dict, folder: Path, now: datetime | None = None) -> Path | None:
    """Keep every fundamentals pull as its own file (the 7-day cache above is overwritten in place; this is not)."""
    if not pulled:
        return None
    now = now or datetime.now()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{now:%Y-%m-%dT%H%M%S}.json"
    with path.open("x", encoding="utf-8") as fh:
        json.dump(pulled, fh)
    return path


def parse_news(items: list, limit: int = 5) -> list[dict]:
    """Normalise Yahoo news items (nested `content` format or flat `link`/`publisher` format) to {title, src, url}."""
    out = []
    for n in items[:limit]:
        c = n.get("content") if isinstance(n.get("content"), dict) else n
        title = c.get("title")
        if not title:
            continue
        pub = c.get("provider", {}).get("displayName") if isinstance(c.get("provider"), dict) else c.get("publisher")
        url = None
        for key in ("canonicalUrl", "clickThroughUrl"):
            if isinstance(c.get(key), dict) and c[key].get("url"):
                url = c[key]["url"]
                break
        url = url or c.get("link")
        out.append({"title": title, "src": pub or "", "url": url or ""})
    return out


def fetch_news(ticker: str, limit: int = 5) -> list[dict]:
    """Headlines for one ticker. Yahoo's per-ticker news list came back empty on 2026-11-02, so fall back to its search."""
    import yfinance as yf

    sources = (lambda: yf.Ticker(ticker).news, lambda: yf.Search(ticker, news_count=limit).news)
    for get in sources:
        try:
            items = parse_news(get() or [], limit)
        except Exception:
            items = []
        if items:
            return items
    return []
