"""Synthetic price series with known properties (no network, no randomness)."""
import pandas as pd

END = "2026-10-29"  # a Thursday


def dates(n: int, end: str = END) -> pd.DatetimeIndex:
    return pd.bdate_range(end=end, periods=n)


def geometric(n: int, daily: float, start: float = 100.0, end: str = END) -> pd.Series:
    """close_i = start * (1 + daily) ** i; falling for daily < 0, rising for daily > 0."""
    return pd.Series([start * (1 + daily) ** i for i in range(n)], index=dates(n, end))


def flat(n: int, value: float = 100.0, end: str = END) -> pd.Series:
    return pd.Series([value] * n, index=dates(n, end))


def volume(n: int, base: float = 100.0, last: float | None = None, end: str = END) -> pd.Series:
    v = pd.Series([base] * n, index=dates(n, end))
    if last is not None:
        v.iloc[-1] = last
    return v


def slide(n: int = 260, days: int = 5, daily: float = -0.02, end: str = END) -> pd.Series:
    """Gently rising, then `days` straight daily falls: a 5-day drop of about 9.6% at -2%/day."""
    c = geometric(n, 0.0005, end=end)
    for i in range(1, days + 1):
        c.iloc[-days + i - 1] = c.iloc[-days - 1] * (1 + daily) ** i
    return c
