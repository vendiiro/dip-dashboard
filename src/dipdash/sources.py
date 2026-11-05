"""Typed contracts for every network source the live run uses, bundled into one `Sources` object.

`live_sources()` returns the real Yahoo/OpenBB functions; tests pass a fake bundle (tests/fakes.py) instead, so the
live branch can run offline. This module imports no network library, and `live_sources()` only imports modules that
themselves load yfinance/OpenBB lazily, inside the functions that need them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import pandas as pd

Bars = tuple[pd.Series, "pd.Series | None"]          # (close, volume), indexed by date


class PriceSource(Protocol):
    """Batch pull of adjusted daily bars. Tickers it cannot serve are omitted or returned empty / all-NaN."""
    def __call__(self, tickers: list[str]) -> dict[str, Bars]: ...


class FundamentalsSource(Protocol):
    """{ticker: {FUND_KEYS...}} for every ticker asked for (an empty dict when nothing is known), cached at cache_path."""
    def __call__(self, tickers: list[str], cache_path: Path) -> dict: ...


class FxSource(Protocol):
    """Last close of a Yahoo FX pair such as "SEKUSD=X", or None when the pair cannot be fetched."""
    def __call__(self, symbol: str) -> float | None: ...


class IndexSource(Protocol):
    """About 2 years of daily closes for an index symbol such as "^GSPC", or None."""
    def __call__(self, symbol: str) -> pd.Series | None: ...


FallbackBars = Callable[[str, str, str], "Bars | None"]          # (ticker, start ISO, end ISO) -> unadjusted bars or None
EarningsFetch = Callable[[str], dict]                           # ticker -> {"rows": [...], "cal": [...]}; may raise
NewsFetch = Callable[[str], list[dict]]                         # ticker -> [{title, src, url}]
RawCloses = Callable[[str, str, str], "pd.Series | None"]       # (ticker, start, end) -> closes without dividend adjustment


@dataclass(frozen=True)
class Sources:
    """Everything the live branch of cli.main fetches from the network, as one injectable bundle.

    How main wires it: pull_prices(tickers, prices, lambda t: fallback_bars(t, start, end)); fundamentals(tickers, path);
    fetch_fx_to_usd(ccys, fetch_last=fx); fetch_indices(specs, fetch_close=index); load_earnings(..., fetch=earnings);
    build_payload(news_fn=news); the cross-check uses raw_closes as its reference series.
    """
    prices: PriceSource
    fallback_bars: FallbackBars
    fundamentals: FundamentalsSource
    fx: FxSource
    index: IndexSource
    earnings: EarningsFetch
    news: NewsFetch
    raw_closes: RawCloses
    name: str = "live"                      # shown in logs; fakes use "fake"


def live_sources() -> Sources:
    """The real network functions (Yahoo first, OpenBB fallback). Calling this does not import yfinance or OpenBB."""
    from . import data, earnings, fx, openbb_source

    return Sources(
        prices=data.fetch_prices,
        fallback_bars=openbb_source.fetch_bars,
        fundamentals=data.fetch_fundamentals,
        fx=fx._yahoo_last_close,
        index=data._yahoo_index_close,
        earnings=earnings.fetch_yfinance,
        news=data.fetch_news,
        raw_closes=data.fetch_raw_closes,
    )
