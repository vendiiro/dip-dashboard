"""Run the backtest end to end: freeze the spec, then compute, then write spec / data check / events / results / trial log / report.

The order matters (backtest-hygiene rule 1): spec.json is written BEFORE any return is computed, so the rule, the universe,
the split and the one primary hypothesis cannot be adjusted after seeing results. Every headline cell is appended to
output/backtests/trials.csv, including runs that repeat an unchanged spec.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, replace
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import (EU, PERIODS, US, VARIANTS, Cell, add_events, add_peer_returns, add_periods, build_days, run_cells,
                       split_cutoff)
from .config import Settings, Stock
from .validate import validate_prices

INDEX_SYMBOLS = {US: "^GSPC", EU: "^STOXX"}
PRIMARY = {"variant": "V1_price_only", "horizon": 21, "group": "All", "period": "OOS", "baseline": "own"}
PRIMARY_TEXT = ("For the price-only dip rule (V1), after the cooldown, the mean 21-trading-day forward return (entry at the next close), "
                "minus the same stock's mean 21-day return on its non-dip days in the same period, is greater than zero in the "
                "out-of-sample period (the last 40% of trading dates), all regions pooled, before costs. It counts as supported only if "
                "the 90% month-clustered bootstrap interval excludes zero. Every other cell in the report is descriptive.")
SENSITIVITY_COSTS = (1, 2, 4)


def sha256(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean_bars(close: pd.Series, volume: pd.Series | None) -> tuple[pd.Series, int]:
    """Drop bars that did not trade (volume exactly 0). In the 2008-2026 history these are exchange-holiday placeholder rows with an
    unchanged price, plus one corrupt bar (NOVO-B.CO 2010-05-14: price doubled, volume 0). Missing volume is not treated as zero.
    Returns (clean close, number of bars removed)."""
    c = close.dropna()
    if volume is None:
        return c, 0
    v = volume.reindex(c.index)
    keep = ~(v == 0)
    return c[keep], int((~keep).sum())


REVISIONS = [
    "Run 1 (spec 90205cfc6da3a007) was a full run that included the out-of-sample primary cell, so the freeze is 'before the first run', not before anyone saw a number. "
    "Its spec file was overwritten by the next run (only the hash survives in trials.csv); specs are now archived by hash.",
    "Placebo: the independent same-stock same-year draw ignores that events share dates and gave p = 0.002 beside an interval that included zero. "
    "A date-shift placebo that moves all events by one common lag replaced it; the independent one stays in results.csv as 'placebo_*'. This lowered significance.",
    "Baseline and placebo days must have a computable signal (252 bars of history); before, a stock's first year counted as 'non-dip'. No predictable direction; the primary cell did not move.",
    "92 zero-volume bars were removed before the run (91 exchange-holiday placeholders and one corrupt price). They were all in sample.",
    "Later runs with the same analysis (same numbers) only changed report charts and wording, so trials.csv shows several runs per spec.",
    "Found by the independent review and NOT acted on in the numbers: one more bad price (KNEBV.HE 2025-07-29) creates one false out-of-sample event; removing it moves the primary excess from +0.2660% to +0.2667%.",
]


def freeze_spec(s: Settings, universe: list[Stock], data_meta: dict, calendar) -> dict:
    """Everything that defines the test, with a hash. Built from inputs only; no returns are involved."""
    bt = s.backtest
    spec = {
        "rule": {"dip": asdict(s.dip), "falling_knife": asdict(s.falling_knife), "quality": asdict(s.quality),
                 "dip_definition": "1-day <= -drop_1d OR 5-day <= -drop_5d OR close >= drawdown_20d below its 20-day high; needs 252 bars of history"},
        "variants": VARIANTS,
        "universe": {"n": len(universe), "tickers": [u.ticker for u in universe],
                     "bias": "current constituents only: survivorship bias; delisted names are missing"},
        "data": data_meta,
        "indices": INDEX_SYMBOLS,
        "entry": "next close after the signal bar (the signal uses data up to and including the signal bar's close)",
        "exit": "h trading bars after entry; h in horizons",
        "horizons": list(bt.horizons), "cooldown_bars": bt.cooldown_days,
        "costs": {"roundtrip": bt.cost_roundtrip, "sensitivity_multiples": list(SENSITIVITY_COSTS),
                  "note": "subtracted from event returns; baselines are compared before costs on both sides"},
        "split": {"oos_fraction": bt.oos_fraction, "cutoff": str(split_cutoff(calendar, bt.oos_fraction).date()), "purge": "in-sample events whose exit is after the cutoff are dropped"},
        "baselines": ["own: same stock, non-dip days with a computable signal, same period", "index: ^GSPC (US) / ^STOXX (Europe+Nordic), same dates, not FX adjusted",
                      "peers: mean of all other universe stocks the same signal date",
                      "date-shift placebo: all events moved by one common random lag of 70-400 bars, paired comparison (keeps clusters)",
                      "independent placebo: same stock, random non-dip day of the same year (ignores clustering; reference only)"],
        "revisions_after_first_look": REVISIONS,
        "stress": {"definition": "regional index closes >= stress_drawdown below its trailing stress_window-bar high", "drawdown": bt.stress_drawdown, "window": bt.stress_window},
        "uncertainty": {"method": "bootstrap resampling calendar months", "draws": bt.bootstrap_draws, "level": bt.ci_level, "placebo_draws": bt.placebo_draws, "seed": bt.seed},
        "primary_hypothesis": PRIMARY_TEXT, "primary_cell": PRIMARY,
        "headline_trials": len(VARIANTS) * len(bt.horizons),
        "cells_computed": len(VARIANTS) * len(bt.horizons) * 3 * len(PERIODS),
        "sample_notes": "events touching a >40% one-day move stay in the main numbers and are also reported without them",
    }
    notes = {"revisions_after_first_look", "sample_notes"}                                 # descriptive text must not change the identity of the analysis
    spec["spec_hash"] = hashlib.sha256(json.dumps({k: v for k, v in spec.items() if k not in notes}, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return spec


def append_trials(path: Path, spec: dict, results: pd.DataFrame, run_at: str) -> None:
    """Append EVERY computed cell (variant x horizon x region x period) to the running trial log, so the log counts what was looked at."""
    keep = results[results["n"] > 0]
    cols = ["run_at", "spec_hash", "variant", "horizon", "group", "period", "n", "ex_own", "ex_own_lo", "ex_own_hi", "primary"]
    if path.exists() and path.read_text(encoding="utf-8").splitlines()[:1] != [",".join(cols)]:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")                           # never mix two column layouts in one file
        path.rename(path.with_name(f"{path.stem}_older_layout_{stamp}{path.suffix}"))
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        if new:
            w.writerow(cols)
        for _, r in keep.iterrows():
            prim = all(r[k] == v for k, v in PRIMARY.items() if k in r.index)
            w.writerow([run_at, spec["spec_hash"], r["variant"], int(r["horizon"]), r["group"], r["period"], int(r["n"]),
                        *(f"{r[c]:.6f}" for c in ("ex_own", "ex_own_lo", "ex_own_hi")), prim])


def validate_history(prices: dict, today: date, s: Settings, volumes: dict | None = None) -> pd.DataFrame:
    rows = []
    for t, c in prices.items():
        for i in validate_prices(t, c, today, s.data.max_stale_trading_days, (volumes or {}).get(t)):
            rows.append({"ticker": i.ticker, "check": i.check, "severity": i.severity, "detail": i.detail})
    return pd.DataFrame(rows, columns=["ticker", "check", "severity", "detail"])


def run_backtest(prices: dict, index_close: dict, universe: list[Stock], quality: dict, s: Settings, out_dir: Path,
                 data_meta: dict, trials_path: Path | None = None, today: date | None = None, volumes: dict | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    today = today or date.today()
    calendar = sorted({d for c in prices.values() for d in c.index if d >= pd.Timestamp(s.backtest.start_date)})
    spec = freeze_spec(s, universe, data_meta, calendar)
    text = json.dumps(spec, indent=2, default=str)
    (out_dir / "spec.json").write_text(text, encoding="utf-8")                                    # written before any result exists
    archived = out_dir / f"spec_{spec['spec_hash']}.json"
    if not archived.exists():                                                                       # never overwrite an earlier spec
        archived.write_text(text, encoding="utf-8")
    run_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    validation = validate_history(prices, today, s, volumes)
    validation.to_csv(out_dir / "data_validation.csv", index=False)

    days = build_days(prices, universe, index_close, s, quality)
    days = add_peer_returns(add_events(days, s), s.backtest.horizons)
    days, cutoff = add_periods(days, s)
    assert str(cutoff.date()) == spec["split"]["cutoff"], "split moved after the spec was frozen"
    results = run_cells(days, s)
    results.to_csv(out_dir / "results.csv", index=False)
    evcols = [c for c in days.columns if c.startswith("ev_")]
    ev = days[days[evcols].any(axis=1)]
    keep = ["ticker", "region", "group", "date", "entry_date", "f1", "f5", "f20", "knife", "q", "stress", *evcols] + \
           [f"{p}{h}" for h in s.backtest.horizons for p in ("fwd", "mae", "idx", "ew", "period", "suspect")]
    ev[keep].to_csv(out_dir / "events.csv", index=False)
    tpath = trials_path or out_dir.parent / "trials.csv"
    append_trials(tpath, spec, results, run_at)
    trial_runs = int(pd.read_csv(tpath)["run_at"].nunique())
    return {"spec": spec, "days": days, "results": results, "validation": validation, "cutoff": cutoff, "run_at": run_at,
            "n_series": len(prices), "trial_runs": trial_runs}
