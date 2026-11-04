"""Cheap pre-registered experiment: does any price-only dip feature rank-correlate with the 21-day forward return out of sample?

Everything here is a pure function. Rules: .claude/skills/backtest-hygiene. Features at signal day t use only bars <= t (tested by
truncation: cutting the data at t must not change the feature at t). The target is the event's forward return minus the same-day
mean forward return of all stocks in the universe. In-sample events only fix the SIGN of each feature (and the tercile cut points);
the out-of-sample events are the one test. Costs do not enter a rank correlation, so none are applied.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm, rankdata

FEATURES: dict[str, str] = {
    "f1_volume_ratio": "log(V_t / median(V over the previous 20 bars))",
    "f2_mom_12_1": "close(t-21) / close(t-252) - 1",
    "f3_volscaled_drop": "r_1d(t) / std(daily returns over the previous 60 bars, excluding t)",
    "f4_days_since_high": "trading bars since the highest close of the last 252 bars (0 = high is today)",
    "f5_realised_vol": "std(daily returns over the previous 60 bars, excluding t) * sqrt(252)",
    "f6_dd_52w": "close(t) / max(close over the last 252 bars) - 1 (<= 0)",
}
FAMILY = list(FEATURES)
ALPHA = 0.10                       # family-wise level, two-sided; matches the project's 90% intervals
MIN_N = 30


# ---------------------------------------------------------------- features (causal)
def _bars_since_max(a: np.ndarray) -> float:
    return float(np.argmax(a[::-1]))              # most recent maximum wins ties


def compute_features(close: pd.Series, volume: pd.Series | None) -> pd.DataFrame:
    """The six features for every bar, from trailing windows only (every shift is >= 0, every window ends at t).
    close/volume share an index of consecutive trading bars. NaN where the window is not full."""
    c = close.astype(float)
    r = c / c.shift(1) - 1
    prior_sd = r.shift(1).rolling(60).std()                           # returns t-60 .. t-1, t excluded
    out = pd.DataFrame(index=c.index)
    if volume is None:
        out["f1_volume_ratio"] = np.nan
    else:
        v = volume.reindex(c.index).astype(float)
        med = v.shift(1).rolling(20).median()
        out["f1_volume_ratio"] = np.log(v / med).where((v > 0) & (med > 0))
    out["f2_mom_12_1"] = c.shift(21) / c.shift(252) - 1
    out["f3_volscaled_drop"] = (r / prior_sd).where(prior_sd > 0)
    out["f4_days_since_high"] = c.rolling(252).apply(_bars_since_max, raw=True)
    out["f5_realised_vol"] = prior_sd * np.sqrt(252)
    out["f6_dd_52w"] = c / c.rolling(252).max() - 1
    return out


def demeaned_target(days: pd.DataFrame, h: int) -> pd.Series:
    """fwd{h} minus the mean fwd{h} of ALL stocks in `days` on the same signal date (the event's own stock is part of that mean)."""
    f = days[f"fwd{h}"]
    return f - f.groupby(days["date"]).transform("mean")


# ---------------------------------------------------------------- statistics
def spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return np.nan
    rx, ry = rankdata(x), rankdata(y)
    sx, sy = rx.std(), ry.std()
    if sx == 0 or sy == 0:
        return np.nan
    return float(((rx - rx.mean()) * (ry - ry.mean())).mean() / (sx * sy))


def month_bootstrap(stat_fn, arrays: list[np.ndarray], months: np.ndarray, draws: int, level: float, seed: int) -> dict:
    """Percentile interval of stat_fn(*arrays) from resampling whole calendar months with replacement (same scheme as
    backtest.cluster_bootstrap, which only handles means). p is two-sided: twice the smaller tail share beyond zero, +1 smoothing."""
    ok = np.ones(len(months), dtype=bool)
    for a in arrays:
        ok &= ~np.isnan(a)
    arrays = [a[ok] for a in arrays]
    months = np.asarray(months)[ok]
    est = stat_fn(*arrays) if len(months) else np.nan
    labels, inv = np.unique(months, return_inverse=True)
    if len(labels) < 2 or not np.isfinite(est):
        return {"est": est, "lo": np.nan, "hi": np.nan, "p": np.nan, "n": int(ok.sum()), "n_months": len(labels)}
    groups = [np.flatnonzero(inv == k) for k in range(len(labels))]
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(labels), size=(draws, len(labels)))
    boots = np.empty(draws)
    for d in range(draws):
        idx = np.concatenate([groups[k] for k in pick[d]])
        boots[d] = stat_fn(*[a[idx] for a in arrays])
    boots = boots[np.isfinite(boots)]
    a_ = (1 - level) / 2
    lo, hi = np.quantile(boots, [a_, 1 - a_])
    p = min(1.0, 2 * min((1 + (boots <= 0).sum()) / (len(boots) + 1), (1 + (boots >= 0).sum()) / (len(boots) + 1)))
    return {"est": float(est), "lo": float(lo), "hi": float(hi), "p": float(p), "n": int(ok.sum()), "n_months": len(labels)}


