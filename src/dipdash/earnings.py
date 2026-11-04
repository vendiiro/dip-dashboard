"""Last and next earnings-report dates per ticker (Yahoo, current only; NOT point-in-time, never use in a backtest).

The cache (data/earnings.json, 7 days) keeps the raw date rows; the label is worked out from them against the data
date each time, so a cached entry is always judged against today's `asof`. One ticker failing never fails the run:
it gets a written reason, and an older cached value is kept but marked stale."""
from __future__ import annotations

import json
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from .config import EarningsSettings
from .fsio import atomic_write_text
from .screen import trading_days_old

MAX_LAST_AGE_DAYS = 140      # calendar days; a quarterly reporter is never this long between reports, so older = stale data
MAX_NEXT_AHEAD_DAYS = 200    # calendar days; a "next report" further away than two quarters is a placeholder, not a date
ROWS_PER_TICKER = 12
PASSED_DAYS = 14             # a scheduled date this recent with no reported result yet is treated as 'probably just happened'

EXCHANGE_TZ = {".HE": "Europe/Helsinki", ".AS": "Europe/Amsterdam", ".OL": "Europe/Oslo", ".CO": "Europe/Copenhagen",
               ".ST": "Europe/Stockholm", ".SW": "Europe/Zurich", ".DE": "Europe/Berlin", ".PA": "Europe/Paris",
               ".MI": "Europe/Rome", ".MC": "Europe/Madrid", ".BR": "Europe/Brussels", ".L": "Europe/London"}


# ---- pure logic -----------------------------------------------------------------------------------------------
def days_between(a: date, b: date) -> int:
    """Trading days (Mon-Fri, holidays not modelled, same rule as the stale-bar check) from a to b; negative if b is earlier."""
    return trading_days_old(a, b)


def _to_date(x) -> date | None:
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def earnings_context(last_date, next_date, asof, settings: EarningsSettings | None = None) -> dict:
    """Label a stock by its earnings timing. Dates may be date objects or ISO strings.
    An implausible date is dropped and the reason is written into `note`:
    a last report after `asof`, a last report more than 140 days before it, a next report before it or over 200 days after."""
    st = settings or EarningsSettings()
    asof_d = _to_date(asof)
    notes: list[str] = []
    last, nxt = _to_date(last_date), _to_date(next_date)
    if last_date is not None and last is None:
        notes.append(f"last report date '{last_date}' could not be read")
    if next_date is not None and nxt is None:
        notes.append(f"next report date '{next_date}' could not be read")
    if last is not None:
        if last > asof_d:
            notes.append(f"last report {last} is in the future of the data date {asof_d}: not trusted")
            last = None
        elif (asof_d - last).days > MAX_LAST_AGE_DAYS:
            notes.append(f"last report {last} is more than {MAX_LAST_AGE_DAYS} days old: stale, not used")
            last = None
    if nxt is not None:
        if nxt < asof_d:
            notes.append(f"next report {nxt} is in the past of the data date {asof_d}: stale, not used")
            nxt = None
        elif (nxt - asof_d).days > MAX_NEXT_AHEAD_DAYS:
            notes.append(f"next report {nxt} is more than {MAX_NEXT_AHEAD_DAYS} days ahead: placeholder, not used")
            nxt = None
    since = days_between(last, asof_d) if last else None
    until = days_between(asof_d, nxt) if nxt else None
    if since is not None and since <= st.recent_days:
        label = "reported_recently"
    elif until is not None and until <= st.soon_days:
        label = "reports_soon"
    else:
        label = "none"
    if last:
        notes.append(f"reported {last} ({since} trading days before {asof_d})")
    if nxt:
        notes.append(f"next report {nxt} ({until} trading days after {asof_d})")
    if not last and not nxt and not notes:
        notes.append("no earnings dates available")
    return {"last": last.isoformat() if last else None, "next": nxt.isoformat() if nxt else None,
            "days_since_last": since, "days_until_next": until, "label": label, "note": "; ".join(notes)}


