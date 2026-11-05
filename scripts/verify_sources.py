#!/usr/bin/env python3
"""Re-run the M2 data verification and write a Markdown report. Needs network and the project venv.

    .venv/bin/python scripts/verify_sources.py                      # writes output/verification/m2-data-verification.md
    .venv/bin/python scripts/verify_sources.py --out docs/m2-data-verification.md   # deliberately refresh the tracked doc
    .venv/bin/python scripts/verify_sources.py --help

Compares Yahoo (yfinance) with exchange-operator data served through OpenBB 5.0.0:
US closes vs Nasdaq and Cboe, Nordic closes and market caps vs Nasdaq Nordic, fundamentals ratios vs Nasdaq.
Continental European lines have no independent source in the default OpenBB bundle; they only get the internal checks.
"""
import argparse
import json
import re
import sys
import warnings
from datetime import date, datetime, timedelta
from importlib.metadata import version
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_OUT = ROOT / "output" / "verification" / "m2-data-verification.md"   # output/ is not committed
TRACKED_DOC = ROOT / "docs" / "m2-data-verification.md"


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Re-run the M2 data verification (Yahoo vs Nasdaq, Cboe and Nasdaq Nordic) and write a Markdown report. "
                    "Needs network access and the project venv. Educational research tool; no investment advice.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"where to write the report (default: {DEFAULT_OUT.relative_to(ROOT)}). The tracked doc "
                         f"{TRACKED_DOC.relative_to(ROOT)} is only overwritten if you pass it here.")
    return ap.parse_args(argv)


def _load_deps():
    """Network-capable imports live here so that --help and parse_args work without them."""
    global pd, openbb_source, compare_closes, fetch_prices, fetch_raw_closes, validate_prices
    import pandas as pd  # noqa: F401
    from dipdash import openbb_source  # noqa: F401
    from dipdash.crosscheck import compare_closes  # noqa: F401
    from dipdash.data import fetch_prices, fetch_raw_closes  # noqa: F401
    from dipdash.validate import validate_prices  # noqa: F401


US = ["AAPL", "MSFT", "JNJ", "KO", "JPM"]
NORDIC = ["NOKIA.HE", "SAMPO.HE", "KNEBV.HE", "ERIC-B.ST", "NOVO-B.CO"]
EVENT = ["INTC"]                                   # the largest one-day drop in the first live run
CONTINENTAL = ["ASML.AS", "SAP.DE", "NESN.SW", "MC.PA", "AIR.PA", "ROG.SW", "RO.SW"]
TODAY = date.today()
START, END = str(TODAY - timedelta(days=90)), str(TODAY)


def md(rows, header):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def price_rows(tickers, sources):
    rows = []
    for t in tickers:
        ref = fetch_raw_closes(t, START, END)
        for name, fn in sources(t):
            other = fn()
            if ref is None or other is None:
                rows.append([t, name, "no data", "", "", "", ""])
                continue
            r = compare_closes(t, name, ref, other)
            rows.append([t, name, r.n_common, f"{r.max_rel_diff:.4%}", r.n_over_tol, r.last_ref, r.last_other])
    return rows


def us_sources(t):
    from dipdash.openbb_source import _client
    obb = _client()
    nas = lambda: openbb_source.fetch_bars(t, START, END)[0]
    cboe = lambda: obb.cboe.equity.historical(symbol=t, start_date=START, end_date=END).to_df()["close"]
    return [("nasdaq", nas), ("cboe", cboe)]


def nordic_sources(t):
    return [("nasdaq_nordic", lambda: openbb_source.fetch_bars(t, START, END)[0])]


def parse_cap(s):
    m = re.match(r"([A-Z]{3})\s*([\d.,]+)\s*(Tril|Bil|Mil)", str(s))
    if not m:
        return None, None
    return m.group(1), float(m.group(2).replace(",", "")) * {"Tril": 1e12, "Bil": 1e9, "Mil": 1e6}[m.group(3)]


