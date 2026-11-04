"""Currency conversion to USD for size thresholds. Rates come from Yahoo FX pairs (e.g. SEKUSD=X)."""
from __future__ import annotations

from typing import Callable, Iterable

PENCE = {"GBp", "GBX"}


def usd_value(amount, ccy: str | None, rates: dict[str, float]) -> float | None:
    """Convert amount in ccy to USD; None if the amount, currency or rate is unusable."""
    try:
        x = float(amount)
    except (TypeError, ValueError):
        return None
    if not ccy or x != x:
        return None
    if ccy == "USD":
        return x
    if ccy in PENCE:
        r = rates.get("GBP")
        return x / 100 * r if r else None
    r = rates.get(ccy)
    return x * r if r else None


def fetch_fx_to_usd(ccys: Iterable[str | None], fetch_last: Callable[[str], float | None] | None = None) -> dict[str, float]:
    """USD per 1 unit of each currency. Currencies whose rate cannot be fetched are omitted."""
    want = {("GBP" if c in PENCE else c) for c in ccys if c and c != "USD"}
    fetch_last = fetch_last or _yahoo_last_close
    out: dict[str, float] = {}
    for c in sorted(want):
        r = fetch_last(f"{c}USD=X")
        if r and r > 0:
            out[c] = float(r)
    return out


def _yahoo_last_close(symbol: str) -> float | None:
    import yfinance as yf

    try:
        h = yf.Ticker(symbol).history(period="5d")
        return float(h["Close"].dropna().iloc[-1])
    except Exception:
        return None