def holm(p: list[float], alpha: float = ALPHA) -> tuple[np.ndarray, np.ndarray]:
    """Holm step-down adjusted p-values and reject flags. Sort ascending; adjusted_(i) = running max of min(1, (m - i + 1) * p_(i));
    map back to the input order; reject where adjusted <= alpha. Matches statsmodels' method='holm' (checked in the tests)."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    if m == 0:
        return np.zeros(0, dtype=bool), np.zeros(0)
    order = np.argsort(p, kind="stable")
    stepped = np.minimum(1.0, (m - np.arange(m)) * p[order])
    adj = np.empty(m)
    adj[order] = np.maximum.accumulate(stepped)
    return adj <= alpha, adj


def mde(lo: float, hi: float, level: float = 0.90, alpha: float = ALPHA, power: float = 0.80) -> float:
    """Smallest true effect (same units as the interval) detected with `power` at two-sided `alpha`, treating the
    bootstrap interval as a normal one: SE = width / (2 z_level); MDE = (z_{1-alpha/2} + z_power) * SE."""
    se = (hi - lo) / (2 * norm.ppf(0.5 + level / 2))
    return float((norm.ppf(1 - alpha / 2) + norm.ppf(power)) * se)


def tercile_edges(x_in_sample: np.ndarray) -> tuple[float, float]:
    q = np.nanquantile(x_in_sample, [1 / 3, 2 / 3])
    return float(q[0]), float(q[1])


def _top_minus_bottom(x: np.ndarray, y: np.ndarray, e1: float, e2: float) -> float:
    top, bot = y[x > e2], y[x <= e1]
    return float(top.mean() - bot.mean()) if len(top) and len(bot) else np.nan


def _split(ev: pd.DataFrame, group: str) -> pd.DataFrame:
    return ev if group == "All" else ev[ev["group"] == group]


# ---------------------------------------------------------------- the evaluation
@dataclass
class Settings:
    draws: int = 5000
    level: float = 0.90
    seed: int = 1
    alpha: float = ALPHA


def evaluate_features(ev: pd.DataFrame, cfg: Settings, features: list[str] = FAMILY) -> pd.DataFrame:
    """ev needs: period ('IS'/'OOS'; purged events already removed), month, group, target and the feature columns.
    Returns one row per (feature, group, period). Holm and the verdict apply to the pooled out-of-sample family only."""
    rows = []
    for k, f in enumerate(features):
        ins = ev[ev["period"] == "IS"]
        ok_in = ins[f].notna() & ins["target"].notna()
        sign = np.sign(spearman(ins.loc[ok_in, f].to_numpy(float), ins.loc[ok_in, "target"].to_numpy(float)))
        edges = tercile_edges(ins.loc[ok_in, f].to_numpy(float))
        rows.append({"feature": f, "group": "All", "period": "IS", "stat": "spearman", "n": int(ok_in.sum()),
                     "est": spearman(ins.loc[ok_in, f].to_numpy(float), ins.loc[ok_in, "target"].to_numpy(float)),
                     "lo": np.nan, "hi": np.nan, "p": np.nan, "n_months": ins.loc[ok_in, "month"].nunique(),
                     "sign_is": sign, "edge1": edges[0], "edge2": edges[1]})
        oos = ev[ev["period"] == "OOS"]
        for g in ("All", "US", "Europe+Nordic"):
            sub = _split(oos, g)
            x, y, m = sub[f].to_numpy(float), sub["target"].to_numpy(float), sub["month"].to_numpy()
            seed = cfg.seed + 100 * k
            res = month_bootstrap(spearman, [x, y], m, cfg.draws, cfg.level, seed)
            rows.append({"feature": f, "group": g, "period": "OOS", "stat": "spearman", **res, "sign_is": sign,
                         "edge1": edges[0], "edge2": edges[1]})
            res = month_bootstrap(lambda a, b: _top_minus_bottom(a, b, *edges), [x, y], m, cfg.draws, cfg.level, seed + 1)
            rows.append({"feature": f, "group": g, "period": "OOS", "stat": "tercile_top_minus_bottom", **res, "sign_is": sign,
                         "edge1": edges[0], "edge2": edges[1]})
    out = pd.DataFrame(rows)
    out["p_holm"], out["holm_reject"], out["supported"], out["mde_80"] = np.nan, False, False, np.nan
    fam = (out["stat"] == "spearman") & (out["period"] == "OOS") & (out["group"] == "All")
    idx = out.index[fam]
    pvals = out.loc[idx, "p"].fillna(1.0).to_numpy()
    rej, adj = holm(list(pvals), cfg.alpha)
    out.loc[idx, "p_holm"], out.loc[idx, "holm_reject"] = adj, rej
    same_sign = np.sign(out.loc[idx, "est"].to_numpy()) == out.loc[idx, "sign_is"].to_numpy()
    enough = out.loc[idx, "n"].to_numpy() >= MIN_N
    out.loc[idx, "supported"] = rej & same_sign & enough
    has = out["lo"].notna()
    out.loc[has, "mde_80"] = [mde(a, b, cfg.level, cfg.alpha) for a, b in zip(out.loc[has, "lo"], out.loc[has, "hi"])]
    return out


# ---------------------------------------------------------------- spec
def spec_hash(spec: dict) -> str:
    notes = {"notes"}
    return hashlib.sha256(json.dumps({k: v for k, v in spec.items() if k not in notes}, sort_keys=True, default=str).encode()).hexdigest()[:16]


def freeze_spec(parent: dict, cutoff: str, n_universe: int, family_id: str, boot: dict) -> dict:
    """Pre-registration. Built from inputs only (dates, settings, definitions); no return enters it."""
    spec = {
        "family_id": family_id,
        "parent_backtest_spec": parent,
        "events": "V1 price-only dip events of the existing backtest (same rule, 21-bar cooldown, zero-volume bars removed, 252-bar warm-up), horizon 21, entry next close",
        "features": FEATURES,
        "feature_timing": "every feature at signal day t uses bars <= t only (trailing windows; tested by truncation)",
        "target": "fwd21 (entry next close, exit 21 bars later) minus the mean fwd21 of ALL stocks in the universe on the same signal date",
        "statistic": "Spearman rank correlation between feature and target, pooled over events",
        "split": {"oos_fraction": 0.4, "cutoff_last_in_sample_date": cutoff, "purge": "in-sample events whose exit is after the cutoff are dropped"},
        "in_sample_use": "ONLY to fix the sign of each feature (sign of in-sample rho) and the tercile cut points; nothing else is frozen or tuned",
        "out_of_sample": "the one test: last 40% of trading dates",
        "family": {"size": len(FAMILY), "members": FAMILY, "test": "OOS pooled (All regions) Spearman rho",
                   "p_value": "two-sided, from the month-clustered bootstrap (twice the smaller tail share beyond zero, +1 smoothing)",
                   "correction": "Holm step-down across the 6", "alpha_family": ALPHA},
        "uncertainty": boot,
        "sign_convention": "sign_is = sign of in-sample rho. A positive rho means a higher feature value goes with a higher target (a better 21d return than the day's universe mean).",
        "supported_means": ("ALL of: Holm-adjusted two-sided p <= 0.10 across the 6; OOS rho has the same sign as in-sample rho; at least 30 OOS events. "
                            "'Supported' is a statement about a rank correlation in this sample only, not about tradability, costs or the future."),
        "secondary_descriptive": ["top-minus-bottom tercile difference (cut points from in-sample events only)", "US vs Europe+Nordic split (EXPLORATORY)",
                                  "minimum detectable effect (80% power, two-sided 10%, from the interval width)"],
        "not_done": "no variants beyond these six features; no tuning after seeing results; no costs (a rank correlation has none); no fundamentals",
        "universe": {"n": n_universe, "bias": "current constituents only: survivorship bias"},
        "notes": "events cluster in market-wide selloffs; months are the resampling unit; the date-demeaned target removes market and period effects only",
    }
    spec["spec_hash"] = spec_hash(spec)
    return spec
