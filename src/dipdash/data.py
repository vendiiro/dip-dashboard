"""Live data via yfinance (OpenBB comes in milestone 2). Network access lives only in this module."""
from __future__ import annotations

import json
import threading
import time
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from .cache import atomic_write_json
from .exchanges import suffix_of

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


PRICE_BATCH = 60            # tickers per download call: big enough to be quick, small enough that one bad call costs little
PRICE_RETRIES = 3           # extra tries after the first failed call of a batch
BACKOFF_SECONDS = 2.0       # wait before retry k is BACKOFF_SECONDS * 2**k (2 s, 4 s, 8 s)
BATCH_PAUSE_SECONDS = 0.5   # polite gap between two batches
FALLBACK_WORKERS = 4        # OpenBB fallback threads (small on purpose: it is the rate-limited path)


def _chunks(items: list, n: int) -> list[list]:
    return [items[i:i + n] for i in range(0, len(items), n)]


def _usable(v) -> bool:
    return v is not None and v[0] is not None and len(v[0].dropna()) > 0


def _why_unusable(got: dict, t: str) -> str:
    if t not in got or got[t] is None or got[t][0] is None:
        return "Yahoo returned no rows for this ticker"
    return "Yahoo returned an empty price series" if len(got[t][0]) == 0 else "Yahoo returned only empty (NaN) closes"


def _download(batch: list[str], primary: Callable[[list[str]], dict], retries: int, backoff: float,
              sleep: Callable[[float], None]) -> tuple[dict, Exception | None]:
    """One batch with retry and exponential backoff. Returns (bars, None) or ({}, last exception)."""
    exc: Exception | None = None
    for attempt in range(retries + 1):
        if attempt:
            sleep(backoff * 2 ** (attempt - 1))
        try:
            return primary(batch), None
        except Exception as e:                          # network, rate limit, library error: all worth another try
            exc = e
    return {}, exc


def _last_bar_date(bars) -> date | None:
    close = bars[0].dropna()
    return close.index[-1].date() if len(close) else None


def lagging_tickers(last_dates: dict[str, date]) -> dict[str, date]:
    """{ticker: the date its peers have} for tickers whose last bar is behind the other tickers of the same exchange.

    The peer date is the newest last-bar date that at least two tickers of that exchange share (or the newest, for a
    group of one), so one odd future-dated bar cannot make a whole exchange look late. Holidays are not modelled: a
    ticker that is merely halted gets one extra, harmless re-fetch."""
    groups: dict[str, list[str]] = {}
    for t in last_dates:
        groups.setdefault(suffix_of(t), []).append(t)
    out: dict[str, date] = {}
    for members in groups.values():
        counts = Counter(last_dates[t] for t in members)
        shared = [d for d, n in counts.items() if n >= 2]
        ref = max(shared) if shared else max(counts)
        out.update({t: ref for t in members if last_dates[t] < ref})
    return out


