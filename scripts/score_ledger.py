"""Score the forward ledger: how did the screen's flagged stocks do after they were recorded?

Reads data/ledger/flags.csv (one row per screened stock per night, written before the outcome was known) and the newest
price pull, then compares flagged stocks with unflagged ones on the same date. This is the forward record since
recording began. It is short so far and needs years of nights for power. Screen results only; nothing here is advice.

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
from dipdash.ledger import read_ledger, score, summarize_scores  # noqa: E402


def pct(x: float) -> str:
    return "-" if pd.isna(x) else f"{x * 100:+.2f}%"


def describe(summary: pd.DataFrame, n_rows: int, first: str, last: str, cost: float, level: float) -> str:
    out = [f"Forward ledger: {n_rows} recorded stock-nights, {first} to {last}.",
           "This is the forward record since recording began. It is short so far and needs years of nights for power.",
           f"Flagged = met the dip rule. Baseline = unflagged stocks on the same date. Net = after a {cost * 100:.2f}% round-trip cost on the flagged side.",
           f"Intervals are {level * 100:.0f}%, resampling whole calendar months. Fewer than 30 matured flagged rows: no interval is shown.",
           "Survivorship bias does not apply (stocks are recorded before their outcome), but the universe is today's blue-chip list.", ""]
    for _, r in summary.iterrows():
        line = (f"{int(r['horizon']):>3} bars: flagged {int(r['n_flagged'])}, baseline {int(r['n_baseline'])}, dates {int(r['n_dates'])}, "
                f"months {int(r['n_months'])} | gross {pct(r['gross_diff'])} | net {pct(r['net_diff'])}")
        if not pd.isna(r["net_lo"]):
            line += f" [{pct(r['net_lo'])}, {pct(r['net_hi'])}]"
        if r["note"]:
            line += f" | {r['note']}"
        out.append(line)
    out += ["", "Screen results from a past window. They say nothing certain about the future and are not advice."]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger", default=str(ROOT / "data" / "ledger" / "flags.csv"))
    ap.add_argument("--raw", help="price file from data/raw/yfinance (default: the newest)")
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
    raw = Path(a.raw) if a.raw else (list_raw("yfinance", ROOT / "data" / "raw") or [None])[-1]
    if raw is None:
        print("No price pull found in data/raw/yfinance; pass --raw.")
        return 1
    prices = {t: c for t, (c, _) in load_raw_prices(raw).items()}
    scored = score(led, prices, s.backtest.horizons)
    summary = summarize_scores(scored, s)
    out = Path(a.out)
    atomic_write_text(out, summary.to_csv(index=False, lineterminator="\n"))
    atomic_write_text(out.with_name(out.stem + "_rows.csv"), scored.to_csv(index=False, lineterminator="\n"))
    print(f"Prices: {raw.name}")
    print(describe(summary, len(led), led["asof"].min(), led["asof"].max(), s.backtest.cost_roundtrip, s.backtest.ci_level))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
