#!/usr/bin/env python3
"""Walk-forward calibration test of the 21-day volatility range (src/dipdash/forecast.py).

    .venv/Scripts/python.exe scripts/run_forecast_calibration.py [--raw PATH] [--workers 7] [--reuse] [--out-root DIR]

Pre-stated ship criterion is in the forecast.py docstring (written before any result): overall OOS 80% coverage within 0.80 +/- 0.04
AND dip-state coverage within 0.80 +/- 0.06; two attempts (raw, then one in-sample-fitted global scale factor), no further tuning.
Design: per stock, origins every 21 trading days from the 401st close; model refitted on data up to the origin only; outcome = log return
over the next 21 bars (windows do not overlap within a stock). Split = backtest.shared_cutoff (dates on or after settings backtest.start_date, settings oos_fraction; the same as the backtest and the feature experiment); in-sample origins are those
whose outcome ends on or before the cutoff (purge); out-of-sample origins are after it. Uncertainty: month-clustered bootstrap by origin month.
Dip state = backtest.dip_state (the project's dip rule from settings, incl. the 20-day-high rule), looked up by origin date.
Pre-registration: a frozen spec built from the constants below and the settings (forecast_spec) is registered (registry.register: spec_<hash>.json +
a row in <out-root>/registry.csv) BEFORE any origin is computed; every coverage and pinball cell goes to <out-root>/trials_all.csv.
Output: <out-root>/<today>_forecast/{spec_forecast.json, results.csv, origins.csv.gz, report_forecast.md, calibration.png}.
"""
from __future__ import annotations

import argparse
import json
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
from dipdash import registry  # noqa: E402
from dipdash.backtest import cluster_bootstrap, dip_state, group_of, shared_calendar, shared_cutoff, signals  # noqa: E402
from dipdash.backtest_run import clean_bars, sha256  # noqa: E402
from dipdash.cache import load_raw_prices  # noqa: E402
from dipdash.config import load_settings, load_universe  # noqa: E402
from dipdash.provenance import build_provenance  # noqa: E402

H = 21
STEP = 21
START = fc.MIN_OBS            # first origin has 400 returns
TARGET, TOL_ALL, TOL_DIP = 0.80, 0.04, 0.06
METHODS = ("garch_t_fhs", "ewma", "naive")
DEFAULT_RAW = ROOT / "data" / "raw" / "yfinance_backtest" / "2026-11-04.csv.gz"
DRAWS, LEVEL = 2000, 0.95
SEEDS = {"coverage": 11, "pinball_minus_naive": 12}
ATTEMPTS = (1, 2)
STATS = ("coverage", "pinball")
GROUPS = ("ALL OOS", "dip state", "no dip", "US", "Europe", "US dip", "Europe dip", "2020 origins", "2022 origins", "other years")
VERDICT_GROUPS = ("ALL OOS", "dip state")
PLANNED_CELLS = len(GROUPS) * len(METHODS) * len(ATTEMPTS) * len(STATS)
CRITERION_TEXT = " ".join(fc.__doc__.split("PRE-STATED SHIP CRITERION", 1)[1].split()).lstrip()   # the docstring, verbatim (whitespace collapsed)
VERDICT_TEXT = (f"Judged on garch_t_fhs over the out-of-sample origins, on the point estimate: |coverage(ALL OOS) - {TARGET:.2f}| <= {TOL_ALL:.2f} "
                f"AND |coverage(dip state) - {TARGET:.2f}| <= {TOL_DIP:.2f}. Attempt 1 = the raw model; attempt 2 = one global scale factor k "
                f"(the in-sample {TARGET:.2f} quantile of the outcome-to-range ratio, in-sample origins only), re-tested once. The range may ship "
                "if attempt 1 passes, else if attempt 2 passes; otherwise it does not ship. No further attempts.")


DEFAULT_ROOT = ROOT / "output" / "backtests"
META_FILE = "origins_meta.json"


def origins_meta(spec: dict) -> dict:
    """What the cached origins.csv.gz was built from: the spec hash plus its raw-file hash, ticker limit and split cutoff."""
    return {"spec_hash": spec["spec_hash"], "raw_sha256": spec["data"]["raw_sha256"], "limit": spec["data"]["limit"],
            "cutoff": spec["split"]["cutoff"]}


