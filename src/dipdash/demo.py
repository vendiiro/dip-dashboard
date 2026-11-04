"""Synthetic inputs for --demo (no network). Not market data."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Stock
from .validate import expected_currency


def _last_close() -> pd.Timestamp:
    """The previous business day: demo bars look like a run made after the close, so no bar is dated today."""
    return pd.Timestamp.today().normalize() - pd.offsets.BDay(1)


def demo_inputs(universe: list[Stock]):
    rng = np.random.default_rng(7)
    idx = pd.bdate_range(end=_last_close(), periods=460)
    prices, funds = {}, {}
    for i, s in enumerate(universe):
        r = rng.normal(0.0004, 0.014, len(idx))
        if i % 6 == 0:
            r[-5:] = rng.normal(-0.018, 0.006, 5)         # a recent sharp slide
        if i % 11 == 0:
            r[-120:-20] = rng.normal(-0.004, 0.012, 100)  # long downtrend (falling-knife shape)
        close = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
        vol = pd.Series(rng.integers(1_000_000, 5_000_000, len(idx)).astype(float), index=idx)
        if i % 6 == 0:
            vol.iloc[-1] *= 3
        prices[s.ticker] = (close, vol)
        good = i % 3 != 2
        funds[s.ticker] = {
            "returnOnEquity": 0.22 if good else 0.04, "profitMargins": 0.18 if good else 0.03,
            "debtToEquity": 60 if good else 220, "freeCashflow": 1e9 if good else -2e8,
            "revenueGrowth": 0.06 if good else -0.02, "marketCap": 1e11, "forwardPE": 18 + i % 9,
            "trailingPE": 22 + i % 7, "currency": expected_currency(s.ticker) or "USD",
        }
    return prices, funds


def demo_news(_ticker: str) -> list[dict]:
    return [{"title": "DEMO: placeholder headline (live mode fetches real news)", "src": "demo", "url": ""}]


def demo_indices(specs) -> list[dict]:
    """Made-up index moves so the demo shows the market-context tile."""
    moves = {"US": (-0.0042, -0.0113), "Europe": (-0.0068, -0.0181), "Nordic": (-0.0051, -0.0229)}
    asof = str(_last_close().date())
    return [{"symbol": s.symbol, "name": s.name, "region": s.region, "price": None,
             "r1": moves.get(s.region, (0.0, 0.0))[0], "r5": moves.get(s.region, (0.0, 0.0))[1], "asof": asof} for s in specs]
