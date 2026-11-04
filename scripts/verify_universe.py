#!/usr/bin/env python3
"""Check every ticker in config/universe.csv against Yahoo and write config/universe_verified.csv.

Needs network and yfinance (project venv). Run on Iiro's PC, small first:

    .venv\\Scripts\\python.exe scripts\\verify_universe.py --limit 10
    .venv\\Scripts\\python.exe scripts\\verify_universe.py

It never removes a ticker (decision D4); it only reports a status per ticker. Several statuses are joined by ';'.
Results are written row by row, so a re-run resumes (rows with fetch_error are retried).
Exit code: 0 normally (flags are not errors), 2 if the network failed for more than half the tickers.

Statuses: ok, no_bars, stale, not_equity, name_mismatch, currency_mismatch, under_20b, duplicate_name, fetch_error.
Market cap uses today's value (not point-in-time); educational screen only.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dipdash.fx import fetch_fx_to_usd, usd_value  # noqa: E402
from dipdash.screen import trading_days_old  # noqa: E402

# TODO(DATA-7): replace with the exchange registry. suffix -> (region, currency); "" is the US.
SUFFIX_CURRENCY = {"": "USD", ".PA": "EUR", ".DE": "EUR", ".ST": "SEK", ".SW": "CHF", ".HE": "EUR", ".MI": "EUR",
                   ".AS": "EUR", ".MC": "EUR", ".CO": "DKK", ".OL": "NOK", ".BR": "EUR", ".LS": "EUR"}
NORDIC_SUFFIXES = (".HE", ".ST", ".CO", ".OL")

COLUMNS = ["ticker", "csv_name", "yahoo_long_name", "name_score", "quote_type", "exchange", "currency",
           "expected_currency", "first_bar", "last_bar", "bar_count", "market_cap_usd", "status", "detail", "verified_at"]
STATUSES = ["ok", "no_bars", "stale", "not_equity", "name_mismatch", "currency_mismatch", "under_20b",
            "duplicate_name", "fetch_error"]

_LEGAL = {"inc", "incorporated", "corp", "corporation", "co", "company", "plc", "ag", "se", "sa", "nv", "ltd",
          "limited", "llc", "lp", "group", "holding", "holdings", "spa", "ab", "asa", "oyj", "as", "the", "de"}


def suffix_of(ticker: str) -> str:
    m = re.search(r"\.[A-Z]{2}$", ticker)
    return m.group(0) if m else ""


def normalize_name(name: str) -> str:
    """Lowercase, drop punctuation and legal suffixes (Inc, plc, AG, ...). Used for duplicate and name checks."""
    words = re.sub(r"[^a-z0-9 ]", "", re.sub(r"[-/]", " ", (name or "").lower().replace("&", " and "))).split()
    kept = [w for w in words if w not in _LEGAL]
    return " ".join(kept or words)


def name_score(csv_name: str, yahoo_name: str | None) -> float:
    """0..1 similarity between our short name and Yahoo's long name (1.0 if one contains the other)."""
    a, b = normalize_name(csv_name), normalize_name(yahoo_name or "")
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 3)


def classify_row(ticker: str, csv_name: str, info: dict | None, bars: dict | None, today: date, *,
                 rates: dict[str, float], dup_names: set[str] | frozenset = frozenset(),
                 min_cap_usd: float = 20e9, max_stale: int = 4, name_threshold: float = 0.6) -> dict:
    """Pure: build one output row (without verified_at) from fetched info and bar summary.

    info: Yahoo info dict (longName, quoteType, exchange, currency, marketCap) or None if the fetch failed.
    bars: {"first": date, "last": date, "count": int} or None/empty count when no bars came back.
    """
    expected = SUFFIX_CURRENCY.get(suffix_of(ticker))
    row = {c: "" for c in COLUMNS}
    row.update(ticker=ticker, csv_name=csv_name, expected_currency=expected or "")
    flags: list[str] = []
    notes: list[str] = []

    if info is None and bars is None:
        row.update(status="fetch_error", detail="no data returned (network or Yahoo error)")
        return row

    if info is None:
        flags.append("fetch_error")
        notes.append("info call failed")
    else:
        row.update(yahoo_long_name=info.get("longName") or info.get("shortName") or "",
                   quote_type=info.get("quoteType") or "", exchange=info.get("exchange") or "",
                   currency=info.get("currency") or "")
        if row["quote_type"] != "EQUITY":
            flags.append("not_equity")
            notes.append(f"quoteType={row['quote_type'] or 'missing'}")
        if row["yahoo_long_name"]:
            sc = name_score(csv_name, row["yahoo_long_name"])
            row["name_score"] = sc
            if sc < name_threshold:
                flags.append("name_mismatch")
                notes.append(f"'{csv_name}' vs '{row['yahoo_long_name']}'")
        if row["currency"] and expected and row["currency"] != expected:
            flags.append("currency_mismatch")
            notes.append(f"{row['currency']} != {expected}")
        cap = usd_value(info.get("marketCap"), row["currency"] or expected, rates)
        if cap is None:
            notes.append("market cap unavailable")
        else:
            row["market_cap_usd"] = round(cap)
            if cap < min_cap_usd:
                flags.append("under_20b")
                notes.append(f"market cap {cap / 1e9:.1f}B USD")

    if not bars or not bars.get("count"):
        flags.append("no_bars")
    else:
        row.update(first_bar=bars["first"], last_bar=bars["last"], bar_count=bars["count"])
        age = trading_days_old(bars["last"], today)
        if age > max_stale:
            flags.append("stale")
            notes.append(f"last bar {age} trading days old")

    if normalize_name(csv_name) in dup_names:
        flags.append("duplicate_name")

    row["status"] = ";".join(dict.fromkeys(flags)) or "ok"
    row["detail"] = "; ".join(notes)
    return row