def pull_prices(tickers: list[str], primary: Callable[[list[str]], dict],
                fallback: Callable[[str], tuple | None] | None = None, *,
                batch_size: int = PRICE_BATCH, retries: int = PRICE_RETRIES, backoff: float = BACKOFF_SECONDS,
                pause: float = BATCH_PAUSE_SECONDS, sleep: Callable[[float], None] = time.sleep,
                reasons: dict[str, str] | None = None, refetch_lagging: bool = True,
                fallback_workers: int = FALLBACK_WORKERS) -> tuple[dict, dict[str, str]]:
    """Primary pull in batches, then the fallback for each ticker the primary did not return (or returned empty).

    1. Batches of `batch_size`; a batch that raises is retried `retries` times with exponential backoff. If EVERY batch
       fails the last error is raised (nothing to screen; the caller keeps yesterday's files). Otherwise the tickers of a
       dead batch go on to the fallback.
    2. Tickers still missing get one more primary pass (Yahoo often drops tickers under rate limiting).
    3. Tickers whose last bar is behind their exchange peers are re-fetched once; newer bars replace older ones.
    4. Remaining misses go to `fallback(ticker)` in a small thread pool (fallback bars are unadjusted).

    Returns (prices, source_by_ticker); source is "primary" or "fallback". If `reasons` (a dict) is passed it is filled
    with {ticker: plain-language reason} for every failed fetch step, so data_quality can show why (a ticker can have a
    reason and still be in `prices`, for example when the fallback saved it or a re-fetch did not help).
    Raw pulls are not written here; the caller saves them with cache.save_raw_prices, which never overwrites."""
    reasons = {} if reasons is None else reasons
    tickers = list(dict.fromkeys(tickers))
    prices: dict = {}
    dead: set[str] = set()
    ok_batches, last_exc = 0, None
    for i, batch in enumerate(_chunks(tickers, batch_size)):
        if i:
            sleep(pause)
        got, exc = _download(batch, primary, retries, backoff, sleep)
        if exc is not None:
            last_exc = exc
            dead.update(batch)
            for t in batch:
                reasons[t] = f"price download failed after {retries + 1} attempts: {type(exc).__name__}: {exc}"
            continue
        ok_batches += 1
        for t in batch:
            if _usable(got.get(t)):
                prices[t] = got[t]
            else:
                reasons[t] = _why_unusable(got, t)
    if tickers and not ok_batches:
        raise last_exc                                  # type: ignore[misc]  (set whenever no batch succeeded)
    source = {t: "primary" for t in prices}

    missing = [t for t in tickers if t not in prices and t not in dead]
    if missing:                                         # one more pass for tickers Yahoo dropped
        sleep(backoff)
        for batch in _chunks(missing, batch_size):
            got, exc = _download(batch, primary, 0, backoff, sleep)
            for t in batch:
                if exc is not None:
                    reasons[t] = f"{reasons.get(t, 'no data')}; second try raised {type(exc).__name__}: {exc}"
                elif _usable(got.get(t)):
                    prices[t], source[t] = got[t], "primary"
                    reasons.pop(t, None)

    if refetch_lagging and prices:
        last = {t: d for t in prices if source[t] == "primary" and (d := _last_bar_date(prices[t])) is not None}
        late = lagging_tickers(last)
        for batch in _chunks(list(late), batch_size):
            sleep(pause)
            got, exc = _download(batch, primary, 0, backoff, sleep)
            for t in batch:
                new = got.get(t) if exc is None else None
                nd = _last_bar_date(new) if _usable(new) else None
                if nd is not None and nd > last[t]:
                    prices[t] = new
                else:
                    reasons[t] = (f"last bar {last[t]} is behind its exchange peers ({late[t]}); "
                                  f"re-fetch gave {'an error' if exc is not None else 'no newer bar'}")

    if fallback:
        todo = [t for t in tickers if t not in prices]

        gates = [threading.Event() for _ in todo]
        gates.append(threading.Event())

        def one(i):
            t = todo[i]
            if i:
                gates[i - 1].wait()                     # calls start in list order (stable logs), then run side by side
            try:
                gates[i].set()
                return t, fallback(t), None
            except Exception as e:
                return t, None, e

        if todo:
            with ThreadPoolExecutor(max(1, min(fallback_workers, len(todo)))) as ex:
                for t, got, err in ex.map(one, range(len(todo))):
                    if got is not None and _usable(got):
                        prices[t], source[t] = got, "fallback"
                        reasons[t] = f"{reasons.get(t, 'primary source had no data')}; used the OpenBB fallback"
                    elif err is not None:
                        reasons[t] = f"{reasons.get(t, 'no data')}; OpenBB fallback raised {type(err).__name__}: {err}"
                    else:
                        reasons[t] = f"{reasons.get(t, 'no data')}; OpenBB fallback had no data"
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


INDEX_ATTEMPTS = 3           # tries per index symbol for the backtest baselines
INDEX_BACKOFF_SECONDS = 2.0  # wait before retry k is INDEX_BACKOFF_SECONDS * 2**k (2 s, then 4 s)


def _yahoo_history_close(symbol: str, start: str) -> pd.Series:
    import yfinance as yf

    return yf.Ticker(symbol).history(start=start)["Close"]