def dip_text(s) -> str:
    """The dip definition in words, with the settings values, for the frozen spec."""
    d = s.dip
    return (f"the project's dip rule (backtest.dip_state), true if 1-day return <= -{100 * d.drop_1d:g}% or 5-day return <= -{100 * d.drop_5d:g}% "
            f"or the close is >= {100 * d.drawdown_20d:g}% below its 20-day high, at the origin close; needs 252 bars of history")


def origin_dips(close: pd.Series, s) -> pd.Series:
    """backtest.dip_state of one stock, on the stock's own dates. Every origin (bar START and later) must have 252 bars of history."""
    sig = signals(close, s)
    assert sig.index.equals(close.index), "signals dropped bars: the dip series would not line up with the origins"
    assert len(sig) > START and bool(sig["valid"].iloc[START:].all()), "an origin lacks the 252 bars of history the dip rule needs"
    return dip_state(close, s)


def forecast_spec(raw: Path, tickers: list[str], cutoff: pd.Timestamp, limit: int, family_id: str, s) -> dict:
    """Pre-registration of the calibration test, built from constants, the raw file's hash and dates only (no outcome enters)."""
    spec = {
        "family_id": family_id,
        "question": "Is the 80% range of the 21-day log return calibrated out of sample, overall and in the dip state?",
        "model": {"primary": "garch_t_fhs", "window": fc.WINDOW, "min_obs": fc.MIN_OBS, "sims": fc.SIMS, "quantiles": list(fc.Q),
                  "ewma_lambda": fc.EWMA_LAMBDA, "naive_window": fc.NAIVE_WINDOW, "fallback": "ewma when the GARCH fit fails"},
        "methods": list(METHODS),
        "design": {"horizons": [H], "step": STEP, "first_origin_bar": START, "refit": "at every origin, on data up to the origin only",
                   "outcome": "log return from the origin close to the close H bars later",
                   "dip_state": dip_text(s),
                   "dip_settings": {"drop_1d": s.dip.drop_1d, "drop_5d": s.dip.drop_5d, "drawdown_20d": s.dip.drawdown_20d}},
        "split": {"oos_fraction": s.backtest.oos_fraction, "start_date": s.backtest.start_date, "cutoff": str(cutoff.date()),
                  "purge": "in-sample origins whose outcome ends after the cutoff are dropped; out-of-sample = origins after the cutoff"},
        "criterion_text": CRITERION_TEXT,
        "verdict_rule": {"target": TARGET, "tol_all": TOL_ALL, "tol_dip": TOL_DIP, "attempts": list(ATTEMPTS), "groups": list(VERDICT_GROUPS),
                         "judged_on": "point estimate", "text": VERDICT_TEXT},
        "groups": list(GROUPS), "stats": list(STATS),
        "uncertainty": {"method": "bootstrap resampling origin months", "draws": DRAWS, "level": LEVEL, "seeds": SEEDS},
        "planned_cells": PLANNED_CELLS,
        "data": {"raw_file": raw.name, "raw_sha256": sha256(raw), "n_stocks": len(tickers), "tickers": sorted(tickers), "limit": limit},
        "universe": {"bias": "current constituents only: survivorship bias"},
        "notes": "the criterion was first written in the forecast.py docstring before any calibration result; this spec freezes it as data",
    }
    spec["spec_hash"] = registry.hash_for("forecast", spec)
    return spec


def attach_provenance(spec: dict, s) -> dict:
    """Record code, package versions and settings-section hashes in the spec. Not hashed (registry.ALWAYS_EXCLUDED)."""
    spec["provenance"] = build_provenance(s, ROOT / "src" / "dipdash")
    return spec


