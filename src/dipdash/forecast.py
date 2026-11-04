"""Volatility-based 21-trading-day return RANGE per stock. Educational; not a price target, not a direction call.

What it is: from daily adjusted closes only, the 10th / 50th / 90th percentile of the next `horizon`-day return, so
80% of outcomes are expected inside [lo, hi] if the model is calibrated. What it is not: it says nothing about whether
the stock will rise or fall. Direction is NOT forecastable with ~80 independent out-of-sample months (see docs/decisions.md);
volatility is (it clusters), so only the SIZE of the move is modelled.

Method (primary, 'garch_t_fhs'): filtered historical simulation. GARCH(1,1) with Student-t innovations (package `arch`,
percent returns, zero conditional mean) is fitted on the trailing 750 daily log returns (minimum 400, else no forecast);
`arch` bootstraps the standardised residuals through the fitted variance recursion for 21 days; the 10/50/90% quantiles of the
simulated cumulative log returns form the range. DRIFT: the conditional mean is fixed at zero, so the median LOG return is about
zero (the bootstrapped residuals are mean-zero but negatively skewed, so the simulated median sits about +1% above zero). A neutral
assumption, not an estimate of expected return: daily drift (~0.03%) is far below its own estimation noise.
Baselines in the same module: 'ewma' (RiskMetrics lambda 0.94, normal quantiles) and 'naive' (trailing 60-day realised
volatility x sqrt(h), normal quantiles). If the GARCH fit fails or looks unstable, the result falls back to EWMA and
method = 'ewma_fallback'. No network, no files; every function takes pandas Series and only reads values up to the last date.

PRE-STATED SHIP CRITERION (written before any calibration result was seen; tested by scripts/run_forecast_calibration.py):
the range may be shown on the dashboard only if, on the out-of-sample period (last 40% of dates, nothing fitted on it),
 (a) overall empirical coverage of the 80% range is within 0.80 +/- 0.04, AND
 (b) coverage when the stock is in a dip state at the forecast origin (5-day return <= -7% or 1-day return <= -4%)
     is within 0.80 +/- 0.06.
Two attempts in total, no further tuning: attempt 1 = the raw model above; attempt 2 = ONE global scale factor k applied to the
log-range (lo, hi -> k*lo, k*hi) with k = the in-sample 80th percentile of the outcome-to-range ratio, fitted on in-sample
origins only, then re-tested once out of sample against the same criterion. If both fail, the range does not ship.
The criterion is judged on the point estimate (the intervals are reported, not used to relax it).
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy.stats import norm

MIN_OBS = 400
WINDOW = 750
EWMA_LAMBDA = 0.94
NAIVE_WINDOW = 60
SIMS = 1000
Q = (0.10, 0.50, 0.90)
TRADING_DAYS = 252


def _log_returns(close: pd.Series) -> pd.Series:
    c = pd.Series(close).astype(float)
    c = c[np.isfinite(c) & (c > 0)]
    return np.log(c).diff().dropna()


def _normal_quantiles(sigma_h: float) -> tuple[float, float, float]:
    return tuple(float(sigma_h * norm.ppf(q)) for q in Q)        # zero drift in log returns


def _ewma_vol(r: np.ndarray, lam: float = EWMA_LAMBDA) -> float:
    """Daily vol after the RiskMetrics recursion s2_t = lam*s2_{t-1} + (1-lam)*r_t^2 (one-step-ahead, held flat)."""
    s2 = float(np.var(r[:NAIVE_WINDOW]))
    for x in r:
        s2 = lam * s2 + (1 - lam) * x * x
    return float(np.sqrt(s2))


def _garch_fhs(r: np.ndarray, horizon: int, seed: int, sims: int = SIMS) -> tuple[tuple[float, float, float], float]:
    """GARCH(1,1)-t filtered historical simulation. Returns ((lo, mid, hi) cumulative log return, daily vol forecast).
    Raises RuntimeError when the fit does not converge or is not stationary."""
    from arch import arch_model
    pct = r * 100.0
    am = arch_model(pct, mean="Zero", vol="GARCH", p=1, q=1, dist="t", rescale=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = am.fit(disp="off", show_warning=False)
        if res.convergence_flag != 0:
            raise RuntimeError(f"GARCH did not converge (flag {res.convergence_flag})")
        p = res.params
        if not np.all(np.isfinite(p.values)) or p["alpha[1]"] + p["beta[1]"] >= 0.9999:
            raise RuntimeError("GARCH fit is not stationary")
        f = res.forecast(horizon=horizon, method="bootstrap", simulations=sims, reindex=False,
                         random_state=np.random.RandomState(seed))
    cum = f.simulations.values[-1].sum(axis=1) / 100.0
    lo, mid, hi = (float(x) for x in np.quantile(cum, Q))
    vol_d = float(np.sqrt(f.variance.values[-1].mean()) / 100.0)   # mean forecast variance per day (percent^2 -> fraction)
    if not np.isfinite([lo, mid, hi, vol_d]).all():
        raise RuntimeError("non-finite GARCH forecast")
    return (lo, mid, hi), vol_d


def _pack(q_log, vol_d: float, method: str, n_obs: int, asof: str) -> dict:
    lo, mid, hi = (float(np.expm1(x)) for x in q_log)
    return {"lo": lo, "mid": mid, "hi": hi, "vol_ann": float(vol_d * np.sqrt(TRADING_DAYS)),
            "method": method, "n_obs": n_obs, "asof": asof, "reason": None}


def _none(reason: str, n_obs: int, asof) -> dict:
    return {"lo": None, "mid": None, "hi": None, "vol_ann": None, "method": None, "n_obs": n_obs, "asof": asof, "reason": reason}


def all_ranges(close: pd.Series, horizon: int = 21, *, seed: int = 0) -> dict[str, dict]:
    """Every method on the same data: keys 'garch_t_fhs' (carries method 'ewma_fallback' and a fit_error if the fit failed),
    'ewma', 'naive'. Used by the calibration script; `range_forecast` returns the first entry."""
    r_all = _log_returns(close)
    asof = r_all.index[-1].date().isoformat() if len(r_all) else None
    if len(r_all) < MIN_OBS:
        none = _none(f"only {len(r_all)} daily returns; at least {MIN_OBS} are needed for a volatility model", len(r_all), asof)
        return {"garch_t_fhs": none, "ewma": none, "naive": none}
    r = r_all.to_numpy()[-WINDOW:]
    n, h = len(r), np.sqrt(horizon)
    ew = _ewma_vol(r)
    nv = float(np.std(r[-NAIVE_WINDOW:], ddof=1))
    ewma = _pack(_normal_quantiles(ew * h), ew, "ewma", n, asof)
    naive = _pack(_normal_quantiles(nv * h), nv, "naive", n, asof)
    try:
        q_log, vd = _garch_fhs(r, horizon, seed)
        g = _pack(q_log, vd, "garch_t_fhs", n, asof)
    except Exception as e:                                        # noqa: BLE001  any optimiser failure -> documented fallback
        g = dict(ewma, method="ewma_fallback", fit_error=str(e)[:120])
    return {"garch_t_fhs": g, "ewma": ewma, "naive": naive}


def range_forecast(close: pd.Series, horizon: int = 21, *, seed: int = 0) -> dict:
    """10/50/90% range of the next `horizon`-day simple return from daily adjusted closes (fractions, -0.09 = -9%).

    Keys: lo, mid, hi, vol_ann (forecast annualised volatility), method ('garch_t_fhs' | 'ewma_fallback'), n_obs (returns used),
    asof (ISO date of the last close used), reason (None if ok). With fewer than 400 returns every number is None and `reason`
    says why. A volatility range under a zero-drift assumption, not a price target."""
    d = dict(all_ranges(close, horizon, seed=seed)["garch_t_fhs"])
    d.pop("fit_error", None)
    return d


def range_label(d: dict) -> str:
    if not d or d.get("lo") is None:
        return ""
    return (f"Typical 21-day range (80% of outcomes in the historical-simulation model): {d['lo'] * 100:+.0f}% to {d['hi'] * 100:+.0f}%. "
            "Volatility range, not a price target.")
