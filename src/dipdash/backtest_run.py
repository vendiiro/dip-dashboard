"""Run the backtest end to end: freeze the spec, register it, then compute, then write data check / events / results / trial log.

The order matters (backtest-hygiene rule 1): the spec is registered (registry.register: spec_<hash>.json + a row in
output/backtests/registry.csv) BEFORE any return is computed, so the rule, the universe, the split and the one primary
hypothesis cannot be adjusted after seeing results. Every computed cell (all of them, empty ones included) is appended to
output/backtests/trials_all.csv through registry.record_trials, including runs that repeat an unchanged spec.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import (EU, PERIODS, US, VARIANTS, Cell, add_events, add_peer_returns, add_periods, build_days, run_cells,
                       split_cutoff)
from . import registry
from .backtest_notes import revisions_for
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


# NOTE: if the backtest ever starts using these keys, remove them from this exclusion first, or the spec hash will not change
# and the frozen spec would silently misdescribe the test.
QUALITY_LABEL_KEYS = ("must_pass", "distorted_roe_above", "not_applicable", "debt_to_equity_max_by_sector")


def freeze_spec(s: Settings, universe: list[Stock], data_meta: dict, calendar) -> dict:
    """Everything that defines the test, with a hash. Built from inputs only; no returns are involved."""
    bt = s.backtest
    # must_pass and distorted_roe_above are labelling definitions used by the dashboard, not tested filters: the backtest's V3
    # uses the raw score vs min_score. Keeping them out keeps existing spec hashes (incl. the published sample) reproducible.
    quality = {k: v for k, v in asdict(s.quality).items() if k not in QUALITY_LABEL_KEYS}
    spec = {
        "rule": {"dip": asdict(s.dip), "falling_knife": asdict(s.falling_knife), "quality": quality,
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
        "revisions_after_first_look": [],                                                  # filled from backtest_notes once the hash is known
        "stress": {"definition": "regional index closes >= stress_drawdown below its trailing stress_window-bar high", "drawdown": bt.stress_drawdown, "window": bt.stress_window},
        "uncertainty": {"method": "bootstrap resampling calendar months", "draws": bt.bootstrap_draws, "level": bt.ci_level, "placebo_draws": bt.placebo_draws, "seed": bt.seed},
        "primary_hypothesis": PRIMARY_TEXT, "primary_cell": PRIMARY,
        "headline_trials": len(VARIANTS) * len(bt.horizons),
        "cells_computed": len(VARIANTS) * len(bt.horizons) * 3 * len(PERIODS),
        "sample_notes": "events touching a >40% one-day move stay in the main numbers and are also reported without them",
    }
    spec["spec_hash"] = registry.hash_for("backtest", spec)                             # notes keys are excluded: text never changes the identity
    spec["revisions_after_first_look"] = revisions_for(spec["spec_hash"])               # notes for exactly this hash; none for a new spec
    return spec


def primary_history(root: Path) -> list[dict]:
    """The primary cell as logged in every backtest run in trials_all.csv: run_at, spec_hash, n, ex_own. Used so the report only says
    'identical in every run' when the log shows it."""
    log = registry.read_trials(root)
    prim = log[(log["kind"] == "backtest") & log["primary"]]
    return [{"run_at": r["run_at"], "spec_hash": r["spec_hash"], "n": int(r["n"]), "ex_own": float(r["estimate"])} for _, r in prim.iterrows()]


def trial_rows(results: pd.DataFrame) -> pd.DataFrame:
    """Every computed cell (variant x horizon x region x period) in the registry's long schema, empty cells included, so the log
    counts what was looked at and matches the planned cell count."""
    prim = np.ones(len(results), dtype=bool)
    for k, v in PRIMARY.items():
        if k in results.columns:
            prim &= (results[k] == v).to_numpy()
    return pd.DataFrame({"cell": results["variant"], "stat": "ex_own", "group": results["group"], "period": results["period"],
                         "horizon": results["horizon"].astype(int), "n": results["n"].fillna(0).astype(int),
                         "estimate": results["ex_own"].where(results["n"] > 0), "lo": results["ex_own_lo"].where(results["n"] > 0),
                         "hi": results["ex_own_hi"].where(results["n"] > 0), "primary": prim})


def validate_history(prices: dict, today: date, s: Settings, volumes: dict | None = None) -> pd.DataFrame:
    rows = []
    for t, c in prices.items():
        for i in validate_prices(t, c, today, s.data.max_stale_trading_days, (volumes or {}).get(t)):
            rows.append({"ticker": i.ticker, "check": i.check, "severity": i.severity, "detail": i.detail})
    return pd.DataFrame(rows, columns=["ticker", "check", "severity", "detail"])


def run_backtest(prices: dict, index_close: dict, universe: list[Stock], quality: dict, s: Settings, out_dir: Path,
                 data_meta: dict, root: Path | None = None, today: date | None = None, volumes: dict | None = None) -> dict:
    """root: folder holding registry.csv and trials_all.csv (default: out_dir's parent, i.e. output/backtests)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    root = Path(root) if root is not None else out_dir.parent
    today = today or date.today()
    calendar = sorted({d for c in prices.values() for d in c.index if d >= pd.Timestamp(s.backtest.start_date)})
    spec = freeze_spec(s, universe, data_meta, calendar)
    cut = pd.Timestamp(spec["split"]["cutoff"])
    oos = [d for d in calendar if d > cut]
    reg = registry.register("backtest", spec, out_dir, root,                                       # before any result exists
                            fields={"family_id": registry.BACKTEST_FAMILY, "oos_start": oos[0], "oos_end": oos[-1]})
    spec["registration"] = registry.registration_block(reg)                                         # not hashed
    (out_dir / "spec.json").write_text(json.dumps(spec, indent=2, default=str), encoding="utf-8")   # the latest spec, beside the archive
    earlier = registry.earlier_specs("backtest", root, exclude=reg.spec_hash, before=reg.registered_at)
    run_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    registry.require_registered(reg)                                                                # compute entry point: token required
    validation = validate_history(prices, today, s, volumes)
    days = build_days(prices, universe, index_close, s, quality)
    days = add_peer_returns(add_events(days, s), s.backtest.horizons)
    days, cutoff = add_periods(days, s)
    assert str(cutoff.date()) == spec["split"]["cutoff"], "split moved after the spec was frozen"
    results = run_cells(days, s)
    registry.record_trials(reg, trial_rows(results))                                                # ledger first, then any result file
    validation.to_csv(out_dir / "data_validation.csv", index=False)
    results.to_csv(out_dir / "results.csv", index=False)
    evcols = [c for c in days.columns if c.startswith("ev_")]
    ev = days[days[evcols].any(axis=1)]
    keep = ["ticker", "region", "group", "date", "entry_date", "f1", "f5", "f20", "knife", "q", "stress", *evcols] + \
           [f"{p}{h}" for h in s.backtest.horizons for p in ("fwd", "mae", "idx", "ew", "period", "suspect")]
    ev[keep].to_csv(out_dir / "events.csv", index=False)
    registry.mark_complete(reg)
    log = registry.read_trials(root)
    trial_runs = int(log.loc[log["kind"] == "backtest", "run_at"].nunique())          # run key = registered_at (microseconds)
    return {"spec": spec, "days": days, "results": results, "validation": validation, "cutoff": cutoff, "run_at": run_at,
            "n_series": len(prices), "trial_runs": trial_runs, "primary_history": primary_history(root),
            "earlier_specs": [{"spec_hash": h} for h in earlier], "oos_reuse": reg.reuse_note(), "incomplete_earlier": reg.incomplete_earlier, "registration": reg}
