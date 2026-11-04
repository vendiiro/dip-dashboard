"""Event-study backtest of the dip rules. Pure functions, no network. Rules: .claude/skills/backtest-hygiene.

Conventions (frozen in spec.json before any result is computed):
- A signal at the close of bar i uses only bars <= i. Entry is the NEXT close (bar i+1), exit is h bars after entry.
- One event per stock per cooldown window. Returns are dividend-adjusted closes in the stock's own currency.
- Baselines: (a) the same stock's non-dip days, (b) the regional index over the same dates, (c) the other stocks the same day,
  (d) a placebo: the same stock on random non-dip dates in the same year.
- Uncertainty: bootstrap that resamples calendar months, because events pile up in market-wide selloffs.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Settings, Stock

US, EU = "US", "Europe+Nordic"
VARIANTS = {
    "V1_price_only": "dip rule, price only (primary)",
    "V2_no_knife": "dip rule, falling knives removed (price only)",
    "V3_quality_indicative": "dip rule with today's quality score >= min (INDICATIVE: today's fundamentals leak into the past)",
}
PERIODS = ("ALL", "IS", "OOS", "OOS_exstress")
MAX_JUMP = 0.40


def group_of(region: str) -> str:
    return US if region == "US" else EU


# ---------------------------------------------------------------- signals
def signals(close: pd.Series, s: Settings) -> pd.DataFrame:
    """Daily dip / falling-knife flags from the close up to each bar. Matches metrics.py + screen.py bar for bar
    (same windows, same rounding to 4 decimals); tests compare the two."""
    c = close.dropna()
    r1 = (c / c.shift(1) - 1).round(4)
    r5 = (c / c.shift(5) - 1).round(4)
    dd20 = (c / c.rolling(20).max() - 1).round(4)
    dd52 = (c / c.rolling(252).max() - 1).round(4)
    sma = c.rolling(200).mean()
    sma_prev = sma.shift(20)
    vs200 = (c / sma - 1).round(4)
    falling = sma < sma_prev
    d, k = s.dip, s.falling_knife
    f1, f5, f20 = r1 <= -d.drop_1d, r5 <= -d.drop_5d, dd20 <= -d.drawdown_20d
    valid = dd52.notna() & sma_prev.notna()                  # a full 252-bar year of history and a 200-day average with its slope
    knife = (vs200 < 0) & (dd52 <= -k.drawdown_52w) & (falling if k.below_200d_falling else True)
    out = pd.DataFrame({"close": c, "r1": r1, "r5": r5, "dd20": dd20, "dd52": dd52, "vs200": vs200, "valid": valid,
                        "f1": f1 & valid, "f5": f5 & valid, "f20": f20 & valid,
                        "dip": (f1 | f5 | f20) & valid, "knife": knife & valid})
    return out


def apply_cooldown(flag: np.ndarray, cooldown: int) -> np.ndarray:
    """Keep a signal only if more than `cooldown` bars have passed since the last KEPT signal."""
    out = np.zeros(len(flag), dtype=bool)
    last = -10 ** 9
    for i in np.flatnonzero(flag):
        if i - last > cooldown:
            out[i] = True
            last = i
    return out


# ---------------------------------------------------------------- forward returns
def forward(close: pd.Series, horizons, lag: int = 1) -> pd.DataFrame:
    """For a signal at bar i: entry at bar i+lag, exit h bars after entry.
    fwd{h} = close[i+lag+h] / close[i+lag] - 1; mae{h} = worst drawdown from entry along the way (<= 0);
    exit{h} = date of the exit bar. NaN where the window runs past the end of the data."""
    c = close.dropna()
    entry = c.shift(-lag)
    dates = pd.Series(c.index, index=c.index)
    out = {"entry_date": dates.shift(-lag)}
    for h in horizons:
        out[f"fwd{h}"] = c.shift(-(lag + h)) / entry - 1
        path_min = c[::-1].rolling(h).min()[::-1].shift(-(lag + 1))      # min of closes at bars i+lag+1 .. i+lag+h
        out[f"mae{h}"] = np.minimum(0.0, path_min / entry - 1)
        out[f"exit{h}"] = dates.shift(-(lag + h))
    return pd.DataFrame(out)


def stress_flags(index_close: pd.Series, window: int, drawdown: float) -> pd.Series:
    """True on days the index closes at least `drawdown` below its trailing `window`-bar high (known at that close)."""
    c = index_close.dropna()
    return c <= (1 - drawdown) * c.rolling(window, min_periods=window).max()


def split_cutoff(dates, oos_fraction: float) -> pd.Timestamp:
    """Last in-sample date: the first (1 - oos_fraction) of the distinct trading dates are in-sample."""
    d = pd.DatetimeIndex(sorted(set(pd.to_datetime(list(dates)))))
    return d[int(len(d) * (1 - oos_fraction)) - 1]


# ---------------------------------------------------------------- day table
def _naive(c: pd.Series) -> pd.Series:
    """Index by calendar date: drop any time zone and time of day so stocks and indices line up by date."""
    c = c.copy()
    c.index = pd.DatetimeIndex(c.index).tz_localize(None).normalize()
    return c


def build_days(prices: dict, universe: list[Stock], index_close: dict[str, pd.Series], s: Settings,
               quality: dict[str, int | None] | None = None) -> pd.DataFrame:
    """One row per stock-day from settings.backtest.start_date, with signals, forward returns, index and stress info.
    prices: {ticker: close Series}; index_close: {US: Series, EU: Series}."""
    hs, bt = s.backtest.horizons, s.backtest
    start = pd.Timestamp(bt.start_date)
    stress = {g: stress_flags(_naive(c), bt.stress_window, bt.stress_drawdown) for g, c in index_close.items()}
    frames = []
    for st in universe:
        if st.ticker not in prices:
            continue
        sig = signals(prices[st.ticker], s)
        fw = forward(sig["close"], hs)
        df = sig.join(fw)
        g = group_of(st.region)
        ix = _naive(index_close[g].dropna()).reindex(df.index, method="ffill")       # index level on this stock's trading days
        ixf = forward(ix, hs)
        for h in hs:
            df[f"idx{h}"] = ixf[f"fwd{h}"]
        df["stress"] = stress[g].reindex(df.index, method="ffill").fillna(False).astype(bool)
        bm = (df["r1"].abs() > MAX_JUMP).astype(float)
        for h in hs:                                                           # a >40% one-day move anywhere in the signal-to-exit window
            df[f"suspect{h}"] = bm[::-1].rolling(h + 2, min_periods=1).max()[::-1].astype(bool)
        df["ticker"], df["region"], df["group"] = st.ticker, st.region, g
        df["q"] = (quality or {}).get(st.ticker)
        df["pos"] = np.arange(len(df))
        df.index.name = "date"
        frames.append(df)
    days = pd.concat(frames).reset_index()
    days = days[days["date"] >= start].sort_values(["ticker", "date"]).reset_index(drop=True)
    days["month"] = days["date"].dt.to_period("M").astype(str)
    days["year"] = days["date"].dt.year
    rows = days.index.to_series()
    days["tstart"] = rows.groupby(days["ticker"]).transform("min")      # first and one-past-last row of each stock (rows are in date order)
    days["tend"] = rows.groupby(days["ticker"]).transform("max") + 1
    return days


def add_events(days: pd.DataFrame, s: Settings) -> pd.DataFrame:
    """Add one boolean column per variant: True on the day that starts an event (signal, then cooldown per stock).
    Expects days sorted by (ticker, date), as build_days returns them."""
    flags = {"V1_price_only": days["dip"],
             "V2_no_knife": days["dip"] & ~days["knife"],
             "V3_quality_indicative": days["dip"] & (days["q"].fillna(-1) >= s.quality.min_score)}
    groups = days.groupby("ticker", sort=False).indices
    for v, flag in flags.items():
        arr, ev = flag.to_numpy(), np.zeros(len(days), dtype=bool)
        for idx in groups.values():
            ev[idx] = apply_cooldown(arr[idx], s.backtest.cooldown_days)
        days[f"ev_{v}"] = ev
    return days


def add_periods(days: pd.DataFrame, s: Settings) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Label every day IS / OOS / purged per horizon. OOS = after the cutoff. IS = signal AND exit on or before the cutoff;
    an in-sample signal whose forward window crosses the cutoff is purged (it would peek into the OOS period)."""
    cutoff = split_cutoff(days["date"].unique(), s.backtest.oos_fraction)
    for h in s.backtest.horizons:
        ex = days[f"exit{h}"]
        days[f"period{h}"] = np.where(days["date"] > cutoff, "OOS", np.where(ex <= cutoff, "IS", "purged"))
    return days, cutoff


