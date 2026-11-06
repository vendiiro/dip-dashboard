"""Score the forward ledger: how did the screen's flagged stocks do after they were recorded?

Reads data/ledger/flags.csv (one row per screened stock per night, written before the outcome was known) and a price
pull, then compares flagged stocks with unflagged ones on the same date. This is the forward record since recording
began. It is short so far and needs years of nights before the result can mean much. Screen results only; nothing here
is advice.

Scoring needs prices that reach back to the oldest ledger row. The nightly pull holds about 2 years, which is enough
at first; later pass a longer pull with --raw (for example the newest file in data/raw/yfinance_backtest).

    python scripts/score_ledger.py [--ledger FILE] [--raw FILE] [--out FILE]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from dipdash.cache import list_raw, load_raw_prices  # noqa: E402
from dipdash.config import load_settings  # noqa: E402
from dipdash.fsio import atomic_write_text  # noqa: E402
from dipdash.ledger import MIN_FLAGGED, MIN_MONTHS, pick_raw, read_ledger, score, summarize_scores  # noqa: E402

CAVEAT = ("In a synthetic no-effect test run during review (not saved in this repository), nominal 90% intervals at these sizes "
          "covered somewhat less than 90%, so treat the intervals as somewhat too narrow.")


def pct(x: float) -> str:
    return "-" if pd.isna(x) else f"{x * 100:+.2f}%"


def explain(cost: float, level: float, cooldown: int) -> list[str]:
    return [
        "Flagged = met the dip rule that night. Baseline = stocks that were not flagged on the same date.",
        "Gross = flagged return minus baseline return, before any cost. Net = gross minus one round trip "
        f"(buying and later selling) at {cost * 100:.2f}%, charged to the flagged side only. 2x net doubles that cost.",
        f"'After cooldown' keeps a stock's flagged night only if at least {cooldown} trading days (price bars) have passed since "
        "its last kept one, so consecutive nights count as one event. 'All nights' keeps every flagged night and counts the same "
        "event many times.",
        f"Intervals are {level * 100:.0f}%, resampling whole calendar months. An interval is shown only with at least {MIN_FLAGGED} events "
        f"after the cooldown over at least {MIN_MONTHS} calendar months; otherwise only the means are shown.",
        CAVEAT,
        "Survivorship bias means a history that holds only the stocks that still exist, which flatters dip rules. The ledger is "
        "fixed in advance, so that bias does not enter the record. But a stock that was delisted or acquired has no later price "
        "and cannot be scored. Those rows are counted as unscored below, and they may be the worst outcomes.",
        "'excess' is each flagged return minus the same-date baseline: median, then 10th and 90th percentile.",
    ]


def describe(summary: pd.DataFrame, n_rows: int, first: str, last: str, cost: float, level: float, cooldown: int) -> str:
    out = [f"Forward ledger: {n_rows} recorded stock-nights, {first} to {last}.",
           "This is the forward record since recording began. It is short so far and needs years of nights before the result "
           "can mean much.", *explain(cost, level, cooldown), ""]
    versions = summary["settings_hash"].nunique()
    if versions > 1:
        out.append(f"{versions} rule versions are in the ledger. They are shown separately and never pooled.")
    for (v, section), g in summary.groupby(["settings_hash", "section"], sort=False):
        out.append(f"== rule version {v or 'unknown'} | {section} ==  (late-recorded rows excluded: {int(g['n_late'].iloc[0])})")
        for _, r in g.iterrows():
            line = (f"{r['view']:>14}, {int(r['horizon']):>2} trading days: flagged {int(r['n_flagged'])}, baseline {int(r['n_baseline'])}, "
                    f"unscored {int(r['n_unscored'])}, months {int(r['n_months'])} | gross {pct(r['gross_diff'])} | "
                    f"net {pct(r['net_diff'])} | 2x net {pct(r['net_diff_2x'])}")
            if not pd.isna(r["net_lo"]):
                line += f" [{pct(r['net_lo'])}, {pct(r['net_hi'])}]"
            line += f" | excess {pct(r['med_excess'])} ({pct(r['p10_excess'])} to {pct(r['p90_excess'])})"
            if r["note"]:
                line += f" | {r['note']}"
            out.append(line)
    out += ["", "Screen results from a past window. They say nothing certain about the future and are not advice."]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger", default=str(ROOT / "data" / "ledger" / "flags.csv"))
    ap.add_argument("--raw", help="price file (default: the newest complete pull in data/raw/yfinance; longer pulls need this)")
    ap.add_argument("--out", default=str(ROOT / "output" / "ledger_scores.csv"))
    a = ap.parse_args(argv)
    s = load_settings()
    ledger_path = Path(a.ledger)
    if not ledger_path.exists():
        print(f"No ledger at {ledger_path} yet. It is written by the daily run; nothing to score.")
        return 1
    led = read_ledger(ledger_path)
    if led.empty:
        print("The ledger has no rows yet; nothing to score.")
        return 1
    if a.raw:
        raw, warn = Path(a.raw), ""
    else:
        raw, warn = pick_raw(list_raw("yfinance", ROOT / "data" / "raw"))
    if raw is None:
        print("No price pull found in data/raw/yfinance; pass --raw.")
        return 1
    if warn:
        print(f"Warning: {warn}")
    prices = {t: c for t, (c, _) in load_raw_prices(raw).items()}
    scored = score(led, prices, s.backtest.horizons)
    summary = summarize_scores(scored, s)
    out = Path(a.out)
    atomic_write_text(out, summary.to_csv(index=False, lineterminator="\n"))
    atomic_write_text(out.with_name(out.stem + "_rows.csv"), scored.to_csv(index=False, lineterminator="\n"))
    print(f"Prices: {raw.name}")
    print(describe(summary, len(led), led["asof"].min(), led["asof"].max(), s.backtest.cost_roundtrip, s.backtest.ci_level,
                   s.backtest.cooldown_days))
    n_bad = int((scored["reason"] != "").sum())
    if n_bad:
        print(f"{n_bad} ledger rows could not be entered (reason column in {out.stem}_rows.csv); older rows may need a longer pull via --raw.")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