def _one_stock(args):
    ticker, close, dip = args                      # dip: precomputed bool Series on close's index (the pool gets data, not settings)
    t0 = time.time()
    c = close.to_numpy()
    rows = []
    for k in range(START, len(c) - H, STEP):
        res = fc.all_ranges(close.iloc[: k + 1], H, seed=k)
        y = float(np.log(c[k + H] / c[k]))
        row = {"ticker": ticker, "origin": close.index[k], "end": close.index[k + H], "y": y,
               "dip": bool(dip.loc[close.index[k]]), "fallback": res["garch_t_fhs"]["method"] == "ewma_fallback"}
        for m in METHODS:
            d = res[m]
            row[f"{m}_lo"], row[f"{m}_mid"], row[f"{m}_hi"] = (float(np.log1p(d[x])) for x in ("lo", "mid", "hi"))
            row[f"{m}_vol"] = d["vol_ann"]
        rows.append(row)
    return ticker, rows, time.time() - t0


def build_origins(reg, prices: dict, dips: dict, workers: int) -> tuple[pd.DataFrame, float]:
    """workers <= 1 runs in this process (tests, small runs); otherwise a process pool. Needs the Registration token."""
    registry.require_registered(reg)
    jobs = [(t, c, dips[t]) for t, c in prices.items()]
    out, secs, nfits = [], 0.0, 0
    if workers <= 1:
        results = map(_one_stock, jobs)
    else:
        ex = ProcessPoolExecutor(workers)
        results = ex.map(_one_stock, jobs, chunksize=1)
    try:
        for i, (t, rows, s) in enumerate(results, 1):
            out += rows
            secs += s
            nfits += len(rows)
            if i % 20 == 0:
                print(f"  {i}/{len(jobs)} stocks", flush=True)
    finally:
        if workers > 1:
            ex.shutdown()
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
    """Keys and order equal GROUPS (tested), so the registered cell count is the computed one."""
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
            mean, lo, hi, ncl = cluster_bootstrap(cov, mo, DRAWS, LEVEL, SEEDS["coverage"])
            lmean = float(np.mean(ls)) if len(ls) else np.nan
            dl = ls - loss(sub, "naive", ks["naive"])
            dm, dlo, dhi, _ = cluster_bootstrap(dl, mo, DRAWS, LEVEL, SEEDS["pinball_minus_naive"])
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


def trial_rows(res: pd.DataFrame) -> pd.DataFrame:
    """evaluate() output in the registry's long schema: a coverage row and a pinball row per group x method x attempt.
    cell = '<method>|attempt<k>'. Primary = the verdict rows: garch_t_fhs coverage, ALL OOS and dip state, in each attempt."""
    rows = []
    for _, r in res.iterrows():
        cell = f"{r['method']}|attempt{int(r['attempt'])}"
        base = {"cell": cell, "group": r["group"], "period": "OOS", "horizon": H, "n": int(r["n"])}
        prim = r["method"] == "garch_t_fhs" and r["group"] in VERDICT_GROUPS
        rows.append({**base, "stat": "coverage", "estimate": r["coverage"], "lo": r["cov_lo"], "hi": r["cov_hi"], "primary": prim})
        rows.append({**base, "stat": "pinball", "estimate": r["pinball"], "primary": False})
    return pd.DataFrame(rows)


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
- Registered as spec `{meta['spec_hash']}` before any origin was computed (`spec_forecast.json`, `registry.csv`); {meta['planned_cells']} cells logged in `trials_all.csv`.
- **Out-of-sample period used before:** {meta['oos_reuse']}
{('- **Earlier incomplete runs:** ' + meta['incomplete']) if meta['incomplete'] else ''}