def add_peer_returns(days: pd.DataFrame, horizons) -> pd.DataFrame:
    """ew{h}: mean forward return of ALL OTHER stocks signalling on the same date (a market proxy made of the universe itself)."""
    for h in horizons:
        f = days[f"fwd{h}"]
        tot = f.groupby(days["date"]).transform("sum")
        cnt = f.groupby(days["date"]).transform("count")
        own = f.fillna(0.0)
        n_other = cnt - f.notna().astype(int)
        days[f"ew{h}"] = np.where(n_other > 0, (tot - own) / n_other.replace(0, np.nan), np.nan)
    return days


# ---------------------------------------------------------------- statistics
def cluster_bootstrap(x: np.ndarray, clusters: np.ndarray, draws: int, level: float, seed: int) -> tuple[float, float, float, int]:
    """Mean of x with a percentile interval from resampling whole clusters (calendar months) with replacement.
    Returns (mean, lo, hi, n_clusters). Events inside a cluster stay together, which respects the way dip events
    bunch up in market-wide selloffs; a naive standard error would be far too small."""
    x = np.asarray(x, dtype=float)
    ok = ~np.isnan(x)
    x, clusters = x[ok], np.asarray(clusters)[ok]
    if len(x) == 0:
        return np.nan, np.nan, np.nan, 0
    labels, inv = np.unique(clusters, return_inverse=True)
    csum = np.bincount(inv, weights=x, minlength=len(labels))
    cnt = np.bincount(inv, minlength=len(labels)).astype(float)
    mean = float(x.mean())
    if len(labels) < 2:
        return mean, np.nan, np.nan, len(labels)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(labels), size=(draws, len(labels)))
    boots = csum[pick].sum(axis=1) / cnt[pick].sum(axis=1)
    a = (1 - level) / 2
    lo, hi = np.quantile(boots, [a, 1 - a])
    return mean, float(lo), float(hi), len(labels)


