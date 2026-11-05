"""Market-model residual move: how much of a stock's recent move is NOT explained by its own market index.

Descriptive only. It says how unusual the move is relative to what the index did, given the stock's past
sensitivity. It is not a forecast, and nothing here has been backtested (see docs/decisions.md).

Method (pure numpy/pandas, no new dependencies)
- Stock and index closes are inner-joined on common dates, then daily returns are taken on that common grid, so a
  date missing on one side becomes a multi-day return on both (never a misaligned pair).
- The index is only used up to the stock's own last bar (the join cannot see later index bars). If the index has no
  bar on the stock's last date the result is None: a stock bar one day behind is compared with the index move ending
  on the STOCK's date, never with a later index move.
- Estimation window: the last `window` (252) daily returns BEFORE the most recent `exclude` (5) returns. The 5
  excluded returns are exactly the 5-day move being measured, so the drop cannot leak into beta or the residual
  volatility. Needs at least `min_obs` (120) returns, else None (no guess).
- beta = cov(rs, ri) / var(ri) (OLS slope with intercept). Zero index variance -> None.
- beta is clipped to [0, 3] for the residual (flag `beta_clipped`, unclipped value in `beta_raw`): a blue-chip
  with a negative or >3 estimated beta is far more likely to be estimation noise than a real exposure.
- No winsorizing: a large daily move is real information for a dip screener, and a data error is the job of
  validate.py. Cost: one extreme day in the window can shift beta; check `beta_raw` against the clip.
- residual_h = stock h-day return - beta * index h-day return (h = 1, 5). Intercept (alpha) is NOT subtracted: a daily
  alpha of a few basis points is below its own estimation noise.
- res5z = res5 / (sd_resid * sqrt(5)), sd_resid = sample std (ddof=1) of the daily residuals rs - beta*ri in the
  estimation window. sqrt(h) scaling assumes uncorrelated daily residuals and ignores fat tails, so treat z as a
  ranking aid, not a p-value.
- "vs index" means this residual: the stock's move minus beta times the index move over the same dates. It is never
  a raw comparison of the stock with the index.
- beta_se = standard error of the OLS slope (unclipped fit with intercept, estimation window), rounded to 3 places.
  market_adjusted is True only if the residual is computed with an unclipped beta and beta_se <= 0.25
  (BETA_SE_UNCERTAIN). The 0.25 threshold is a judgement call, not tested on returns: at 0.25 the 95% interval
  for beta is about 1.0 wide.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import clean

WINDOW = 252
EXCLUDE = 5
MIN_OBS = 120
BETA_CLIP = (0.0, 3.0)

BETA_SE_UNCERTAIN = 0.25

_NONE = {"res1": None, "res5": None, "res5z": None, "beta": None, "beta_raw": None, "beta_clipped": False,
         "beta_se": None, "market_adjusted": False, "n_obs": 0, "asof": None}


def _fail(reason: str, **extra) -> dict:
    return {**_NONE, **extra, "reason": reason}


def _day_index(idx) -> pd.DatetimeIndex:
    """Calendar dates as naive midnight timestamps (Yahoo returns exchange-local, sometimes tz-aware, stamps)."""
    d = pd.DatetimeIndex(idx)
    return (d.tz_localize(None) if d.tz is not None else d).normalize()


def slope_se(x, y, slope: float) -> float:
    """Standard error of the OLS slope in y = a + slope*x (intercept fitted, residuals unclipped). Unrounded."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    intercept = float(y.mean() - slope * x.mean())
    e = y - intercept - slope * x
    sxx = float(np.sum((x - x.mean()) ** 2))
    return float(np.sqrt(np.sum(e ** 2) / (len(x) - 2) / sxx))


def residual_move(stock_close: pd.Series, index_close: pd.Series, *, window: int = WINDOW, exclude: int = EXCLUDE,
                  min_obs: int = MIN_OBS, beta_clip: tuple[float, float] = BETA_CLIP) -> dict:
    """Keys: res1, res5 (fractions), res5z, beta (clipped), beta_raw, beta_clipped, n_obs, asof, reason (None if ok).
    On any failure all numeric outputs are None and `reason` says why."""
    s = stock_close.dropna()
    i = index_close.dropna()
    if len(s) == 0 or len(i) == 0:
        return _fail("no price data for the stock or its index")
    s.index = _day_index(s.index)
    i.index = _day_index(i.index)
    s = s[~s.index.duplicated(keep="last")].sort_index()      # a duplicated or unsorted date (a known Yahoo quirk) must not abort the run
    i = i[~i.index.duplicated(keep="last")].sort_index()
    last = s.index[-1]
    if last not in i.index:
        return _fail(f"index has no bar on the stock's last bar {last.date()}")
    both = pd.concat({"s": s, "i": i}, axis=1, join="inner").loc[:last]
    r = both.pct_change().dropna()
    est = r.iloc[:-exclude].tail(window)
    if len(est) < min_obs or len(both) <= 5:
        return _fail(f"too little overlapping history ({len(est)} usable returns, need {min_obs})", n_obs=len(est))
    var_i = float(est["i"].var(ddof=1))
    if not np.isfinite(var_i) or var_i < 1e-12:
        return _fail("index has no variance in the estimation window", n_obs=len(est))
    raw = float(est["s"].cov(est["i"]) / var_i)
    beta = min(max(raw, beta_clip[0]), beta_clip[1])
    sd = float((est["s"] - beta * est["i"]).std(ddof=1))
    se = slope_se(est["i"].to_numpy(), est["s"].to_numpy(), raw)

    def move(h: int) -> float:
        return float(both["s"].iloc[-1] / both["s"].iloc[-1 - h] - 1) - beta * float(both["i"].iloc[-1] / both["i"].iloc[-1 - h] - 1)

    res1, res5 = move(1), move(5)
    z = res5 / (sd * np.sqrt(5)) if sd > 0 else None
    clipped = bool(beta != raw)
    adjusted = z is not None and not clipped and se <= BETA_SE_UNCERTAIN
    return {"res1": clean(res1), "res5": clean(res5), "res5z": clean(z, 2) if z is not None else None,
            "beta": clean(beta, 3), "beta_raw": clean(raw, 3), "beta_clipped": clipped,
            "beta_se": clean(se, 3), "market_adjusted": adjusted,
            "beta_side": ("floor" if raw < beta_clip[0] else "cap") if beta != raw else None, "n_obs": len(est),
            "asof": str(last.date()), "reason": None if z is not None else "residual volatility is zero"}
