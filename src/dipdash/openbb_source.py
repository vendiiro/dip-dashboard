"""OpenBB 5.0.0 as a second price source (raw, unadjusted closes). Imported lazily: OpenBB is slow to load.

Verified 2026-11-02 (docs/m2-data-verification.md): `nasdaq` serves US stocks, `nasdaq.nordic` serves Helsinki,
Stockholm and Copenhagen. Nothing in the default bundle serves Amsterdam, Xetra, Paris, Swiss or Oslo lines.
"""
from __future__ import annotations

import pandas as pd

from .exchanges import EXCHANGES, exchange_for

NORDIC_SUFFIXES = tuple(s for s, e in EXCHANGES.items() if e.openbb == "nasdaq_nordic")   # derived: (".ST", ".HE", ".CO")


def source_for(ticker: str) -> str | None:
    """Which OpenBB provider can serve this Yahoo-style ticker, or None."""
    ex = exchange_for(ticker)   # no dot = US line, including share classes written like BRK-B
    return ex.openbb if ex else None


def nordic_symbol(ticker: str) -> str:
    """Yahoo 'ERIC-B.ST' -> Nasdaq Nordic 'ERIC B'."""
    return ticker.rsplit(".", 1)[0].replace("-", " ")


def us_symbol(ticker: str) -> str:
    return ticker.replace("-", ".")


_obb = None


def _client():
    global _obb
    if _obb is None:
        from openbb import obb
        _obb = obb
    return _obb


def fetch_bars(ticker: str, start: str, end: str) -> tuple[pd.Series, pd.Series | None] | None:
    """(close, volume) between two ISO dates, or None if the provider has no data or the call fails."""
    src = source_for(ticker)
    if src is None:
        return None
    try:
        obb = _client()
        if src == "nasdaq":
            df = obb.nasdaq.equity.historical(symbol=us_symbol(ticker), start_date=start, end_date=end).to_df()
        else:
            df = obb.nasdaq.nordic.historical(symbol=nordic_symbol(ticker), start_date=start, end_date=end).to_df()
    except Exception:
        return None
    if df is None or df.empty or "close" not in df:
        return None
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    vol = df["volume"].astype(float) if "volume" in df else None
    return df["close"].astype(float), vol