def placebo_means(ev: pd.DataFrame, pool: pd.DataFrame, col: str, draws: int, seed: int) -> tuple[np.ndarray, float, int]:
    """For each event draw a random non-dip day of the SAME stock in the SAME calendar year (any year if that year has none),
    and average the forward returns. Returns (placebo means, mean of the matched events, matched event count)."""
    rng = np.random.default_rng(seed)
    pool = pool[["ticker", "year", col]].dropna()
    by_year = {k: v.to_numpy() for k, v in pool.groupby(["ticker", "year"])[col]}
    by_tkr = {k: v.to_numpy() for k, v in pool.groupby("ticker")[col]}
    arrays, obs = [], []
    for t, y, r in zip(ev["ticker"], ev["year"], ev[col]):
        a = by_year.get((t, y))
        if a is None or len(a) == 0:
            a = by_tkr.get(t)
        if a is None or len(a) == 0 or np.isnan(r):
            continue
        arrays.append(a)
        obs.append(r)
    if not arrays:
        return np.array([]), np.nan, 0
    lens = np.array([len(a) for a in arrays])
    starts = np.concatenate([[0], np.cumsum(lens)[:-1]])
    flat = np.concatenate(arrays)
    idx = starts + (rng.random((draws, len(arrays))) * lens).astype(int)
    return flat[idx].mean(axis=1), float(np.mean(obs)), len(arrays)


