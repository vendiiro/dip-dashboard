"""Price metrics from daily adjusted closes. Pure functions, no network."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

MIN_BARS = 60


def rsi14(c: pd.Series) -> float:
    """Wilder RSI(14) of the last bar. NaN if too short or the price never moved."""
    d = c.diff().dropna()
    if len(d) < 15:
        return float("nan")
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    if up == 0 and dn == 0:
        return float("nan")
    if dn == 0:
        return 100.0
    return float(100 - 100 / (1 + up / dn))


def clean(x, nd: int = 4):
    """Round to nd places; None for missing, NaN or infinite values (keeps the JSON valid)."""
    if x is None:
        return None
    try:
        if isinstance(x, (float, np.floating)) and (math.isnan(x) or math.isinf(x)):
            return None
    except TypeError:
        return None
    return round(float(x), nd)


def compute_metrics(close: pd.Series, volume: pd.Series | None) -> dict | None:
    """Return the metric dict for one stock, or None if there are fewer than MIN_BARS closes."""
    c = close.dropna()
    if len(c) < MIN_BARS:
        return None
    last = float(c.iloc[-1])

    def ret(n: int) -> float:
        return float(last / c.iloc[-1 - n] - 1) if len(c) > n else float("nan")

    r1, r5, r21 = ret(1), ret(5), ret(21)
    dd52 = last / float(c.iloc[-252:].max()) - 1
    dd20 = last / float(c.iloc[-20:].max()) - 1
    sma200 = c.rolling(200).mean()
    s_now = sma200.iloc[-1]
    s_prev = sma200.iloc[-21] if len(c) >= 221 else float("nan")
    vs200 = last / s_now - 1 if not math.isnan(s_now) else float("nan")
    s200_falling = (not math.isnan(s_prev)) and bool(s_now < s_prev)
    daily = c.pct_change().dropna()
    sd = float(daily.iloc[-63:].std())
    z5 = r5 / (sd * math.sqrt(5)) if sd > 0 else float("nan")
    volx = float("nan")
    if volume is not None:
        v = volume.dropna()
        if len(v) > 25 and v.iloc[-21:-1].mean() > 0:
            volx = float(v.iloc[-1] / v.iloc[-21:-1].mean())
    return {
        "price": clean(last, 2), "r1": clean(r1), "r5": clean(r5), "r21": clean(r21),
        "dd20": clean(dd20), "dd52": clean(dd52), "rsi": clean(rsi14(c), 1),
        "vs200": clean(vs200), "z5": clean(z5, 2), "volx": clean(volx, 2),
        "s200_falling": s200_falling, "spark": [round(float(x), 2) for x in c.iloc[-90:].tolist()],
        "asof": str(c.index[-1])[:10],
    }


def history(close: pd.Series, n: int = 252) -> dict:
    """Last n bars with the 200-day average and rolling 52-week high, for the detail chart.
    Values are None where the average or high cannot be computed yet."""
    c = close.dropna()
    sma = c.rolling(200).mean()
    hi = c.rolling(252, min_periods=60).max()

    def vals(s: pd.Series) -> list:
        return [None if pd.isna(v) else round(float(v), 2) for v in s.iloc[-n:]]

    return {"d": [str(x)[:10] for x in c.index[-n:]], "c": vals(c), "s": vals(sma), "h": vals(hi)}


def index_move(close: pd.Series) -> dict | None:
    """Latest level and 1-day / 5-day move of an index, or None with fewer than 6 bars."""
    c = close.dropna()
    if len(c) < 6:
        return None
    last = float(c.iloc[-1])
    return {"price": clean(last, 1), "r1": clean(last / float(c.iloc[-2]) - 1), "r5": clean(last / float(c.iloc[-6]) - 1),
            "asof": str(c.index[-1])[:10]}