def resolve_dates(data: dict, asof) -> dict:
    """From raw rows [{d, rep}] (rep = EPS already reported) and calendar dates, pick last and next relative to `asof`.
    Returns {last, next, estimated, why}. Yahoo does not mark confirmed vs estimated dates; `estimated` is True only
    when the source itself gives a date range for the next report."""
    asof_d = _to_date(asof)
    why: list[str] = []
    rows = [(_to_date(r.get("d")), bool(r.get("rep"))) for r in data.get("rows") or []]
    rows = [(d, rep) for d, rep in rows if d is not None]
    cal = sorted({d for d in (_to_date(x) for x in data.get("cal") or []) if d is not None})

    reported = [d for d, rep in rows if rep and d <= asof_d]
    for d, rep in rows:
        if rep and d > asof_d:
            why.append(f"row {d} says reported but is after the data date {asof_d}: ignored")
    last = max(reported) if reported else None

    upcoming = [d for d, rep in rows if not rep and d >= asof_d and (last is None or d > last)]    # not the report that just happened
    nxt, estimated = (min(upcoming), False) if upcoming else (None, False)
    if nxt is None:
        future_cal = [d for d in cal if d >= asof_d and (last is None or d > last)]
        if future_cal:
            nxt, estimated = future_cal[0], len(cal) > 1
        elif cal:
            why.append(f"calendar date {cal[0]} is in the past: stale, not used")
    passed = [d for d, rep in rows if not rep and d < asof_d and (last is None or d > last) and (asof_d - d).days <= PASSED_DAYS]
    if passed or (last is None and any(not rep and d < asof_d for d, rep in rows)):
        why.append("a scheduled date passed without a reported result yet" + (f" ({max(passed)})" if passed else ""))
    return {"last": last.isoformat() if last else None, "next": nxt.isoformat() if nxt else None,
            "estimated": estimated, "why": "; ".join(why)}


# ---- network fetch (only used when no fetch function is injected) ---------------------------------------------
def fetch_yfinance(ticker: str) -> dict:
    """{"rows": [{"d": ISO date in the exchange's own time zone, "rep": EPS reported}], "cal": [ISO dates]}.
    Yahoo returns timestamps in New York time; converted to the exchange zone the date can still be a day off."""
    import pandas as pd
    import yfinance as yf

    tk = yf.Ticker(ticker)
    suffix = "." + ticker.rsplit(".", 1)[1] if "." in ticker else ""
    tzname = EXCHANGE_TZ.get(suffix, "America/New_York")
    rows, cal, errors = [], [], []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = tk.get_earnings_dates(limit=ROWS_PER_TICKER)
        if df is not None and len(df):
            for ts, r in df.iterrows():
                t = pd.Timestamp(ts)
                t = t.tz_convert(tzname) if t.tzinfo is not None else t
                rows.append({"d": t.date().isoformat(), "rep": bool(pd.notna(r.get("Reported EPS")))})
    except Exception as e:
        errors.append(f"get_earnings_dates: {e}")
    try:
        c = tk.calendar
        for x in (c or {}).get("Earnings Date") or []:
            d = _to_date(x)
            if d:
                cal.append(d.isoformat())
    except Exception as e:
        errors.append(f"calendar: {e}")
    if not rows and not cal and errors:
        raise RuntimeError("; ".join(errors))
    return {"rows": rows, "cal": cal}


# ---- cache + loader -------------------------------------------------------------------------------------------
def _read_cache(path: Path) -> dict:
    try:
        c = json.loads(path.read_text(encoding="utf-8"))
        return c if isinstance(c, dict) else {}
    except Exception:
        return {}


def _fetch_with_retry(t: str, fetch: Callable[[str], dict], retries: int, sleep: Callable[[float], None]) -> tuple[dict | None, str | None]:
    err = "unknown error"
    for attempt in range(max(1, retries)):
        try:
            data = fetch(t)
            if data and (data.get("rows") or data.get("cal")):
                return {"rows": list(data.get("rows") or []), "cal": list(data.get("cal") or [])}, None
            return None, "no earnings data returned by the source"      # an empty answer is final, retrying does not help
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
            if attempt < retries - 1:
                limited = "429" in err or "too many" in err.lower() or "rate" in err.lower()
                sleep((5.0 if limited else 1.0) * 2 ** attempt)
    return None, err


