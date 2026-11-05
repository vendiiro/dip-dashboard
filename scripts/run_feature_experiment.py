#!/usr/bin/env python3
"""Run the pre-registered price-feature experiment (family features_<date>) from a cached history. No network.

    .venv/Scripts/python.exe scripts/run_feature_experiment.py --raw path/to/2026-11-04.csv.gz

Order: load bars -> compute the split cutoff from dates only -> freeze the spec and register it (registry.register:
spec_<hash>.json + a row in output/backtests/registry.csv) and write spec_features.json -> only then build events, features,
target and correlations. Every cell goes to output/backtests/trials_all.csv through registry.record_trials (the older
trials_features.csv is frozen; `python -m dipdash.registry backfill` imports it once).
"""
import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dipdash.backtest import Cell, add_events, add_periods, build_days, cell_events, group_of, split_cutoff  # noqa: E402
from dipdash.backtest_run import clean_bars, sha256  # noqa: E402
from dipdash import registry  # noqa: E402
from dipdash.cache import load_raw_prices  # noqa: E402
from dipdash.config import load_settings, load_universe  # noqa: E402
from dipdash.provenance import build_provenance  # noqa: E402
from dipdash.feature_experiment import (FAMILY, FEATURES, Settings, compute_features, demeaned_target, evaluate_features,  # noqa: E402
                                        freeze_spec, mde, planned_cells)

PARENT_SPEC = "8583ea959c7ce228"
PARENT_OOS_N = 4409
H = 21


def truncation_check(close: pd.Series, volume, feats: pd.DataFrame, positions: list[int]) -> int:
    """Recompute the features on data cut at bar t and require identical values at t. Returns the number of checks passed."""
    n = 0
    for i in positions:
        cut = compute_features(close.iloc[: i + 1], None if volume is None else volume.iloc[: i + 1]).iloc[-1]
        full = feats.iloc[i]
        assert np.allclose(cut.to_numpy(float), full.to_numpy(float), equal_nan=True), f"look-ahead at bar {i}"
        n += 1
    return n


def trial_rows(res: pd.DataFrame) -> pd.DataFrame:
    """evaluate_features output in the registry's long schema. The six pooled OOS Spearman rows (the Holm family) are primary."""
    fam = (res["stat"] == "spearman") & (res["period"] == "OOS") & (res["group"] == "All")
    return pd.DataFrame({"cell": res["feature"], "stat": res["stat"], "group": res["group"], "period": res["period"], "horizon": H,
                         "n": res["n"], "estimate": res["est"], "lo": res["lo"], "hi": res["hi"], "p_raw": res["p"],
                         "p_holm": res["p_holm"], "primary": fam})


def build_event_table(reg, prices: dict, universe, calendar: list, s, cutoff) -> tuple[pd.DataFrame, dict]:
    """The first place forward returns are computed. Needs the Registration token: no registration, no computing."""
    registry.require_registered(reg)
    dummy = pd.Series(100.0, index=pd.DatetimeIndex(calendar))
    days = build_days(prices, universe, {"US": dummy, "Europe+Nordic": dummy}, s, None)
    days = add_events(days, s)
    days, cut2 = add_periods(days, s)
    assert cut2 == cutoff
    sanity = {"oos_n": len(cell_events(days, Cell("V1_price_only", H, "All", "OOS")))}
    days["target"] = demeaned_target(days, H)
    return days, sanity