def date_shift_placebo(rows: np.ndarray, fwd: np.ndarray, tstart: np.ndarray, tend: np.ndarray, F: np.ndarray,
                       draws: int, seed: int, lo: int = 70, hi: int = 400, with_draws: bool = False) -> dict:
    """Placebo that keeps events where they are relative to each other. Every draw moves ALL events by one common random lag
    (70 to 400 bars, either direction) and reads each stock's forward return at the shifted bar (F, NaN where not eligible).
    Crashes and rebounds therefore stay clustered, unlike independent random days, which understate the noise.
    Per draw the events' own mean is taken over the same events that found a valid shifted day, so the comparison is paired.
    p = share of draws where the shifted mean is at least the events' mean. `shift_lags` = number of distinct lags among the kept draws
    (at most 2 * (hi - lo + 1)); the p-value cannot be finer than the draws and lags allow."""
    rng = np.random.default_rng(seed)
    cand = np.concatenate([np.arange(-hi, -lo + 1), np.arange(lo, hi + 1)])
    delta = rng.choice(cand, size=draws)
    obs_m, pla_m, nval = np.full(draws, np.nan), np.full(draws, np.nan), np.zeros(draws, dtype=int)
    for a in range(0, draws, 250):
        d = delta[a:a + 250]
        idx = rows[None, :] + d[:, None]
        inside = (idx >= tstart[None, :]) & (idx < tend[None, :])
        vals = np.where(inside, F[np.clip(idx, 0, len(F) - 1)], np.nan)
        good = ~np.isnan(vals)
        cnt = good.sum(axis=1)
        safe = np.maximum(cnt, 1)
        pla_m[a:a + 250] = np.where(cnt > 0, np.where(good, vals, 0.0).sum(axis=1) / safe, np.nan)
        obs_m[a:a + 250] = np.where(cnt > 0, np.where(good, fwd[None, :], 0.0).sum(axis=1) / safe, np.nan)
        nval[a:a + 250] = cnt
    keep = nval >= max(20, 0.3 * len(rows))
    if not keep.any():
        return {}
    o, p = obs_m[keep], pla_m[keep]
    out = {"shift_p": float((1 + (p >= o).sum()) / (keep.sum() + 1)), "shift_excess": float((o - p).mean()),
           "shift_draws": int(keep.sum()), "shift_mean": float(p.mean()),
           "shift_lags": int(len(np.unique(delta[keep])))}                              # distinct lags actually used: the placebo's resolution
    if with_draws:
        out["placebo_minus_events"] = p - o
    return out


def shift_inputs(days: pd.DataFrame, c: Cell, ev: pd.DataFrame) -> tuple:
    """Arrays date_shift_placebo needs for one cell: event rows, their returns and stock bounds, and the eligible-day return array F."""
    h = c.horizon
    eligible = days["valid"] & days[f"fwd{h}"].notna() & _period_mask(days, h, c.period)
    if c.group != "All":
        eligible &= days["group"] == c.group
    F = np.where(eligible, days[f"fwd{h}"], np.nan)
    return ev.index.to_numpy(), ev[f"fwd{h}"].to_numpy(), ev["tstart"].to_numpy(), ev["tend"].to_numpy(), F


@dataclass
class Cell:
    variant: str
    horizon: int
    group: str
    period: str


def cell_events(days: pd.DataFrame, c: Cell) -> pd.DataFrame:
    """Events of one cell: variant events, horizon with data, group and period filters."""
    h = c.horizon
    m = days[f"ev_{c.variant}"] & days[f"fwd{h}"].notna()
    if c.group != "All":
        m &= days["group"] == c.group
    return days[m & _period_mask(days, h, c.period)]


def _period_mask(days: pd.DataFrame, h: int, period: str) -> pd.Series:
    if period == "ALL":
        return pd.Series(True, index=days.index)
    if period == "IS":
        return days[f"period{h}"] == "IS"
    if period == "OOS":
        return days[f"period{h}"] == "OOS"
    if period == "OOS_exstress":
        return (days[f"period{h}"] == "OOS") & ~days["stress"]
    raise ValueError(period)


def own_baseline(days: pd.DataFrame, c: Cell) -> pd.Series:
    """Mean forward return per stock on NON-DIP days inside the same period filter (and the same group)."""
    h = c.horizon
    return days[_nondip_mask(days, c)].groupby("ticker")[f"fwd{h}"].mean()


def _nondip_mask(days: pd.DataFrame, c: Cell) -> pd.Series:
    """Baseline days: a signal could be computed (252 bars of history) and it said "no dip", in the cell's period and group."""
    h = c.horizon
    m = days["valid"] & ~days["dip"] & days[f"fwd{h}"].notna() & _period_mask(days, h, c.period)
    if c.group != "All":
        m &= days["group"] == c.group
    return m