def _save_raw(pulled: dict, folder: Path, now: float) -> Path | None:
    if not pulled:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromtimestamp(now).strftime("%Y-%m-%dT%H%M%S")
    for n in range(100):
        path = folder / (f"{stamp}.json" if n == 0 else f"{stamp}_{n}.json")
        try:
            with path.open("x", encoding="utf-8") as fh:                  # "x": never overwrite a raw pull
                json.dump(pulled, fh)
            return path
        except FileExistsError:
            continue
    return None


def load_earnings(tickers: list[str], cache_path: Path | str, asof, settings: EarningsSettings | None = None,
                  fetch: Callable[[str], dict] | None = None, max_age_days: int = 7, now: float | None = None,
                  workers: int = 4, retries: int = 3, sleep: Callable[[float], None] = time.sleep,
                  raw_dir: Path | str | None = None) -> dict[str, dict]:
    """Earnings context for every ticker. Never raises for a bad ticker.

    Each value: last, next, days_since_last, days_until_next, label, note (see earnings_context) plus
    estimated (bool), stale (bool: the refresh failed and an older value is shown), error (str | None), fetched_at (ISO | None)."""
    cache_path = Path(cache_path)
    fetch = fetch or fetch_yfinance
    now = time.time() if now is None else now
    asof_d = _to_date(asof)
    cache = _read_cache(cache_path)

    def fresh(e) -> bool:
        try:
            if not (isinstance(e, dict) and e.get("ts") is not None and not e.get("stale") and now - e["ts"] <= max_age_days * 86400):
                return False
            # A report scheduled on or after the day we fetched, and on or before the data date, may have happened since:
            # fetch again until Yahoo shows a reported result (or the date is more than PASSED_DAYS old).
            fetched = date.fromtimestamp(e["ts"])
            dates = [(_to_date(r.get("d")), bool(r.get("rep"))) for r in e.get("rows") or []] + [(_to_date(x), False) for x in e.get("cal") or []]
            return not any(d is not None and not rep and fetched <= d <= asof_d and (asof_d - d).days <= PASSED_DAYS for d, rep in dates)
        except Exception:
            return False

    todo = [t for t in tickers if not fresh(cache.get(t))]
    pulled: dict = {}
    if todo:
        with ThreadPoolExecutor(max(1, workers)) as ex:
            results = list(ex.map(lambda t: (t, *_fetch_with_retry(t, fetch, retries, sleep)), todo))
        stamp = datetime.fromtimestamp(now).isoformat(timespec="seconds")
        for t, data, err in results:
            old = cache.get(t) if isinstance(cache.get(t), dict) else {}
            if data is not None:
                cache[t] = {"ts": now, "fetched_at": stamp, "rows": data["rows"], "cal": data["cal"], "error": None, "stale": False}
                pulled[t] = cache[t]
            elif old.get("ts") is not None:                                  # keep the old value, say it is old
                cache[t] = {**old, "stale": True, "error": err, "tried_at": stamp}
            else:
                cache[t] = {"ts": None, "fetched_at": None, "rows": [], "cal": [], "error": err, "stale": False, "tried_at": stamp}
        try:
            atomic_write_text(cache_path, json.dumps(cache))
        except OSError as e:
            print(f"earnings: could not write {cache_path}: {e}")
        if raw_dir is not None:
            try:
                _save_raw(pulled, Path(raw_dir), now)
            except OSError as e:
                print(f"earnings: could not write raw pull: {e}")

    out = {}
    for t in tickers:
        e = cache.get(t) if isinstance(cache.get(t), dict) else {}
        try:
            r = resolve_dates(e, asof_d)
        except Exception as exc:                                              # a malformed cache entry must not abort the run
            e = {"error": f"unreadable cached data: {type(exc).__name__}"}
            r = {"last": None, "next": None, "estimated": False, "why": ""}
        ctx = earnings_context(r["last"], r["next"], asof_d, settings)
        notes = [n for n in (r["why"], ctx["note"]) if n]
        if e.get("error"):
            notes.insert(0, ("refresh failed, showing data fetched " + str(e.get("fetched_at"))[:10] + ": " if e.get("stale") else "") + e["error"])
        ctx["note"] = "; ".join(notes)
        ctx.update(estimated=bool(r["estimated"]), stale=bool(e.get("stale")), error=e.get("error"), fetched_at=e.get("fetched_at"))
        out[t] = ctx
    return out