def forest(res: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = res[(res["stat"] == "spearman") & (res["period"] == "OOS") & (res["group"] == "All")].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    y = np.arange(len(d))[::-1]
    ax.errorbar(d["est"], y, xerr=[d["est"] - d["lo"], d["hi"] - d["est"]], fmt="o", color="#1f4e79", ecolor="#1f4e79", capsize=3)
    ax.axvline(0, color="#555", lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{f}  (IS sign {int(s):+d})" for f, s in zip(d["feature"], d["sign_is"])], fontsize=8)
    ax.set_xlabel("Out-of-sample Spearman rho with date-demeaned 21d forward return (90% month-clustered interval)")
    ax.set_title("Six price features, out-of-sample rank correlation (no multiplicity adjustment shown)", fontsize=9)
    ax.xaxis.label.set_size(8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fmt(v, d=3):
    return "n/a" if pd.isna(v) else f"{v:+.{d}f}"


def write_report(path: Path, spec: dict, res: pd.DataFrame, counts: dict, sanity: dict, run_at: str, reuse: str = "", incomplete: str = "") -> None:
    fam = res[(res["stat"] == "spearman") & (res["period"] == "OOS") & (res["group"] == "All")].set_index("feature")
    isr = res[(res["period"] == "IS")].set_index("feature")
    terc = res[(res["stat"] == "tercile_top_minus_bottom") & (res["group"] == "All")].set_index("feature")
    any_sup = bool(fam["supported"].any())
    L = [f"# Price-feature experiment, family `{spec['family_id']}` (spec `{spec['spec_hash']}`)", "",
         f"Run {run_at}. Descriptive research screen; not investment advice. Spec written before any correlation: `spec_features.json`.", "",
         "## Result", ""]
    if any_sup:
        sup = ", ".join(fam.index[fam["supported"]])
        L.append(f"In this sample, after Holm correction across 6 features, the out-of-sample rank correlation was distinguishable from zero for: {sup}. "
                 "This is a statement about a rank correlation in this sample (current constituents, overlapping months), not about tradability.")
    else:
        L.append("No tested price feature shows detectable out-of-sample signal in this sample: none survives Holm correction across the 6. "
                 "The dashboard remains a listing and monitoring tool.")
    L += ["", f"Events: V1 price-only dip events, 21d horizon, 171-stock universe ({spec['universe']['n']} names listed, current constituents). "
          f"Reproduction check: out-of-sample events {sanity['oos_n']:,} vs {PARENT_OOS_N:,} in backtest spec {PARENT_SPEC} "
          f"({'matches' if sanity['oos_n'] == PARENT_OOS_N else 'DOES NOT MATCH'}). Split cutoff {spec['split']['cutoff_last_in_sample_date']}; "
          f"in-sample events used {counts['IS']:,} (purged dropped), out-of-sample {counts['OOS']:,} (US {counts['OOS_US']:,}, Europe+Nordic {counts['OOS_EU']:,}).", "",
          f"**Out-of-sample period used before:** {reuse or 'not checked (this run was not registered)'}", "",
          *([f"**Earlier incomplete runs:** {incomplete}", ""] if incomplete else []),
          "## Out-of-sample Spearman rho (pooled), 90% month-clustered interval", "",
          "| feature | IS rho (sign only) | OOS n | OOS rho | 90% interval | raw p | Holm p | MDE (80% power) | supported |",
          "|---|---|---|---|---|---|---|---|---|"]
    for f in FAMILY:
        r = fam.loc[f]
        L.append(f"| {f} | {fmt(isr.loc[f, 'est'])} | {int(r['n'])} | {fmt(r['est'])} | [{fmt(r['lo'])}, {fmt(r['hi'])}] | {r['p']:.4f} | {r['p_holm']:.4f} | {r['mde_80']:.3f} | {'yes' if r['supported'] else 'no'} |")
    mdes = fam["mde_80"]
    L += ["", f"Minimum detectable effect: with these intervals only a true rank correlation of about {mdes.min():.3f} to {mdes.max():.3f} "
          "(or larger, in absolute value) would be detected 80% of the time at the two-sided 10% level before any Holm adjustment; under the strictest Holm step "
          "(10%/6) it is about 20% larger. A smaller true rho cannot be resolved by this sample. Absence of a detected signal is not evidence of absence.", "",
          "![forest](forest_features.png)", "",
          "## Top-minus-bottom tercile difference in mean 21d target (descriptive, not in the Holm family)", "",
          "Cut points from in-sample events only. Raw difference (top tercile of the feature minus bottom), out-of-sample, in return units.", "",
          "| feature | IS sign | top - bottom | 90% interval |", "|---|---|---|---|"]
    for f in FAMILY:
        r = terc.loc[f]
        L.append(f"| {f} | {int(r['sign_is']):+d} | {r['est'] * 100:+.2f}% | [{r['lo'] * 100:+.2f}%, {r['hi'] * 100:+.2f}%] |")
    L += ["", "## Region split (EXPLORATORY, descriptive only; not tested, not corrected)", "",
          "| feature | US n | US rho [90%] | Europe+Nordic n | EU rho [90%] |", "|---|---|---|---|---|"]
    reg = res[(res["stat"] == "spearman") & (res["period"] == "OOS")]
    for f in FAMILY:
        u = reg[(reg.feature == f) & (reg.group == "US")].iloc[0]
        e = reg[(reg.feature == f) & (reg.group == "Europe+Nordic")].iloc[0]
        L.append(f"| {f} | {int(u['n'])} | {fmt(u['est'])} [{fmt(u['lo'])}, {fmt(u['hi'])}] | {int(e['n'])} | {fmt(e['est'])} [{fmt(e['lo'])}, {fmt(e['hi'])}] |")
    L += ["", "## How much to trust this", "",
          "- Survivorship bias: the universe is today's constituents; names that fell and were removed or delisted are missing, which can distort any dip-related relation.",
          "- Non-independence: events bunch in market-wide selloffs (2020, 2022). Months are the resampling unit; with a few dozen OOS months the intervals are wide and the effective sample is far smaller than the event count.",
          "- Costs are not applied because a rank correlation has no trade or cost; nothing here is a return after costs, and nothing says a screen is tradable.",
          "- The target removes only the same-day universe mean; sector, size and beta effects remain. The event stock is included in its own date mean (171 names, small effect).",
          "- Overlapping 21-day windows within a month and across nearby months make neighbouring events share returns.",
          "- Six features were tested once each, signs fixed in-sample, one OOS look; no variants and no tuning. The OOS period was used for nothing else in this experiment, but the dip rule itself and the 60/40 split come from earlier work on the same history.",
          "- Prices are dividend-adjusted closes from Yahoo; bad ticks can remain (the backtest removed only zero-volume bars).",
          f"- Trials: {len(FAMILY)} family tests plus descriptive cells ({planned_cells()} cells per run) are logged in `output/backtests/trials_all.csv` "
          f"(family `{spec['family_id']}`); the registration and its out-of-sample window are in `output/backtests/registry.csv`.", ""]
    path.write_text("\n".join(L), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True, help="cached history .csv.gz (data/raw/yfinance_backtest/<date>.csv.gz)")
    ap.add_argument("--out-root", default=str(ROOT / "output" / "backtests"))
    ap.add_argument("--draws", type=int, default=None)
    a = ap.parse_args(argv)
    raw = Path(a.raw)
    if not raw.exists():
        print(f"history file missing: {raw}")
        return 2
    s, universe = load_settings(), load_universe()
    today = date.today().isoformat()
    family_id = f"features_{today}"
    out_dir = Path(a.out_root) / f"{today}_features"
    out_dir.mkdir(parents=True, exist_ok=True)

    bars = load_raw_prices(raw)
    prices, volumes = {}, {}
    for t, (c, v) in bars.items():
        c2, _ = clean_bars(c, v)
        if len(c2):
            prices[t] = c2
            volumes[t] = v.reindex(c2.index) if v is not None else None
    calendar = sorted({d for c in prices.values() for d in c.index if d >= pd.Timestamp(s.backtest.start_date)})
    cutoff = split_cutoff(calendar, s.backtest.oos_fraction)
    boot = {"method": "bootstrap resampling calendar months (whole months with replacement), rank correlation recomputed per draw",
            "draws": a.draws or s.backtest.bootstrap_draws, "level": s.backtest.ci_level, "seed": s.backtest.seed + 2100}
    parent = {"spec_hash": PARENT_SPEC, "raw_file": raw.name, "raw_sha256": sha256(raw),
              "universe_sha256": sha256(ROOT / "config" / "universe.csv"), "n_series": len(prices)}
    rule = {"dip": asdict(s.dip), "falling_knife": asdict(s.falling_knife), "cooldown_days": s.backtest.cooldown_days,
            "start_date": s.backtest.start_date, "horizons": list(s.backtest.horizons)}      # used by build_event_table; was only in the file hash
    spec = freeze_spec(parent, str(cutoff.date()), len(universe), family_id, boot, rule)
    oos_dates = [d for d in calendar if d > cutoff]
    spec["provenance"] = build_provenance(s, ROOT / "src" / "dipdash")                      # not hashed; set before register so the archive holds it
    reg = registry.register("features", spec, out_dir, Path(a.out_root),                   # BEFORE any return or correlation
                            fields={"oos_start": oos_dates[0], "oos_end": oos_dates[-1], "horizons": [H], "planned_cells": planned_cells()})
    spec["registration"] = registry.registration_block(reg)                                 # not hashed
    (out_dir / "spec_features.json").write_text(json.dumps(spec, indent=2, default=str), encoding="utf-8")
    print(reg.reuse_note())
    print(f"spec {spec['spec_hash']} written; cutoff {cutoff.date()}")

    days, sanity = build_event_table(reg, prices, universe, calendar, s, cutoff)
    print(f"reproduction: OOS V1 21d events {sanity['oos_n']} (parent {PARENT_OOS_N})")
    ev = days[days["ev_V1_price_only"] & days[f"fwd{H}"].notna() & days[f"period{H}"].isin(["IS", "OOS"])].copy()
    ev["period"] = ev[f"period{H}"]

    feats, checks = [], 0
    rng = np.random.default_rng(7)
    for t, g in ev.groupby("ticker"):
        c, v = prices[t], volumes[t]
        fr = compute_features(c, v)
        pos = c.index.get_indexer(g["date"])
        assert (pos >= 0).all()
        pick = rng.choice(pos, size=min(len(pos), 2), replace=False)
        checks += truncation_check(c, v, fr, [int(p) for p in pick])
        part = fr.iloc[pos].copy()
        part.index = g.index
        feats.append(part)
    ev = ev.join(pd.concat(feats))
    print(f"look-ahead truncation checks passed: {checks}")

    cfg = Settings(draws=boot["draws"], level=boot["level"], seed=boot["seed"])
    registry.require_registered(reg)
    res = evaluate_features(ev, cfg)
    run_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    registry.record_trials(reg, trial_rows(res))                                            # ledger first, then any result file
    res.to_csv(out_dir / "results.csv", index=False)
    keep = ["ticker", "region", "group", "date", "entry_date", "period", f"fwd{H}", "target", *FAMILY]
    ev[keep].to_csv(out_dir / "events_features.csv", index=False)
    counts = {"IS": int((ev.period == "IS").sum()), "OOS": int((ev.period == "OOS").sum()),
              "OOS_US": int(((ev.period == "OOS") & (ev.group == "US")).sum()), "OOS_EU": int(((ev.period == "OOS") & (ev.group == "Europe+Nordic")).sum())}
    forest(res, out_dir / "forest_features.png")
    write_report(out_dir / "report_features.md", spec, res, counts, sanity, run_at, reg.reuse_note(), reg.incomplete_earlier)
    registry.mark_complete(reg)
    print(json.dumps(counts))
    print(res[(res.stat == "spearman") & (res.period == "OOS") & (res.group == "All")][["feature", "n", "est", "lo", "hi", "p", "p_holm", "sign_is", "supported", "mde_80"]].to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
