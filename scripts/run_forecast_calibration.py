#!/usr/bin/env python3
"""Walk-forward calibration test of the 21-day volatility range (src/dipdash/forecast.py).

    .venv/Scripts/python.exe scripts/run_forecast_calibration.py [--raw PATH] [--workers 7] [--reuse]

Pre-stated ship criterion is in the forecast.py docstring (written before any result): overall OOS 80% coverage within 0.80 +/- 0.04
AND dip-state coverage within 0.80 +/- 0.06; two attempts (raw, then one in-sample-fitted global scale factor), no further tuning.
Design: per stock, origins every 21 trading days from the 401st close; model refitted on data up to the origin only; outcome = log return
over the next 21 bars (windows do not overlap within a stock). Split = backtest.split_cutoff(all dates, 0.4); in-sample origins are those
whose outcome ends on or before the cutoff (purge); out-of-sample origins are after it. Uncertainty: month-clustered bootstrap by origin month.
Output: output/backtests/<today>_forecast/{results.csv, origins.csv.gz, report_forecast.md, calibration.png}.
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dipdash import forecast as fc  # noqa: E402
from dipdash.backtest import cluster_bootstrap, group_of, split_cutoff  # noqa: E402
from dipdash.backtest_run import clean_bars  # noqa: E402
from dipdash.cache import load_raw_prices  # noqa: E402
from dipdash.config import load_universe  # noqa: E402

H = 21
STEP = 21
START = fc.MIN_OBS            # first origin has 400 returns
OOS_FRACTION = 0.4
TARGET, TOL_ALL, TOL_DIP = 0.80, 0.04, 0.06
METHODS = ("garch_t_fhs", "ewma", "naive")
DEFAULT_RAW = ROOT / "data" / "raw" / "yfinance_backtest" / "2026-11-04.csv.gz"
DRAWS, LEVEL = 2000, 0.95


def _one_stock(args):
    ticker, close = args
    t0 = time.time()
    c = close.to_numpy()
    rows = []
    for k in range(START, len(c) - H, STEP):
        res = fc.all_ranges(close.iloc[: k + 1], H, seed=k)
        y = float(np.log(c[k + H] / c[k]))
        r1 = c[k] / c[k - 1] - 1
        r5 = c[k] / c[k - 5] - 1
        row = {"ticker": ticker, "origin": close.index[k], "end": close.index[k + H], "y": y,
               "dip": bool(r5 <= -0.07 or r1 <= -0.04), "fallback": res["garch_t_fhs"]["method"] == "ewma_fallback"}
        for m in METHODS:
            d = res[m]
            row[f"{m}_lo"], row[f"{m}_mid"], row[f"{m}_hi"] = (float(np.log1p(d[x])) for x in ("lo", "mid", "hi"))
            row[f"{m}_vol"] = d["vol_ann"]
        rows.append(row)
    return ticker, rows, time.time() - t0


def build_origins(prices: dict, workers: int) -> tuple[pd.DataFrame, float]:
    jobs = list(prices.items())
    out, secs, nfits = [], 0.0, 0
    with ProcessPoolExecutor(workers) as ex:
        for i, (t, rows, s) in enumerate(ex.map(_one_stock, jobs, chunksize=1), 1):
            out += rows
            secs += s
            nfits += len(rows)
            if i % 20 == 0:
                print(f"  {i}/{len(jobs)} stocks", flush=True)
    return pd.DataFrame(out), secs / max(nfits, 1)


# ------------------------------------------------------------ scoring
def pinball(y, q, tau):
    d = y - q
    return np.maximum(tau * d, (tau - 1) * d)


def scale_factor(df: pd.DataFrame, m: str) -> float:
    """In-sample k with fraction(lo*k <= y <= hi*k) = TARGET: the TARGET-quantile of y/hi (y>0) or y/lo (y<0)."""
    y, lo, hi = df.y.to_numpy(), df[f"{m}_lo"].to_numpy(), df[f"{m}_hi"].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        u = np.where(y >= 0, np.where(hi > 0, y / hi, np.inf), np.where(lo < 0, y / lo, np.inf))
    return float(np.quantile(u, TARGET))


def covered(df: pd.DataFrame, m: str, k: float) -> np.ndarray:
    return ((df.y >= df[f"{m}_lo"] * k) & (df.y <= df[f"{m}_hi"] * k)).to_numpy().astype(float)


def loss(df: pd.DataFrame, m: str, k: float) -> np.ndarray:
    y = df.y.to_numpy()
    return (pinball(y, df[f"{m}_lo"].to_numpy() * k, 0.1) + pinball(y, df[f"{m}_mid"].to_numpy() * k, 0.5)
            + pinball(y, df[f"{m}_hi"].to_numpy() * k, 0.9)) / 3


def groups(oos: pd.DataFrame) -> dict[str, pd.Series]:
    yr = oos.origin.dt.year
    return {"ALL OOS": oos.origin.notna(), "dip state": oos.dip, "no dip": ~oos.dip,
            "US": oos.group == "US", "Europe": oos.group != "US", "US dip": oos.dip & (oos.group == "US"),
            "Europe dip": oos.dip & (oos.group != "US"),
            "2020 origins": yr == 2020, "2022 origins": yr == 2022, "other years": ~yr.isin([2020, 2022])}


def evaluate(oos: pd.DataFrame, ks: dict, attempt: int) -> pd.DataFrame:
    month = oos.origin.dt.strftime("%Y-%m").to_numpy()
    rows = []
    for gname, mask in groups(oos).items():
        sub, mo = oos[mask.to_numpy()], month[mask.to_numpy()]
        for m in METHODS:
            cov = covered(sub, m, ks[m])
            ls = loss(sub, m, ks[m])
            mean, lo, hi, ncl = cluster_bootstrap(cov, mo, DRAWS, LEVEL, 11)
            lmean = float(np.mean(ls)) if len(ls) else np.nan
            dl = ls - loss(sub, "naive", ks["naive"])
            dm, dlo, dhi, _ = cluster_bootstrap(dl, mo, DRAWS, LEVEL, 12)
            rows.append({"attempt": attempt, "scale_k": ks[m], "method": m, "group": gname, "n": len(sub), "n_months": ncl,
                         "coverage": mean, "cov_lo": lo, "cov_hi": hi, "target": TARGET, "pinball": lmean,
                         "pinball_minus_naive": dm, "pm_lo": dlo, "pm_hi": dhi})
    return pd.DataFrame(rows)


def verdict(res: pd.DataFrame, attempt: int) -> dict:
    g = res[(res.attempt == attempt) & (res.method == "garch_t_fhs")].set_index("group")
    a, d = g.loc["ALL OOS", "coverage"], g.loc["dip state", "coverage"]
    pa, pd_ = abs(a - TARGET) <= TOL_ALL, abs(d - TARGET) <= TOL_DIP
    return {"all": a, "dip": d, "pass_all": bool(pa), "pass_dip": bool(pd_), "pass": bool(pa and pd_)}


def chart(res: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    order = ["ALL OOS", "dip state", "no dip", "US", "Europe", "2020 origins", "2022 origins", "other years"]
    col = {"garch_t_fhs": "#1b6ca8", "ewma": "#d98324", "naive": "#6b6b6b"}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, att, title in zip(axes, (1, 2), ("Attempt 1: raw model", "Attempt 2: one in-sample scale factor")):
        ax.axvspan(TARGET - TOL_ALL, TARGET + TOL_ALL, color="#2a9d5c", alpha=0.10, lw=0)
        ax.axvline(TARGET, color="#2a9d5c", lw=1.2)
        for j, m in enumerate(METHODS):
            r = res[(res.attempt == att) & (res.method == m)].set_index("group").loc[order]
            y = np.arange(len(order)) + (j - 1) * 0.22
            ax.errorbar(r.coverage, y, xerr=[r.coverage - r.cov_lo, r.cov_hi - r.coverage], fmt="o", ms=5, color=col[m],
                        capsize=2.5, lw=1.3, label=m)
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels(order)
        ax.set_xlabel("empirical coverage of the 80% range (95% month-clustered CI)")
        ax.set_title(title, fontsize=11)
        ax.grid(axis="x", alpha=0.25)
    axes[0].invert_yaxis()
    axes[0].legend(loc="lower left", fontsize=8, frameon=False)
    fig.suptitle("Out-of-sample calibration of the 21-day range (line = 0.80 target; band = overall-row tolerance)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def pct(x):
    return f"{100 * x:.1f}%"


def write_report(out: Path, res: pd.DataFrame, meta: dict, v1: dict, v2: dict, ship: str) -> None:
    def table(att):
        r = res[res.attempt == att]
        lines = ["| group | n | months | GARCH-t FHS | EWMA | naive 60d |", "|---|---|---|---|---|---|"]
        for g in r.group.unique():
            cells = []
            for m in METHODS:
                x = r[(r.group == g) & (r.method == m)].iloc[0]
                cells.append(f"{x.coverage:.3f} [{x.cov_lo:.3f}, {x.cov_hi:.3f}]")
            x = r[(r.group == g) & (r.method == "garch_t_fhs")].iloc[0]
            lines.append(f"| {g} | {int(x.n)} | {int(x.n_months)} | " + " | ".join(cells) + " |")
        return "\n".join(lines)

    def ptable(att):
        r = res[res.attempt == att]
        lines = ["| group | GARCH-t FHS | EWMA | naive 60d | GARCH minus naive [95% CI] |", "|---|---|---|---|---|"]
        for g in ("ALL OOS", "dip state", "2020 origins", "2022 origins"):
            c = {m: r[(r.group == g) & (r.method == m)].iloc[0] for m in METHODS}
            gg = c["garch_t_fhs"]
            lines.append(f"| {g} | {c['garch_t_fhs'].pinball:.5f} | {c['ewma'].pinball:.5f} | {c['naive'].pinball:.5f} | "
                         f"{gg.pinball_minus_naive:+.5f} [{gg.pm_lo:+.5f}, {gg.pm_hi:+.5f}] |")
        return "\n".join(lines)

    def line(v, name):
        return (f"{name}: overall {v['all']:.3f} (needs 0.76 to 0.84): {'PASS' if v['pass_all'] else 'FAIL'}; "
                f"dip state {v['dip']:.3f} (needs 0.74 to 0.86): {'PASS' if v['pass_dip'] else 'FAIL'}.")

    k = res[(res.attempt == 2) & (res.method == "garch_t_fhs")].scale_k.iloc[0]
    txt = f"""# 21-day volatility range: calibration report ({meta['today']})

