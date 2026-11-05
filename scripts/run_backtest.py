#!/usr/bin/env python3
"""Run the dip-rule event study on live history and write output/backtests/<date>/.

    .venv/bin/python scripts/run_backtest.py            # uses the newest cached history, or downloads one
    .venv/bin/python scripts/run_backtest.py --refresh  # download a fresh history first

The spec is written before any result is computed (see src/dipdash/backtest_run.py). Needs network only for a fresh download,
fundamentals (V3) and FX rates.
"""
import argparse
import sys
import warnings
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dipdash.backtest_report import write_report  # noqa: E402
from dipdash.backtest_run import INDEX_SYMBOLS, clean_bars, run_backtest, sha256  # noqa: E402
from dipdash.cache import list_raw, load_raw_prices, save_raw_prices  # noqa: E402
from dipdash.config import load_settings, load_universe  # noqa: E402
from dipdash.quality import score_universe  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="download a fresh history even if one is cached")
    ap.add_argument("--out-root", default=str(ROOT / "output" / "backtests"))
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    a = ap.parse_args()
    s = load_settings()
    universe = load_universe()
    data_dir = Path(a.data_dir)
    start = (pd.Timestamp(s.backtest.start_date) - pd.Timedelta(days=500)).date().isoformat()   # warm-up for the 252-bar inputs

    import yfinance  # noqa: F401
    warnings.filterwarnings("ignore", module=r"yfinance(\.|$)")
    from dipdash.data import fetch_index_history, fetch_prices

    cached = list_raw("yfinance_backtest", data_dir / "raw")
    if cached and not a.refresh:
        raw = cached[-1]
        print(f"Using cached history {raw.name}")
        bars = load_raw_prices(raw)
    else:
        print(f"Downloading history from {start} for {len(universe)} tickers...")
        bars = fetch_prices([u.ticker for u in universe], start=start)
        raw = save_raw_prices(bars, "yfinance_backtest", data_dir / "raw")
        print(f"  saved {raw}")
    prices, volumes, removed = {}, {}, {}
    for t, (c, v) in bars.items():
        c2, n = clean_bars(c, v)
        if len(c2):                                  # a ticker Yahoo has no data for (ROG.SW) is left out and named in the spec
            prices[t] = c2
            volumes[t] = v.reindex(c2.index) if v is not None else None
        if n:
            removed[t] = n
    idx = fetch_index_history(INDEX_SYMBOLS, start)

    # V3 (indicative) needs today's fundamentals: the cached pull from the daily run, with today's FX rates.
    import json

    from dipdash.fx import fetch_fx_to_usd
    funds = {t: v.get("d", {}) for t, v in json.loads((data_dir / "fundamentals.json").read_text()).items()}
    fx = fetch_fx_to_usd(f.get("currency") for f in funds.values())
    # use_sector=False: Iiro's decision 2026-11-05 (docs/decisions/2026-11-05-04-*.md): the backtest gets no sector input.
    scored = score_universe(funds, [u for u in universe if u.ticker in prices], s.quality, fx, use_sector=False)
    q = {t: r.score for t, r in scored.items()}

    meta = {"source": "yfinance, dividend-adjusted daily closes", "raw_file": raw.name, "raw_sha256": sha256(raw),
            "history_from": start, "n_series": len(prices), "last_bar": str(max(c.index[-1] for c in prices.values()).date()),
            "missing_tickers": [u.ticker for u in universe if u.ticker not in prices],
            "zero_volume_bars_removed": {"total": sum(removed.values()), "tickers": len(removed), "of_bars": sum(len(c) for c in prices.values()) + sum(removed.values())},
            "index_last_bar": {g: str(c.index[-1].date()) for g, c in idx.items()},
            "universe_sha256": sha256(ROOT / "config" / "universe.csv"), "settings_sha256": sha256(ROOT / "config" / "settings.toml")}
    out_dir = Path(a.out_root) / date.today().isoformat()
    run = run_backtest(prices, idx, universe, q, s, out_dir, meta, volumes=volumes)
    path = write_report(run, s, out_dir)
    print(f"spec {run['spec']['spec_hash']}  cutoff {run['cutoff'].date()}  cells {len(run['results'])}")
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