## Design
- Universe: {meta['n_stocks']} stocks (current constituents), history {meta['first']} to {meta['last']}. Origins every 21 trading days per stock, model refitted on data up to the origin only (trailing 750 returns, min 400); {meta['n_origins']} origins in total, {meta['n_fallback']} ({pct(meta['fb_rate'])}) used the EWMA fallback because GARCH did not converge.
- Split: backtest.py `shared_cutoff` (dates from {meta['start_date']}, {meta['oos_fraction']:.0%} out of sample) -> in-sample ends {meta['cutoff']}. In-sample origins whose 21-day outcome ends after the cutoff are dropped (purge). Out-of-sample: {meta['n_oos']} origins (scored only; k was fitted on {meta['n_is']} in-sample origins).
- Dip state at the origin: {meta['dip_text']}; {meta['n_oos_dip']} OOS origins.
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--reuse", action="store_true", help="reuse origins.csv.gz in the output folder")
    ap.add_argument("--limit", type=int, default=0, help="only the first N tickers (smoke test)")
    ap.add_argument("--out-root", default=str(ROOT / "output" / "backtests"), help="holds registry.csv and trials_all.csv")
    ap.add_argument("--out", default=None, help="run folder (default <out-root>/<today>_forecast)")
    a = ap.parse_args(argv)
    out_root = Path(a.out_root)
    out = Path(a.out) if a.out else out_root / f"{date.today().isoformat()}_forecast"
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
    s = load_settings()
    all_dates = shared_calendar(prices, s.backtest.start_date)
    cutoff = shared_cutoff(prices, s)
    spec = forecast_spec(Path(a.raw), list(prices), cutoff, a.limit, f"forecast_{date.today().isoformat()}", s)
    p = out / "origins.csv.gz"
    meta_p = out / META_FILE
    if a.limit and out_root.resolve() == DEFAULT_ROOT.resolve():
        print("refused: --limit is a smoke test and must not be registered in the real ledger; pass --out-root <scratch folder>.")
        return 2
    if a.reuse and p.exists():
        have = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else None
        if have != origins_meta(spec):
            print(f"refused: --reuse needs {META_FILE} next to origins.csv.gz matching this run's spec hash, raw-file hash, limit and cutoff "
                  f"({'missing' if have is None else 'differs'}). Run without --reuse.")
            return 2
    oos_dates = [d for d in all_dates if d > cutoff]
    attach_provenance(spec, s)                                                   # not hashed; set before register so the archive holds it
    reg = registry.register("forecast", spec, out, out_root, fields={"oos_start": oos_dates[0], "oos_end": oos_dates[-1]})   # BEFORE any origin
    spec["registration"] = registry.registration_block(reg)                                                                 # not hashed
    (out / "spec_forecast.json").write_text(json.dumps(spec, indent=2, default=str), encoding="utf-8")
    print(f"spec {reg.spec_hash} registered. {reg.reuse_note()}")

    if a.reuse and p.exists():
        df = pd.read_csv(p, parse_dates=["origin", "end"])
        spf = float(pd.read_csv(out / "timing.csv").spf.iloc[0]) if (out / "timing.csv").exists() else float("nan")
    else:
        print(f"Walk-forward over {len(prices)} stocks with {a.workers} workers...", flush=True)
        df, spf = build_origins(reg, prices, {t: origin_dips(c, s) for t, c in prices.items()}, a.workers)                       # written below, after the trial cells are logged
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
    registry.record_trials(reg, trial_rows(res))                       # ledger first, then any result file
    if not (a.reuse and p.exists()):
        df.drop(columns=["group"]).to_csv(p, index=False)
        pd.DataFrame({"spf": [spf]}).to_csv(out / "timing.csv", index=False)
        meta_p.write_text(json.dumps(origins_meta(spec), indent=2), encoding="utf-8")
    res.to_csv(out / "results.csv", index=False)
    chart(res, out / "calibration.png")
    meta = {"today": date.today().isoformat(), "n_stocks": df.ticker.nunique(), "first": min(c.index[0] for c in prices.values()).date(),
            "last": max(all_dates).date(), "n_origins": len(df), "n_fallback": int(df.fallback.sum()), "fb_rate": df.fallback.mean(),
            "cutoff": cutoff.date(), "n_oos": len(oos), "n_is": len(ins), "n_oos_dip": int(oos.dip.sum()),
            "n_oos_months": oos.origin.dt.strftime("%Y-%m").nunique(), "sec_per_fit": spf, "sec_per_stock_now": sec_now,
            "dip_text": dip_text(s), "start_date": s.backtest.start_date, "oos_fraction": s.backtest.oos_fraction,
            "spec_hash": reg.spec_hash, "planned_cells": PLANNED_CELLS, "oos_reuse": reg.reuse_note(), "incomplete": reg.incomplete_earlier}
    write_report(out, res, meta, v1, v2, ship)
    registry.mark_complete(reg)
    print(ship)
    print(v1)
    print(v2)
    print(f"k={ks2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