Educational screen output. This tests whether a volatility RANGE is honest. It says nothing about direction and is not a price target.

## Result first
- **Decision: {ship}**
- {line(v1, 'Attempt 1 (raw GARCH-t FHS)')}
- {line(v2, f'Attempt 2 (global scale factor k = {k:.3f} fitted in-sample only)')}
- Criterion (pre-stated in `src/dipdash/forecast.py` before any result): overall OOS coverage 0.80 +/- 0.04 AND dip-state coverage 0.80 +/- 0.06, judged on the point estimate. Two attempts, no further tuning.

## Design
- Universe: {meta['n_stocks']} stocks (current constituents), history {meta['first']} to {meta['last']}. Origins every 21 trading days per stock, model refitted on data up to the origin only (trailing 750 returns, min 400); {meta['n_origins']} origins in total, {meta['n_fallback']} ({pct(meta['fb_rate'])}) used the EWMA fallback because GARCH did not converge.
- Split: backtest.py `split_cutoff` at 60/40 -> in-sample ends {meta['cutoff']}. In-sample origins whose 21-day outcome ends after the cutoff are dropped (purge). Out-of-sample: {meta['n_oos']} origins (scored only; k was fitted on {meta['n_is']} in-sample origins).
- Dip state at the origin: 5-day return <= -7% or 1-day <= -4% (the project's dip rule), {meta['n_oos_dip']} OOS origins.
- Windows do not overlap within a stock; across stocks they do (market-wide events), hence CIs from the month-clustered bootstrap (`backtest.cluster_bootstrap`, {DRAWS} draws, 95%, clusters = origin month, {meta['n_oos_months']} months).
- Runtime: about {meta['sec_per_fit']:.2f} s per origin (one GARCH fit plus baselines, inside a busy process pool); {meta['sec_per_stock_now']:.2f} s for one nightly forecast on its own.

## Coverage of the 80% range, out of sample (target 0.80)
![calibration](calibration.png)

Attempt 1 (raw):

{table(1)}

Attempt 2 (each method's ranges multiplied by its own in-sample factor; only the GARCH row is judged):

{table(2)}

## Pinball (quantile) loss, average of the 10/50/90% quantiles on log returns (lower is better)
Attempt 1:

{ptable(1)}

Attempt 2:

{ptable(2)}

## How much to trust this
- **Survivorship bias**: the universe is today's blue-chip list; names that collapsed and were dropped are missing, so past volatility spikes and crash tails are understated and coverage is flattered.
- **Overlapping, correlated outcomes**: windows do not overlap within a stock, but all stocks fall together in 2020 and 2022; the effective number of independent periods is the {meta['n_oos_months']} months, not {meta['n_oos']}. The intervals above account for this, but only for what happened in this one sample.
- **GARCH can underreact to jumps**: a single-day gap raises the forecast only through the next days' variance recursion, and the model has no event calendar.
- **Earnings gaps**: 21-day windows that contain a report carry extra variance that is not forecast, so ranges around earnings are too narrow on average.
- Zero-drift assumption: the range is centred near zero by construction. It is a size-of-move estimate, not a statement about up or down.
- Coverage is an average. A pass overall does not mean each stock or each regime is calibrated (see the by-group rows); intervals for small groups are wide.
- Prices only, adjusted closes, one data vendor, not cross-checked here.
"""
    (out / "report_forecast.md").write_text(txt, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--reuse", action="store_true", help="reuse origins.csv.gz in the output folder")
    ap.add_argument("--limit", type=int, default=0, help="only the first N tickers (smoke test)")
    ap.add_argument("--out", default=str(ROOT / "output" / "backtests" / f"{date.today().isoformat()}_forecast"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    bars = load_raw_prices(a.raw)
    prices = {}
    for t, (c, v) in bars.items():
        c2, _ = clean_bars(c, v)
        bad = ~(np.isfinite(c2) & (c2 > 0))          # e.g. ABI.BR has 70 zero/negative closes that clean_bars (volume rule) keeps
        if bad.any():
            print(f"  {t}: dropped {int(bad.sum())} non-positive/non-finite closes")
            c2 = c2[~bad]
        if len(c2) > START + H + 1:
            c2.index = pd.DatetimeIndex(c2.index).tz_localize(None).normalize()
            prices[t] = c2
    if a.limit:
        prices = dict(list(prices.items())[: a.limit])
    region = {u.ticker: group_of(u.region) for u in load_universe()}
    all_dates = sorted(set().union(*[set(c.index) for c in prices.values()]))
    cutoff = split_cutoff(all_dates, OOS_FRACTION)

    p = out / "origins.csv.gz"
    if a.reuse and p.exists():
        df = pd.read_csv(p, parse_dates=["origin", "end"])
        spf = float(pd.read_csv(out / "timing.csv").spf.iloc[0]) if (out / "timing.csv").exists() else float("nan")
    else:
        print(f"Walk-forward over {len(prices)} stocks with {a.workers} workers...", flush=True)
        df, spf = build_origins(prices, a.workers)
        df.to_csv(p, index=False)
        pd.DataFrame({"spf": [spf]}).to_csv(out / "timing.csv", index=False)
    df["group"] = df.ticker.map(region).fillna("Other")
    ins = df[df.end <= cutoff]
    oos = df[df.origin > cutoff].reset_index(drop=True)

    one = next(iter(prices.values()))
    fc.range_forecast(one)                      # warm-up (first call imports arch)
    t0 = time.time()
    fc.range_forecast(one)
    sec_now = time.time() - t0

    ks1 = {m: 1.0 for m in METHODS}
    ks2 = {m: scale_factor(ins, m) for m in METHODS}
    res = pd.concat([evaluate(oos, ks1, 1), evaluate(oos, ks2, 2)], ignore_index=True)
    v1, v2 = verdict(res, 1), verdict(res, 2)
    if v1["pass"]:
        ship = "RANGE MAY SHIP (attempt 1, raw model, passes both pre-stated tests)"
    elif v2["pass"]:
        ship = "RANGE MAY SHIP ONLY WITH THE ATTEMPT-2 SCALE FACTOR (raw model failed, recalibrated model passes both tests)"
    else:
        ship = "RANGE DOES NOT SHIP (both attempts fail the pre-stated criterion)"
    res.to_csv(out / "results.csv", index=False)
    chart(res, out / "calibration.png")
    meta = {"today": date.today().isoformat(), "n_stocks": df.ticker.nunique(), "first": min(all_dates).date(),
            "last": max(all_dates).date(), "n_origins": len(df), "n_fallback": int(df.fallback.sum()), "fb_rate": df.fallback.mean(),
            "cutoff": cutoff.date(), "n_oos": len(oos), "n_is": len(ins), "n_oos_dip": int(oos.dip.sum()),
            "n_oos_months": oos.origin.dt.strftime("%Y-%m").nunique(), "sec_per_fit": spf, "sec_per_stock_now": sec_now}
    write_report(out, res, meta, v1, v2, ship)
    print(ship)
    print(v1)
    print(v2)
    print(f"k={ks2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
