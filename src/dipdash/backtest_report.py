"""Write report.md and its charts from a finished backtest run.

Wording rule (backtest-hygiene): describe what happened "historically, in this sample". Never say a rule works or will pay.
Every number in the text is taken from the results table, the frozen spec, the settings or the trial log; nothing is typed in by hand.
Human-written review text lives in backtest_notes.py, keyed by spec hash, and is only printed for the spec it was written for.
"""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .backtest import EU, MAX_JUMP, PERIODS, US, VARIANTS, Cell, _nondip_mask, cell_events, date_shift_placebo, shift_inputs  # noqa: E402
from .backtest_notes import notes_for, quoted_mismatch  # noqa: E402
from .backtest_run import PRIMARY, PRIMARY_TEXT, SENSITIVITY_COSTS  # noqa: E402
from .config import Settings  # noqa: E402
from .fmt import bound, interval, md_table, pct  # noqa: E402,F401

ACCENT, GREY, RED = "#4a3fb5", "#8a92a2", "#c3372f"
VNAME = {"V1_price_only": "V1 price-only", "V2_no_knife": "V2 no falling knives", "V3_quality_indicative": "V3 quality (indicative)"}


def cell(res: pd.DataFrame, variant: str, h: int, group: str, period: str) -> pd.Series | None:
    m = res[(res["variant"] == variant) & (res["horizon"] == h) & (res["group"] == group) & (res["period"] == period)]
    return m.iloc[0] if len(m) and m.iloc[0]["n"] > 0 else None


def excludes_zero(r: pd.Series, key: str = "ex_own") -> str:
    lo, hi = r.get(f"{key}_lo"), r.get(f"{key}_hi")
    if lo is None or not np.isfinite(lo):
        return "no interval"
    return "the interval excludes zero" if (lo > 0 or hi < 0) else "the interval includes zero"