def duplicate_names(universe: list[dict]) -> set[str]:
    seen: dict[str, int] = {}
    for r in universe:
        k = normalize_name(r["name"])
        seen[k] = seen.get(k, 0) + 1
    return {k for k, n in seen.items() if n > 1}


# ---- network layer (not exercised offline) ------------------------------------------------------------------

def yahoo_bars(tickers: list[str]) -> dict[str, dict]:
    """One batched yf.download; returns {ticker: {first, last, count}} (missing tickers are absent)."""
    import yfinance as yf

    df = yf.download(tickers, period="5y", interval="1d", auto_adjust=True, group_by="ticker",
                     progress=False, threads=True)
    out: dict[str, dict] = {}
    for t in tickers:
        try:
            close = (df[t]["Close"] if hasattr(df.columns, "levels") else df["Close"]).dropna()
        except (KeyError, TypeError):
            continue
        if len(close):
            out[t] = {"first": close.index[0].date(), "last": close.index[-1].date(), "count": int(len(close))}
    return out


def yahoo_info(ticker: str, retries: int = 3, sleep: float = 2.0) -> dict | None:
    import yfinance as yf

    for i in range(retries):
        try:
            info = yf.Ticker(ticker).info
            if info and (info.get("quoteType") or info.get("longName")):
                return info
        except Exception:
            pass
        time.sleep(sleep * (2 ** i))
    return None


# ---- driver --------------------------------------------------------------------------------------------------

def read_universe(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [{"ticker": r["ticker"].strip(), "name": (r.get("name") or r["ticker"]).strip()} for r in csv.DictReader(fh)]


def read_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["ticker"] for r in csv.DictReader(fh) if r.get("status") and r["status"] != "fetch_error"}


def run(universe_path: Path, out_path: Path, *, tickers: list[str] | None = None, limit: int | None = None,
        batch: int = 50, sleep: float = 2.0, min_cap_usd: float = 20e9, today: date | None = None,
        bars_fn: Callable[[list[str]], dict] | None = None, info_fn: Callable[[str], dict | None] | None = None,
        fx_last: Callable[[str], float | None] | None = None) -> int:
    today = today or date.today()
    bars_fn = bars_fn or yahoo_bars
    info_fn = info_fn or (lambda t: yahoo_info(t, sleep=sleep))
    universe = read_universe(universe_path)
    dups = duplicate_names(universe)
    todo = [r for r in universe if not tickers or r["ticker"] in tickers]
    done = read_done(out_path)
    todo = [r for r in todo if r["ticker"] not in done]
    if limit:
        todo = todo[:limit]
    rates = fetch_fx_to_usd(set(SUFFIX_CURRENCY.values()), fx_last)

    keep: list[dict] = []
    if out_path.exists():  # keep finished rows, drop fetch_error rows that are being retried
        with out_path.open(encoding="utf-8", newline="") as fh:
            keep = [r for r in csv.DictReader(fh) if r["ticker"] in done]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(keep)
        fh.flush()
        errors = 0
        for i in range(0, len(todo), batch):
            chunk = todo[i:i + batch]
            try:
                bars = bars_fn([r["ticker"] for r in chunk])
            except Exception as e:  # whole batch failed: rows still get an info attempt
                print(f"batch download failed: {e}", file=sys.stderr)
                bars = {}
            for r in chunk:
                t = r["ticker"]
                info = info_fn(t)
                b = bars.get(t)
                row = classify_row(t, r["name"], info, b if b else ({} if info is not None else None), today,
                                   rates=rates, dup_names=dups, min_cap_usd=min_cap_usd)
                row["verified_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if row["status"] == "fetch_error":
                    errors += 1
                w.writerow(row)
                fh.flush()
                print(f"{t:<14} {row['status']}")
            if sleep and i + batch < len(todo):
                time.sleep(sleep)
    if todo and errors > len(todo) / 2:
        print(f"network failed for {errors} of {len(todo)} tickers", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--universe", type=Path, default=ROOT / "config" / "universe.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "config" / "universe_verified.csv")
    ap.add_argument("--tickers", help="comma-separated subset")
    ap.add_argument("--limit", type=int, help="check only the first N pending tickers")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between batches and retry base")
    ap.add_argument("--min-cap-usd", type=float, default=20e9)
    a = ap.parse_args(argv)
    return run(a.universe, a.out, tickers=a.tickers.split(",") if a.tickers else None, limit=a.limit,
               batch=a.batch, sleep=a.sleep, min_cap_usd=a.min_cap_usd)


if __name__ == "__main__":
    raise SystemExit(main())