def fundamentals(obb):
    cache = json.loads((ROOT / "data" / "fundamentals.json").read_text())
    yf_ = lambda t, k: (cache.get(t, {}).get("d") or {}).get(k)
    cap_rows, ratio_rows = [], []
    for t in NORDIC:
        sym = openbb_source.nordic_symbol(t)
        info = obb.nasdaq.nordic.info(symbol=sym).to_df()
        fund = obb.nasdaq.nordic.fundamentals(symbol=sym).to_df()
        label = info[info.label.str.startswith("Market Cap (at close")]
        ccy, cap = parse_cap(label.value.iloc[0]) if len(label) else (None, None)
        y_cap = yf_(t, "marketCap")
        cap_rows.append([t, ccy, f"{cap / 1e9:.2f}B" if cap else "n/a", f"{y_cap / 1e9:.2f}B" if y_cap else "n/a",
                         f"{abs(y_cap / cap - 1):.2%}" if cap and y_cap else "n/a"])

        def latest(label_):
            f = fund[(fund.label == label_) & fund.period.astype(str).str.fullmatch(r"\d{4}")]
            return (float(f.value.iloc[-1]), f.period.iloc[-1]) if len(f) else (None, None)

        roe, yr = latest("Return on Equity %")
        nm, _ = latest("Net Margin %")
        de, _ = latest("Debt/Equity")
        ratio_rows.append([t, f"{roe}% (FY{yr})" if roe is not None else "n/a", f"{yf_(t, 'returnOnEquity') * 100:.1f}%" if yf_(t, "returnOnEquity") is not None else "n/a",
                           f"{nm}%" if nm is not None else "n/a", f"{yf_(t, 'profitMargins') * 100:.1f}%" if yf_(t, "profitMargins") is not None else "n/a",
                           de if de is not None else "n/a", f"{yf_(t, 'debtToEquity'):.1f}" if yf_(t, "debtToEquity") is not None else "n/a"])
    us_rows = []
    for t in US:
        r = obb.nasdaq.equity.fundamental.ratios(symbol=t).to_df()
        r = r[r.fiscal_period == "annual"].sort_values("period_ending").iloc[-1]
        us_rows.append([t, f"{r.return_on_equity * 100:.1f}% (FY{r.fiscal_year})", f"{yf_(t, 'returnOnEquity') * 100:.1f}%",
                        f"{r.net_profit_margin * 100:.1f}%", f"{yf_(t, 'profitMargins') * 100:.1f}%"])
    return cap_rows, ratio_rows, us_rows


def continental_rows():
    prices = fetch_prices(CONTINENTAL)
    rows = []
    for t in CONTINENTAL:
        if t not in prices or not len(prices[t][0].dropna()):
            rows.append([t, "no data", "", "", "Yahoo returned nothing"])
            continue
        c = prices[t][0].dropna()
        iss = validate_prices(t, c, TODAY, 4)
        rows.append([t, len(c), str(c.index[-1])[:10], f"{c.pct_change().abs().max():.1%}", "; ".join(sorted({i.check for i in iss})) or "none"])
    return rows


def main(argv=None):
    args = parse_args(argv)
    _load_deps()
    obb = openbb_source._client()
    parts = [f"# M2 data verification\n\nGenerated {datetime.now():%Y-%m-%d %H:%M} by `scripts/verify_sources.py` "
             f"(openbb {version('openbb')}, yfinance {version('yfinance')}). Window: {START} to {END}. "
             "Prices compared are **unadjusted** closes (split-adjusted only): the exchange sources do not provide dividend-adjusted prices, "
             "so dividend adjustment itself is not verified.\n"]
    hdr = ["Ticker", "Second source", "Days compared", "Max difference", "Days > 1%", "Last bar (Yahoo)", "Last bar (other)"]
    parts += ["## US closes: Yahoo vs Nasdaq and Cboe\n", md(price_rows(US + EVENT, us_sources), hdr), ""]
    parts += ["## Nordic closes: Yahoo vs Nasdaq Nordic\n", md(price_rows(NORDIC, nordic_sources), hdr), ""]
    cap, ratios, us = fundamentals(obb)
    parts += ["## Market cap: Yahoo vs Nasdaq Nordic (same close)\n", md(cap, ["Ticker", "Currency", "Nasdaq Nordic", "Yahoo", "Difference"]), ""]
    parts += ["## Ratios, Nordic: Yahoo (trailing) vs Nasdaq Nordic (last full year)\n",
              "Different periods, so only gross disagreement is meaningful. Debt/equity is **not comparable**: Yahoo's is a percentage of total debt "
              "including leases; Nasdaq Nordic's is a ratio on its own definition.\n",
              md(ratios, ["Ticker", "ROE Nasdaq", "ROE Yahoo", "Net margin Nasdaq", "Net margin Yahoo", "D/E Nasdaq (ratio)", "D/E Yahoo (%)"]), ""]
    parts += ["## Ratios, US: Yahoo (trailing) vs Nasdaq (last full year)\n",
              md(us, ["Ticker", "ROE Nasdaq", "ROE Yahoo", "Net margin Nasdaq", "Net margin Yahoo"]), ""]
    parts += ["## Continental Europe: NOT independently verified\n",
              "No source reachable from the build container covers these lines (OpenBB's default bundle has none; Stooq is blocked by the network policy). "
              "Only the internal checks ran.\n",
              md(continental_rows(), ["Ticker", "Bars (1y)", "Last bar", "Largest 1-day move", "Validation findings"]), ""]
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