def summarize(days: pd.DataFrame, c: Cell, s: Settings) -> dict:
    """All numbers for one cell. Costs are applied to the event return only; the baselines are compared before costs
    on both sides (a trader who picks random days pays the same round trip)."""
    bt, h = s.backtest, c.horizon
    ev = cell_events(days, c)
    base_map = own_baseline(days, c)
    out = {"variant": c.variant, "horizon": h, "group": c.group, "period": c.period, "n": len(ev)}
    if len(ev) == 0:
        return out
    fwd = ev[f"fwd{h}"].to_numpy()
    cost = bt.cost_roundtrip
    net = fwd - cost
    out.update({"n_dates": ev["date"].nunique(), "n_stocks": ev["ticker"].nunique(), "n_months": ev["month"].nunique(),
                "gross_mean": fwd.mean(), "net_mean_1x": (fwd - cost).mean(), "net_mean_2x": (fwd - 2 * cost).mean(),
                "net_mean_4x": (fwd - 4 * cost).mean(), "net_median": float(np.median(net)),
                "hit_rate": float((net > 0).mean()), "p10": float(np.quantile(net, .10)), "p90": float(np.quantile(net, .90)),
                "worst": float(net.min()), "mae_median": float(ev[f"mae{h}"].median()), "mae_worst": float(ev[f"mae{h}"].min()),
                "n_suspect": int(ev[f"suspect{h}"].sum())})
    seed = bt.seed + h
    base = ev["ticker"].map(base_map)
    series = {"own": fwd - base.to_numpy(), "index": fwd - ev[f"idx{h}"].to_numpy(), "peers": fwd - ev[f"ew{h}"].to_numpy()}
    for k, v in series.items():
        m, lo, hi, nc = cluster_bootstrap(v, ev["month"].to_numpy(), bt.bootstrap_draws, bt.ci_level, seed)
        out.update({f"ex_{k}": m, f"ex_{k}_lo": lo, f"ex_{k}_hi": hi, f"ex_{k}_n": int(np.isfinite(v).sum())})
    out["base_own_mean"] = float(np.nanmean(base.to_numpy()))
    pm = _nondip_mask(days, c)
    nd = days[pm]
    out.update({"base_hit": float((nd[f"fwd{h}"] - cost > 0).mean()), "base_n": len(nd),
                "nd_vs_idx": float((nd[f"fwd{h}"] - nd[f"idx{h}"]).mean()), "ev_stress_share": float(ev["stress"].mean())})
    # placebo 1 (independent): random non-dip days of the same stock and year. Ignores that events share dates, so it is too optimistic.
    dist, obs, n_match = placebo_means(ev, nd, f"fwd{h}", bt.placebo_draws, seed)
    if n_match:
        out.update({"placebo_mean": float(dist.mean()), "placebo_obs": obs, "placebo_n": n_match,
                    "placebo_p": float((1 + (dist >= obs).sum()) / (len(dist) + 1))})
    # placebo 2 (date shift): every event moved by one common random lag, so clusters stay clusters
    out.update(date_shift_placebo(*shift_inputs(days, c, ev), bt.placebo_draws, seed + 1000))
    # same cell without events that touch a suspect (>40% one-day) move
    clean = ev[~ev[f"suspect{h}"]]
    if len(clean) != len(ev) and len(clean):
        v = clean[f"fwd{h}"].to_numpy() - clean["ticker"].map(base_map).to_numpy()
        m, lo, hi, _ = cluster_bootstrap(v, clean["month"].to_numpy(), bt.bootstrap_draws, bt.ci_level, seed)
        out.update({"ex_own_nosuspect": m, "ex_own_nosuspect_lo": lo, "ex_own_nosuspect_hi": hi})
    return out


def run_cells(days: pd.DataFrame, s: Settings, groups=("All", US, EU), periods=PERIODS) -> pd.DataFrame:
    rows = []
    for v in VARIANTS:
        for h in s.backtest.horizons:
            for g in groups:
                for p in periods:
                    rows.append(summarize(days, Cell(v, h, g, p), s))
    return pd.DataFrame(rows)