def fetch_index_history(symbols: dict[str, str], start: str, *,
                        fetch: Callable[[str, str], pd.Series] | None = None,
                        sleep: Callable[[float], None] = time.sleep) -> dict[str, pd.Series]:
    """{group: close series} for the backtest's market baselines, e.g. {"US": "^GSPC"}.

    `fetch(symbol, start)` returns a close series (default: yfinance). Each symbol gets INDEX_ATTEMPTS tries with
    2 s and 4 s waits in between; if all fail, RuntimeError names the symbol. Dates are returned naive and normalised
    to midnight, whichever source supplied them, so the series can be compared by date."""
    fetch = fetch or _yahoo_history_close
    out = {}
    for g, sym in symbols.items():
        c = _fetch_with_retry(sym, start, fetch, sleep)
        c = c.dropna()
        c.index = pd.DatetimeIndex(c.index).tz_localize(None).normalize()      # Yahoo returns exchange-local timestamps; compare by date
        out[g] = c
    return out


def _fetch_with_retry(sym: str, start: str, fetch: Callable[[str, str], pd.Series],
                      sleep: Callable[[float], None]) -> pd.Series:
    last: Exception | None = None
    for attempt in range(INDEX_ATTEMPTS):
        if attempt:
            sleep(INDEX_BACKOFF_SECONDS * 2 ** (attempt - 1))
        try:
            return fetch(sym, start)
        except Exception as e:                          # network, rate limit, library error: worth another try
            last = e
    raise RuntimeError(f"index history for {sym} failed after {INDEX_ATTEMPTS} attempts: "
                       f"{type(last).__name__}: {last}") from last


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


def _yahoo_info(ticker: str) -> dict:
    import yfinance as yf

    return yf.Ticker(ticker).info


FUND_RETRIES = 2            # extra tries per ticker after an exception
FUND_MIN_AGE_DAYS = 4       # no ticker is refreshed before it is this old (unless it has no cache entry)
FUND_WORKERS = 4            # fewer threads than before (was 8): Yahoo's info endpoint is the rate-limited one
FUND_PACE_SECONDS = 0.25    # minimum gap between two info requests, across all threads


def refresh_age_days(ticker: str, max_age_days: int = 7, min_age_days: int = FUND_MIN_AGE_DAYS) -> int:
    """Deterministic per-ticker refresh age in whole days, between min_age_days and max_age_days.

    A cache entry is refreshed once it is at least this old, so entries first filled on the same night come due on
    different nights instead of all at once. crc32 is used because Python's hash() changes between runs."""
    lo = min(min_age_days, max_age_days)
    return lo + zlib.crc32(ticker.encode("utf-8")) % (max_age_days - lo + 1)


class _Pacer:
    """Keeps at least `gap` seconds between request starts across threads. Clock and sleep are injectable."""

    def __init__(self, gap: float, sleep: Callable[[float], None], clock: Callable[[], float] = time.monotonic):
        self.gap, self.sleep, self.clock = gap, sleep, clock
        self._lock, self._next = threading.Lock(), 0.0

    def wait(self) -> None:
        if self.gap <= 0:
            return
        with self._lock:
            now = self.clock()
            at = max(now, self._next)
            self._next = at + self.gap
        if at > now:
            self.sleep(at - now)


def _read_fund_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(cache, dict):
            raise ValueError("cache is not a JSON object")
        return cache
    except Exception:
        # Keep the unreadable file for a look instead of silently replacing it; never overwrite an earlier .bad file.
        bad = cache_path.with_name(f"{cache_path.name}.bad-{datetime.now():%Y%m%dT%H%M%S}")
        try:
            if not bad.exists():
                cache_path.replace(bad)
        except OSError:
            pass
        return {}