# ---------------------------------------------------------------- charts
def chart_distribution(days: pd.DataFrame, s: Settings, path: Path) -> None:
    """Left: 21-day net returns after dip events vs on non-dip days (out of sample). Right: placebo means vs the observed mean."""
    c = Cell(PRIMARY["variant"], PRIMARY["horizon"], PRIMARY["group"], PRIMARY["period"])
    h, bt = c.horizon, s.backtest
    ev = cell_events(days, c)
    nd = days[_nondip_mask(days, c)]
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4), gridspec_kw={"width_ratios": [1.35, 1]})
    lim = 0.4
    bins = np.linspace(-lim, lim, 61)
    en, nn = ev[f"fwd{h}"] - bt.cost_roundtrip, nd[f"fwd{h}"] - bt.cost_roundtrip
    a.hist(np.clip(nn, -lim, lim), bins=bins, density=True, color=GREY, alpha=0.55, label=f"non-dip days (n={len(nn):,})")
    a.hist(np.clip(en, -lim, lim), bins=bins, density=True, color=ACCENT, alpha=0.6, label=f"after a dip event (n={len(en):,})")
    a.axvline(en.mean(), color=ACCENT, lw=1.6, ls="--")
    a.axvline(nn.mean(), color=GREY, lw=1.6, ls="--")
    a.axvline(0, color="black", lw=0.8)
    a.set_title(f"{h}-day return after next-close entry\nnet of {bt.cost_roundtrip:.2%} costs, out of sample", fontsize=9.5)
    a.set_xlabel(f"return (clipped at ±{lim:.0%}; dashed = mean)")
    a.yaxis.set_visible(False)
    a.legend(frameon=False, fontsize=9)
    res = date_shift_placebo(*shift_inputs(days, c, ev), bt.placebo_draws, bt.seed + h + 1000, with_draws=True)
    if res:
        d = res["placebo_minus_events"] * 100
        b.hist(d, bins=40, color=GREY, alpha=0.7)
        b.axvline(0, color=ACCENT, lw=2)
        b.set_title("Date-shift placebo: all events moved together\nby a random lag (placebo mean minus events' mean)", fontsize=9.5)
        b.set_xlabel(f"percentage points, before costs\n{res['shift_draws']:,} shifts; share at or above 0: p = {res['shift_p']:.3f}", fontsize=9)
        b.text(0, b.get_ylim()[1] * 0.97, "events' mean ", color=ACCENT, ha="right", va="top", fontsize=9)
    b.yaxis.set_visible(False)
    for ax in (a, b):
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def chart_forest(res: pd.DataFrame, s: Settings, path: Path) -> None:
    """Mean excess over each stock's own non-dip days with its interval, in-sample vs out-of-sample, every variant and horizon."""
    labels, ys = [], []
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    y = 0
    for v in VARIANTS:
        for h in s.backtest.horizons:
            for per, col, off in (("IS", GREY, 0.17), ("OOS", ACCENT, -0.17)):
                r = cell(res, v, h, "All", per)
                if r is None or not np.isfinite(r.get("ex_own_lo", np.nan)):
                    continue
                ax.errorbar(r["ex_own"] * 100, y + off, xerr=[[ (r["ex_own"] - r["ex_own_lo"]) * 100], [(r["ex_own_hi"] - r["ex_own"]) * 100]],
                            fmt="o", color=col, capsize=2.5, ms=4.5, lw=1.4, label=("in sample" if per == "IS" else "out of sample") if y == 0 else None)
            labels.append(f"{VNAME[v]}, {h}d")
            ys.append(y)
            y += 1
    ax.axvline(0, color="black", lw=0.8)
    ax.set_yticks(ys, labels, fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlabel(f"mean excess return over the stock's own non-dip days, % ({s.backtest.ci_level:.0%} month-clustered interval, before costs)")
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------- text
def earlier_specs_line(hist: list[dict], shash: str) -> str:
    """One line saying that runs under other spec hashes exist. Empty if there are none. `hist` is the registry ledger
    (registry.earlier_specs("backtest"), as [{"spec_hash": ...}]), so a run that registered and then crashed still counts.
    Printed whether or not notes exist for the current hash, so the first-look history cannot silently vanish."""
    others = list(dict.fromkeys(h_["spec_hash"] for h_ in hist if h_["spec_hash"] != shash))
    if not others:
        return ""
    names = ", ".join(f"`{o}`" for o in others[:5]) + (f" and {len(others) - 5} more" if len(others) > 5 else "")
    return (f"{len(others)} other spec hash{'es' if len(others) != 1 else ''} {'are' if len(others) != 1 else 'is'} registered (new data, universe or rule changes all alter the hash): {names}. "
            "Changes between specs are described below only where they were written into `backtest_notes.py`.")


def render_report(run: dict, s: Settings, charts: dict[str, str]) -> str:
    spec, res, days, cutoff, val = run["spec"], run["results"], run["days"], run["cutoff"], run["validation"]
    bt = s.backtest
    prim = cell(res, PRIMARY["variant"], PRIMARY["horizon"], PRIMARY["group"], PRIMARY["period"])
    prim_is = cell(res, PRIMARY["variant"], PRIMARY["horizon"], PRIMARY["group"], "IS")
    allc = cell(res, PRIMARY["variant"], PRIMARY["horizon"], PRIMARY["group"], "ALL")
    first, last = days["date"].min().date(), days["date"].max().date()
    H, ci = PRIMARY["horizon"], f"{bt.ci_level:.0%}"
    shash = spec["spec_hash"]
    notes = notes_for(shash)
    n_groups, n_variants = int(res["group"].nunique()), len(VARIANTS)
    L = []
    w = L.append
    w(f"# Dip-rule event study\n\nRun {run['run_at']} · spec `{spec['spec_hash']}` · educational research, not investment advice. "
      "Everything below describes what happened historically, in this sample.\n")
    # ---- lead
    w("## Summary\n")
    if allc is None:
        w("No events were found for the primary variant, so there is nothing to report.\n")
        return "\n".join(L)
    w(f"- **Events:** {int(allc['n']):,} price-only dip events at the {H}-day horizon after a {bt.cooldown_days}-bar cooldown, "
      f"on {int(allc['n_stocks'])} stocks, {int(allc['n_months'])} calendar months ({first} to {last}).")
    w(f"- **Universe:** {spec['universe']['n']} current blue chips (US, Europe, Nordic). Survivorship bias applies (see below).")
    w(f"- **Costs:** {bt.cost_roundtrip:.2%} round trip, also shown at 2× and 4×. Entry at the next close, no intraday fills.")
    w(f"- **Out-of-sample period:** after {cutoff.date()} (the last {bt.oos_fraction:.0%} of trading dates); in-sample events whose window crosses that date are dropped.")
    w(f"- **Out-of-sample period used before:** {run.get('oos_reuse') or 'not checked (this run was not registered)'}\n")
    w("### Pre-registered question\n")
    w(f"> {PRIMARY_TEXT}\n")
    if prim is None:
        w("There were no out-of-sample events for the primary cell.\n")
    else:
        w(f"**Result.** Out of sample, {int(prim['n']):,} events in {int(prim['n_months'])} months averaged **{pct(prim['ex_own'])}** over their own stocks' "
          f"non-dip days at {H} days ({ci} interval {interval(prim['ex_own_lo'], prim['ex_own_hi'])}); {excludes_zero(prim)}. "
          + ("In sample the same figure was " + f"{pct(prim_is['ex_own'])} ({interval(prim_is['ex_own_lo'], prim_is['ex_own_hi'])}). " if prim_is is not None else "")
          + f"Versus the regional index the figure was {pct(prim['ex_index'])} ({interval(prim['ex_index_lo'], prim['ex_index_hi'])}); versus the other stocks the same day {pct(prim['ex_peers'])} "
          f"({interval(prim['ex_peers_lo'], prim['ex_peers_hi'])}). Share of date-shifted comparisons that did as well as the real events: {prim.get('shift_p', float('nan')):.2f}. "
          "In each comparison all events are moved by the same random number of trading days. A high share means the result is easy to get by chance. "
          + (f"At most {int(prim['shift_lags']):,} distinct shifts were drawn, and neighbouring shifts overlap, so the effective number of independent shifts is much smaller; read the figure to two decimals."
             if "shift_lags" in prim.index and pd.notna(prim["shift_lags"]) else
             "Neighbouring shifts overlap, so the effective number of independent shifts is much smaller; read the figure to two decimals.") + "\n")
        lo, hi = prim["ex_own_lo"], prim["ex_own_hi"]
        if np.isfinite(lo) and lo > 0:
            w("The pre-registered condition is met in this sample. That is a statement about these dates and these stocks; the sections below list why it may not carry over.\n")
        elif np.isfinite(hi) and hi < 0:
            w("Out of sample, the events did worse than the same stocks' ordinary days, and the interval excludes zero.\n")
        else:
            w("The pre-registered condition is not met: the interval includes zero, so this sample cannot separate the result from noise.\n")
    tally = {}
    for per in ("IS", "OOS", "OOS_exstress"):
        d = res[(res["period"] == per) & (res["n"] > 0) & res["ex_own_lo"].notna()]
        tally[per] = (int(((d["ex_own_lo"] > 0) | (d["ex_own_hi"] < 0)).sum()), len(d))
    if prim is not None:
        w(f"**In sample versus out of sample.** Across {tally['IS'][1]} non-empty cells (at most {n_variants} variants × {len(bt.horizons)} horizons × {n_groups} region groups; empty cells are left out), {tally['IS'][0]} in-sample intervals for the excess over each stock's own non-dip days "
          f"exclude zero, against {tally['OOS'][0]} of {tally['OOS'][1]} out of sample ({tally['OOS_exstress'][0]} of {tally['OOS_exstress'][1]} with market-stress days removed). The cells overlap, so this is a tally, not "
          f"{tally['IS'][1]} independent tests. It does not show that the in-sample and out-of-sample results differ from each other: the out-of-sample intervals are about ±{(prim['ex_own_hi'] - prim['ex_own_lo']) / 2 * 100:.1f} points wide at {H} days, "
          "so this sample has little power to detect an edge of the size seen in sample.\n")
    w(f"![Return distribution and placebo]({charts['distribution']})\n")
    # ---- tables
    w("## Excess return over baselines, out of sample\n")
    rows = []
    for v in VARIANTS:
        for h in bt.horizons:
            r = cell(res, v, h, "All", "OOS")
            if r is None:
                rows.append([VNAME[v], f"{h}d", 0, "", "", "", "", ""])
                continue
            rows.append([VNAME[v], f"{h}d", f"{int(r['n']):,}", f"{pct(r['ex_own'])} ({interval(r['ex_own_lo'], r['ex_own_hi'])})",
                         f"{pct(r['ex_index'])} ({interval(r['ex_index_lo'], r['ex_index_hi'])})", f"{pct(r['ex_peers'])} ({interval(r['ex_peers_lo'], r['ex_peers_hi'])})",
                         f"{r.get('shift_p', float('nan')):.2f}", int(r["n_months"])])
    w(md_table(["Variant", "Horizon", "Events", "Excess vs own non-dip days", "vs regional index", "vs other stocks", "Date-shift placebo p", "Months"], rows))
    w(f"\nIntervals are {ci} bootstrap intervals that resample whole calendar months. V3 uses today's fundamentals on past dates, so it is indicative only. "
      "The index baseline is not currency-adjusted for stocks that do not trade in the index currency.\n")
    if prim is not None:
        w(f"**Reading the index column.** It is not like-for-like: the stocks are dividend-adjusted and the indices are price-only, so it also carries roughly the dividend yield (not measured). "
          f"On top of that, on ordinary (non-dip) days these same stocks beat their regional index by {pct(prim['nd_vs_idx'])} over {H} days out of sample, because the universe is today's survivors. "
          "Read 'vs regional index' with both in mind; it is the weakest of the three baselines. "
          "'vs own non-dip days' is the least distorted comparison, but survivorship can still bias even that one upward: dips that kept falling belong to companies that dropped out of the universe. "
          f"The independent random-day placebo (kept in `results.csv`) gave {prim.get('placebo_p', float('nan')):.3f} for the primary cell, but it ignores that events share dates and reads too optimistic, so it is not used.\n")
    w(f"![Excess by variant and horizon]({charts['forest']})\n")
    # ---- by horizon/region
    w("## By horizon and region (V1, price-only)\n")
    rows = []
    for h in bt.horizons:
        for g, gl in (("All", "All"), (US, "US"), (EU, "Europe + Nordic")):
            for per in ("ALL", "OOS"):
                r = cell(res, "V1_price_only", h, g, per)
                if r is None:
                    continue
                rows.append([f"{h}d", gl, "full sample" if per == "ALL" else "out of sample", f"{int(r['n']):,}", pct(r["ex_own"]), interval(r["ex_own_lo"], r["ex_own_hi"]),
                             f"{r['hit_rate']:.0%} / {r['base_hit']:.0%}", pct(r["net_median"]), pct(r["p10"]), pct(r["p90"]), pct(r["worst"])])
    w(md_table(["Horizon", "Region", "Period", "Events", "Excess (own)", f"{ci} interval", "Hit rate: events / non-dip days (net)", "Median (net)", "10th pct", "90th pct", "Worst"], rows))
    w("\nHit rate, median and percentiles are net of costs, from entry to exit. A hit rate means little alone: the same stocks' ordinary windows also end higher most of the time. "
      "Worst = the single worst event. Events overlap in time at the longer horizons.\n")
    # ---- costs
    w("## After costs (V1, out of sample)\n")
    rows = []
    for h in bt.horizons:
        r = cell(res, "V1_price_only", h, "All", "OOS")
        if r is None:
            continue
        rows.append([f"{h}d", pct(r["gross_mean"]), *(pct(r[f"net_mean_{m}x"]) for m in SENSITIVITY_COSTS), pct(r["base_own_mean"]),
                     pct((1 + r["base_own_mean"]) ** (252 / h) - 1, 0), pct(r["mae_median"]), pct(r["mae_worst"])])
    w(md_table(["Horizon", "Mean gross", *(f"Net at {m}× cost" for m in SENSITIVITY_COSTS), "Same stocks' average non-dip day", "…as a yearly rate", "Median worst dip after entry", "Worst dip after entry"], rows))
    w(f"\nThe excess figures compare events with baselines before costs on both sides, because a trader who picked random days would pay the same round trip. "
      f"1× cost is {bt.cost_roundtrip:.2%}; spreads on less liquid names, taxes and currency conversion are not modelled. "
      "**The absolute returns in this table are inflated by survivorship**: these are today's large, successful companies, and their ordinary days already returned the rate shown in the last return column. "
      "Nobody could have picked this universe in advance, so the comparison with the same stocks' ordinary days is the least distorted one (survivorship still biases even that upward).\n")
    # ---- stress
    w("## Market-wide selloffs (V1, out of sample)\n")
    rows = []
    for h in bt.horizons:
        for per, lab in (("OOS", "all out-of-sample events"), ("OOS_exstress", f"excluding days the regional index was {bt.stress_drawdown:.0%}+ below its {bt.stress_window}-day high")):
            r = cell(res, "V1_price_only", h, "All", per)
            if r is not None:
                rows.append([f"{h}d", lab, f"{int(r['n']):,}", pct(r["ex_own"]), interval(r["ex_own_lo"], r["ex_own_hi"]), pct(r["net_mean_1x"])])
    w(md_table(["Horizon", "Events", "n", "Excess (own)", f"{ci} interval", "Mean net"], rows))
    si, so = cell(res, "V1_price_only", H, "All", "IS"), cell(res, "V1_price_only", H, "All", "OOS")
    w(f"\nStress share of events: {allc['ev_stress_share']:.0%} overall"
      + (f", {si['ev_stress_share']:.0%} in sample and {so['ev_stress_share']:.0%} out of sample" if si is not None and so is not None else "")
      + ". Events cluster in market-wide selloffs, and the out-of-sample period contains " + ("more" if si is not None and so is not None and so["ev_stress_share"] > si["ev_stress_share"] else "no more") + " of them than the in-sample period.\n")
    # ---- data checks
    w("## Data checks\n")
    zv = spec["data"].get("zero_volume_bars_removed", {})
    if zv:
        w(f"- {zv['total']} zero-volume bars in {zv['tickers']} tickers were removed before the run ({zv['total'] / zv['of_bars']:.3%} of bars)."
          + ("" if notes.get("data_notes") else " No note about them is recorded for this spec."))
        for dn in notes.get("data_notes", []):
            w(f"  - {dn}")
    w(f"- {run['n_series']} price series validated after cleaning. Findings: " + (", ".join(f"{k} × {v}" for k, v in val["check"].value_counts().items()) or "none") + ".")
    big = val[val["check"].isin(["large_move", "spike_revert"])]
    for _, b_ in big.iterrows():
        when = re.search(r"\d{4}-\d{2}-\d{2}", b_["detail"])
        part = "out of sample" if when and pd.Timestamp(when.group()) > cutoff else "in sample"
        w(f"  - {b_['ticker']}: {b_['detail']} ({part}).")
    prim_events = cell_events(days, Cell("V1_price_only", H, "All", "ALL"))
    nsus = int(prim_events[f"suspect{H}"].sum())
    w(f"- {nsus} of {len(prim_events):,} primary events touch a move of more than {MAX_JUMP:.0%} in one day. They stay in the main numbers"
      + ("; the primary out-of-sample cell contains " + str(int(prim["n_suspect"])) + " of them" + (f", and without them it reads {pct(prim['ex_own_nosuspect'])} ({interval(prim['ex_own_nosuspect_lo'], prim['ex_own_nosuspect_hi'])})" if prim is not None and prim["n_suspect"] and "ex_own_nosuspect" in prim.index and pd.notna(prim["ex_own_nosuspect"]) else "") if prim is not None else "") + ".")
    w("- Prices are Yahoo's dividend-adjusted closes. They were cross-checked against exchange sources for sample tickers only (docs/m2-data-verification.md); long-history adjustments were not verified.\n")
    # ---- trials
    w("## How many things were tried\n")
    w(f"{spec['headline_trials']} headline tests ({n_variants} variants × {len(bt.horizons)} horizons) were planned, and {spec['cells_computed']} cells were computed (adding {n_groups} region groups and {len(PERIODS)} periods), each with three baselines and a placebo. "
      "The report prints a subset; `results.csv` has all of them and `output/backtests/trials_all.csv` logs every one on every run"
      + (f" ({run['trial_runs']} runs so far; several only reformatted the report)" if run.get("trial_runs") else "") + ". With this many looks, the best-looking cell is a candidate, not a finding.\n")
    w("## Changes after the first look\n")
    revs = spec.get("revisions_after_first_look", [])
    earlier = earlier_specs_line(run.get("earlier_specs", []), shash)
    if earlier:
        w(earlier + "\n")
    if run.get("incomplete_earlier"):
        w(run["incomplete_earlier"] + "\n")
    if not revs:
        w(f"No changes after the first look are recorded for spec `{shash}`. That is not a statement that none were made: only changes written into `backtest_notes.py` for this spec hash appear here.\n")
    else:
        hist = run.get("primary_history", [])
        same = len(hist) >= 2 and all(h_["n"] == hist[0]["n"] and abs(h_["ex_own"] - hist[0]["ex_own"]) < 5e-7 for h_ in hist)
        if same:
            ident = f"the primary cell is identical in every logged run ({hist[0]['ex_own']:+.4%}, n = {hist[0]['n']:,}, {len(hist)} runs in the trial log)"
        elif len(hist) >= 2:
            ident = "the primary cell differs between logged runs: " + "; ".join(f"{h_['ex_own']:+.4%} (n = {h_['n']:,}) in {h_['spec_hash'][:8]}" for h_ in hist[-4:])
        else:
            ident = "only one run of the primary cell is in the trial log, so no comparison between runs is possible"
        w("The first run of this study was computed with an earlier spec, and its output was read before the corrections below were made. The pre-registered question, the thresholds and the split were not changed, "
          f"and {ident}. The corrections were found by reading the first run's own numbers; they were not searched for in the other direction"
          + (", and the independent review (next section) found one more problem that was left uncorrected.\n" if notes.get("review") else ".\n"))
        for t_ in revs:
            w(f"- {t_}")
        w("")
    w("## Independent review\n")
    if notes.get("review"):
        w(notes["review"] + "\n")
        warn = quoted_mismatch(shash, float(prim["ex_own"]) if prim is not None else None, int(prim["n"]) if prim is not None else None)
        if warn:
            w(f"**Note: figures differ.** {warn}\n")
    else:
        w(f"No review is recorded for spec {shash}. These numbers have not been checked by a second person or tool; treat them as unreviewed.\n")
    # ---- trust
    w("## How much to trust this\n")
    n_uni = spec["universe"]["n"]
    missing = spec["data"].get("missing_tickers")
    src_txt, hist_from = spec["data"].get("source", "source not recorded"), spec["data"].get("history_from", first)
    if run["n_series"] >= n_uni:
        cov = f"**Coverage.** All {n_uni} stocks have price data."
    elif missing:
        cov = f"**Coverage.** {run['n_series']} of {n_uni} stocks: {', '.join(missing)} had no usable price data at the source and {'is' if len(missing) == 1 else 'are'} left out."
    else:
        cov = f"**Coverage.** {run['n_series']} of {n_uni} stocks have price data; the missing tickers are not recorded in this run's spec."
    for t in [
        "**Survivorship bias.** The universe is today's blue chips. Companies that fell out of the indices, were delisted or were taken over are missing, and those are more likely to have kept falling after a dip. This flatters any dip-based rule, including the excess over a stock's own non-dip days. No result here has been discounted for it.",
        "**Events cluster.** Many events sit in the same selloffs, so the effective sample is far smaller than the event count. The intervals resample whole months for that reason; they still assume months are independent, and overlapping forward windows (horizons " + ", ".join(map(str, bt.horizons)) + " days) add more dependence.",
        "**Today's fundamentals in the past.** V3 filters past dips with the current quality score, which uses information that did not exist then. Treat V3 as indicative only; it is not shown to be better or worse than V1.",
        "**Thresholds were set before testing, but they are not proven.** They are the project's starting defaults; the report does not tune them. Changing them now and re-testing would create new trials.",
        "**Costs are simple.** One round-trip figure for all stocks and years. Real spreads, taxes, currency conversion and the cost of being unable to trade at the next close are not modelled.",
        "**Currency.** Returns are in each stock's own currency. The Europe + Nordic index baseline (STOXX 600, in EUR) is not currency-adjusted for CHF, SEK, DKK or NOK stocks.",
        f"**Data.** One free source ({src_txt}), history from {hist_from}. Continental European lines were not independently verified (see the M2 notes), and clean data-quality counts above do not prove the prices are right.",
        "**One sample.** A single market history with a handful of large selloffs. A different history could give a different answer.",
        (f"**Low power.** Out-of-sample intervals are about ±{(prim['ex_own_hi'] - prim['ex_own_lo']) / 2 * 100:.1f} points wide at {H} days, " if prim is not None else "**Low power.** Out-of-sample intervals are wide, ")
        + "so an edge of a few tenths of a percent could not be detected either way. 'Not shown' is not 'absent'.",
        cov + " The exchange cross-check (M2) covered about three months of unadjusted closes for sample tickers; dividend adjustment and older history were not checked.",
        f"**Simplifications.** Costs are one flat figure even though dip days usually have wider spreads (the 4× column partly covers that). The worst-dip-after-entry numbers use closes only, not intraday lows. A {bt.cooldown_days}-bar cooldown means events in the same stock are at least {bt.cooldown_days + 1} bars apart.",
    ]:
        w(f"- {t}")
    w("")
    w("## Files\n")
    w("`spec.json` (frozen before the run) · `results.csv` (every cell) · `events.csv` (every event with its returns) · `data_validation.csv` · "
      "`../trials_all.csv` (running trial log) · `../registry.csv` (every registration and its out-of-sample window) · charts `distribution.png`, `forest.png`. Reproduce: `python scripts/run_backtest.py`.\n")
    return "\n".join(L)


def write_report(run: dict, s: Settings, out_dir: Path) -> Path:
    chart_distribution(run["days"], s, out_dir / "distribution.png")
    chart_forest(run["results"], s, out_dir / "forest.png")
    text = render_report(run, s, {"distribution": "distribution.png", "forest": "forest.png"})
    p = out_dir / "report.md"
    p.write_text(text, encoding="utf-8")
    return p