def fetch_fundamentals(tickers: list[str], cache_path: Path, max_age_days: int = 7,
                       fetch_info: Callable[[str], dict] | None = None, *,
                       retries: int = FUND_RETRIES, backoff: float = BACKOFF_SECONDS,
                       sleep: Callable[[float], None] = time.sleep, now: float | None = None,
                       workers: int = FUND_WORKERS, pace: float = FUND_PACE_SECONDS,
                       min_age_days: int = FUND_MIN_AGE_DAYS, status: dict | None = None) -> dict:
    """{ticker: {FUND_KEYS...}} from a cache, refreshing entries. `fetch_info(ticker)` returns a Yahoo-style info dict;
    default is yfinance (tests inject a fake so nothing touches the network).

    - Missing tickers are always fetched. Cached ones are refreshed when older than their own refresh age
      (`refresh_age_days`, between min_age_days and max_age_days), so refreshes spread over the week.
    - At most about 2/max_age_days of the list is renewed per night (oldest first); missing tickers are always fetched.
    - Each fetch is retried `retries` times with exponential backoff when it raises; requests are paced `pace` seconds
      apart. A ticker that still fails keeps its old cache entry.
    - The cache file is written atomically (temp file, fsync, rename): a crash leaves the old file, never half a file.
    - An entry older than `max_age_days` that could not be refreshed is stale. If `status` (a dict) is passed it is
      filled with {ticker: {"stale": bool, "age_days": float | None, "fetched_at": iso | None, "error": str | None}}
      for every requested ticker. The returned values are unchanged (payload fields do not move)."""
    fetch_info = fetch_info or _yahoo_info
    cache = _read_fund_cache(cache_path)
    now = time.time() if now is None else now
    ttl = max_age_days * 86400

    def due(t: str) -> bool:
        e = cache.get(t)
        if not isinstance(e, dict) or not e.get("ts") or not isinstance(e.get("d"), dict):
            return True
        return now - e["ts"] >= refresh_age_days(t, max_age_days, min_age_days) * 86400

    uniq = list(dict.fromkeys(tickers))
    missing = [t for t in uniq if not (isinstance(cache.get(t), dict) and cache[t].get("ts") and isinstance(cache[t].get("d"), dict))]
    # Entries that are merely due are capped per night, oldest first, so equal refresh ages that happen to line up cannot send
    # the whole universe to Yahoo on one night. Missing entries are never capped; the cap is about 2/max_age_days of the list.
    cap = max(1, -(-len(uniq) * 2 // max_age_days))
    renew = sorted((t for t in uniq if t not in missing and due(t)), key=lambda t: cache[t]["ts"])[:cap]
    todo = missing + renew
    errors: dict[str, str] = {}
    pacer = _Pacer(pace, sleep)

    def get(t):
        err = "no fundamentals returned"
        for attempt in range(retries + 1):
            if attempt:
                sleep(backoff * 2 ** (attempt - 1))
            pacer.wait()
            try:
                info = fetch_info(t) or {}
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                continue
            d = {k: info.get(k) for k in FUND_KEYS}
            if any(v is not None for v in d.values()):
                return t, {"ts": now, "fetched_at": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
                           "d": d}, None
            return t, None, "no fundamentals returned"          # an answer with nothing in it is not worth retrying
        return t, None, f"failed after {retries + 1} attempts: {err}"

    if todo:
        print(f"Fetching fundamentals for {len(todo)} tickers (refreshed after {min_age_days}-{max_age_days} days)...")
        with ThreadPoolExecutor(max(1, workers)) as ex:
            for t, v, err in ex.map(get, todo):
                if v:
                    cache[t] = v
                else:
                    errors[t] = err
        atomic_write_json(cache_path, cache)
        save_raw_fundamentals({t: cache[t] for t in todo if t in cache and cache[t].get("ts") == now},
                              cache_path.parent / "raw" / "yfinance_fundamentals")

    if status is not None:
        for t in tickers:
            e = cache.get(t) if isinstance(cache.get(t), dict) else None
            age = (now - e["ts"]) / 86400 if e and e.get("ts") else None
            status[t] = {"stale": age is not None and age * 86400 > ttl,       # nothing cached is "missing" (see error), not stale
                         "age_days": age, "fetched_at": e.get("fetched_at") if e else None, "error": errors.get(t)}
    return {t: cache.get(t, {}).get("d", {}) for t in tickers}


def save_raw_fundamentals(pulled: dict, folder: Path, now: datetime | None = None) -> Path | None:
    """Keep every fundamentals pull as its own file (the 7-day cache above is overwritten in place; this is not)."""
    if not pulled:
        return None
    now = now or datetime.now()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{now:%Y-%m-%dT%H%M%S}.json"
    n = 1
    while path.exists():                                # a second pull in the same second gets a suffix, never overwrites
        path = folder / f"{now:%Y-%m-%dT%H%M%S}_{n}.json"
        n += 1
    atomic_write_json(path, pulled)
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
