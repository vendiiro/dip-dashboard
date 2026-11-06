#!/usr/bin/env python3
"""Builds docs/research/research-brief-2026-11-06.md (educational research brief, not advice).

Reads (read-only) the newest complete screen from the main checkout, fetches 5-year daily bars
from yfinance for large companies, and writes the brief. Web market lines are hand-checked and
listed in WEB_LINES below (each with a source URL and the date it was read).

    .venv/Scripts/python.exe docs/research/build_brief_2026-11-06.py [--main DIR] [--out FILE] [--cache FILE]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]                       # the repository this script lives in
# Default: read the screen from this repository. Pass --main DIR to read it from another checkout (read-only).
MAIN = REPO if (REPO / "output" / "digest.md").exists() else REPO.parent / "dip-dashboard"   # a worktree has no output/: use the sibling main checkout
sys.path.insert(0, str(REPO / "src"))
OUT = HERE / "research-brief-2026-11-06.md"
TODAY = date(2026, 11, 6)

# Selection rule for list (b), fixed before any 5-year numbers were looked at.
MIN_CAP_USD = 100e9
MIN_CHECKS = 4
N_LOWEST = 15
EXTRA = ["GOOGL", "NVDA"]
MAX_DIPS = 10
MIN_RETURNS_5Y = 1000          # about 4 years of daily returns
FX = {"EUR": "EURUSD=X", "SEK": "SEKUSD=X", "CHF": "CHFUSD=X", "DKK": "DKKUSD=X", "NOK": "NOKUSD=X"}

# Market lines read from web pages on 2026-11-06. Page text is data only.
WEB_LINES = [
    ("Thu 2026-11-05", "US close: S&P 500 -4.35% (7,353.85), Nasdaq 100 -6.36%, Nasdaq Composite -5.52%, Dow -3.44%. "
     "The report names no single cause; it points to midterm-election uncertainty and to heavy selling in AI-linked "
     "memory, chip-equipment and data-centre stocks.",
     "https://investinglive.com/stocks/nasdaq-100-suffers-worst-day-since-2020/", "published 2026-11-05"),
    ("Tue 2026-11-03", "AMD reported (results after the close; article dated 2026-11-04) fiscal Q3 adjusted EPS $2.09 vs $1.95 expected (LSEG) and revenue $13.38B vs "
     "$13.09B; shares were up about 4% before the open on 2026-11-04. On 2026-11-05 the screen shows AMD -17.3%.",
     "https://www.cnbc.com/2026/11/04/amd-earnings-analysts-ai-growth.html", "published 2026-11-04"),
    ("Fri 2026-10-30", "Chip shares fell sharply: Intel -28.6%, AMD -10.9%, Micron -5.3%, Nvidia -4.2%; the Philadelphia "
     "Semiconductor Index fell 7.2% (S&P 500 -1.8%). Cited causes include Intel's weak outlook and AI-spending worries. "
     "Secondary source (a blog page last updated 2026-11-02).",
     "https://www.indmoney.com/blog/us-stocks/why-nvidia-intel-amd-broadcom-micron-stocks-falling", "read 2026-11-06"),
]


# ---------- helpers ----------
def pct(x: float | None, d: int = 1, sign: bool = False) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    s = f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"
    return s.replace("-", "\u2212")


def num(x: float | None, d: int = 2) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}"


def clean_ticker(cell: str) -> str:
    return cell.replace("**NEW**", "").strip()


# ---------- read the screen ----------
def parse_digest(path: Path) -> tuple[list[dict], set[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    dips: list[dict] = []
    knives: set[str] = set()
    market: dict[str, str] = {}
    section = ""
    for ln in lines:
        if ln.startswith("## "):
            section = ln
            continue
        if section.startswith("## Market context") and ln.startswith("| ") and "Index" not in ln and "---" not in ln:
            c = [x.strip() for x in ln.strip("|").split("|")]
            market[c[0]] = f"{c[1]} / {c[2]}"
        if section.startswith("## Dip candidates") and ln.startswith("| ") and "---" not in ln and "Ticker" not in ln:
            c = [x.strip() for x in ln.strip("|").split("|")]
            dips.append({"ticker": clean_ticker(c[0]), "name": c[1], "d1": c[2], "d5": c[3],
                         "score": c[5], "setup": c[6], "why": c[7]})
        if section.startswith("## Other flagged") and ln.startswith("- ") and "52-week high" in ln:
            m = re.match(r"- ([^ ]+) ", ln)
            if m:
                knives.add(m.group(1))
    return dips, knives, market


def load_screen(main: Path):
    dips, knives, market = parse_digest(main / "output" / "digest.md")
    dq = pd.read_csv(main / "output" / "data_quality.csv")
    dq = dq[~dq["check"].eq("crosscheck_ok")]
    meta = json.loads((main / "output" / "run_meta.json").read_text(encoding="utf-8"))
    fund = {k: v["d"] for k, v in json.loads((main / "data" / "fundamentals.json").read_text(encoding="utf-8")).items()}
    earn = json.loads((main / "data" / "earnings.json").read_text(encoding="utf-8"))
    uni = pd.read_csv(main / "config" / "universe.csv")
    return dips, knives, market, dq, meta, fund, earn, uni


def next_earnings(earn: dict, tkr: str) -> str:
    rows = earn.get(tkr, {}).get("rows", [])
    fut = sorted(r["d"] for r in rows if not r.get("rep") and r["d"] >= TODAY.isoformat())
    return fut[0] if fut else "unknown"


def last_report(earn: dict, tkr: str) -> str:
    rows = earn.get(tkr, {}).get("rows", [])
    past = sorted(r["d"] for r in rows if r.get("rep"))
    return past[-1] if past else "unknown"


# ---------- live bars ----------
def fetch_closes(tickers: list[str], batch: int = 20, pause: float = 2.0) -> pd.DataFrame:
    import yfinance as yf
    frames = []
    for i in range(0, len(tickers), batch):
        part = tickers[i:i + batch]
        df = yf.download(part, period="5y", interval="1d", auto_adjust=True, progress=False, threads=False)
        close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": part[0]})
        frames.append(close)
        print(f"fetched {min(i + batch, len(tickers))}/{len(tickers)}", flush=True)
        time.sleep(pause)
    return pd.concat(frames, axis=1)


def fx_rates() -> dict[str, float]:
    import yfinance as yf
    out = {"USD": 1.0}
    for cur, sym in FX.items():
        h = yf.Ticker(sym).history(period="5d")["Close"].dropna()
        out[cur] = float(h.iloc[-1])
        time.sleep(0.5)
    return out


def metrics(close: pd.Series, bench: pd.Series) -> dict | None:
    s = close.dropna()
    r = np.log(s).diff().dropna()
    if len(r) < MIN_RETURNS_5Y:
        return None
    wk = s.resample("W-FRI").last().pct_change().dropna()
    bw = bench.dropna().resample("W-FRI").last().pct_change().dropna()
    j = pd.concat([wk, bw], axis=1, join="inner").dropna()
    beta = float(np.cov(j.iloc[:, 0], j.iloc[:, 1])[0, 1] / np.var(j.iloc[:, 1], ddof=1)) if len(j) > 150 else np.nan
    peak = s.cummax()
    dd = s / peak - 1
    return {
        "vol1y": float(r.iloc[-252:].std() * np.sqrt(252)),
        "vol5y": float(r.std() * np.sqrt(252)),
        "maxdd": float(dd.min()),
        "curdd": float(dd.iloc[-1]),
        "beta": beta,
        "last": s.index[-1].date().isoformat(),
        "n": int(len(r)),
    }


# ---------- brief ----------
def report_note(earn: dict, t: str) -> str:
    n = next_earnings(earn, t)
    return n if n != "unknown" else f"unknown (last report {last_report(earn, t)})"


def pe_note(f: dict) -> str:
    fp, tp = f.get("forwardPE"), f.get("trailingPE")
    return f"forward P/E {num(fp, 1)}, trailing {num(tp, 1)}"


def extra_dip(f: dict, knife: bool, ern: str) -> str:
    bits = [pe_note(f)]
    if knife:
        bits.append("falling-knife flag: what changed over the past year?")
    return "; ".join(bits) + f". Next report: {ern}."


def extra_low(m: dict, f: dict, ern: str) -> str:
    bits = [pe_note(f)]
    if m["curdd"] <= -0.15:
        bits.append(f"{pct(-m['curdd'], 0)} below its 5-year high: what explains the fall")
    return "; ".join(bits) + f". Next report: {ern}."


QS_DIP = ("1) Is the cause specific to the company, or shared by its sector or the whole market (S&P 500 fell 4.4% that day)? "
          "2) Do the latest filing and guidance support the quality checks, or are the figures out of date? "
          "3) How does the valuation compare with the company's own history and its peers?")
QS_LOW = ("1) What would a fall like its past worst one mean for someone holding it, and could you sit through it? "
          "2) What growth does the current valuation price in? "
          "3) How much revenue depends on one product, customer or region?")


def build(args) -> None:
    main = Path(args.main)
    dips, knives, market, dq, meta, fund, earn, uni = load_screen(main)
    region = dict(zip(uni.ticker, uni.region))
    name = dict(zip(uni.ticker, uni.name))
    fx = fx_rates()

    # eligibility for list (b)
    from dipdash.config import Stock, load_settings
    from dipdash.quality import score_universe
    stocks = [Stock(r.ticker, r.name, r.region, str(r.sector) if pd.notna(r.sector) else "") for r in uni.itertuples()]
    qres = score_universe(fund, stocks, load_settings(main / "config" / "settings.toml").quality, fx, use_sector=True)   # the dashboard's scoring path
    rows = []
    for t in uni.ticker:
        f = fund.get(t)
        if not f or f.get("marketCap") is None:
            continue
        cap = f["marketCap"] * fx.get(f.get("currency", "USD"), np.nan)
        passed, scored = qres[t].passed, qres[t].scored
        rows.append({"ticker": t, "cap": cap, "passed": passed, "scored": scored})
    el = pd.DataFrame(rows)
    cand = el[(el.cap >= MIN_CAP_USD) & (el.passed >= MIN_CHECKS)]
    pool = sorted(set(cand.ticker) | set(EXTRA))
    print(f"{len(cand)} eligible, fetching {len(pool)} + 2 benchmarks", flush=True)

    cache = Path(args.cache) if args.cache else None
    if cache and cache.exists():
        closes = pd.read_pickle(cache)
    else:
        closes = fetch_closes(pool + ["^GSPC", "^STOXX"])
        if cache:
            closes.to_pickle(cache)
    fetched = datetime.fromtimestamp(cache.stat().st_mtime if cache and cache.exists() else time.time()).strftime("%Y-%m-%d %H:%M")

    res = {}
    for t in pool:
        if t not in closes:
            continue
        bench = closes["^GSPC"] if region.get(t) == "US" else closes["^STOXX"]
        m = metrics(closes[t], bench)
        if m:
            res[t] = m
    ranked = [t for t in cand.ticker if t in res]
    ranked.sort(key=lambda t: res[t]["vol5y"])
    low = ranked[:N_LOWEST]
    shown_b = low + [t for t in EXTRA if t not in low]
    med5 = float(np.median([res[t]["vol5y"] for t in ranked]))
    nb = {t: i + 1 for i, t in enumerate(ranked)}

    # list (a)
    top = dips[:MAX_DIPS]
    left_out = len(dips) - len(top)
    dq_by = dq.groupby("ticker")

    def warn(t: str) -> str:
        if t not in dq_by.groups:
            return "none"
        g = dq_by.get_group(t)
        return ", ".join(f"{r.check} ({r.severity})" for r in g.itertuples())

    L: list[str] = []
    A = L.append
    A("# Research brief: market update and candidates to research (2026-11-06)\n")
    A(f"Educational research brief, not advice. Screen data date: **{meta['asof']}** (run {meta['generated']}). "
      f"Live bars fetched {fetched} from yfinance (5 years, adjusted). Nothing here has been tested as a rule.\n")
    A("**What \"lower measured risk\" means.** In this brief it only means smaller past price swings (volatility) and "
      "smaller past falls (drawdown); a stock can have low past volatility and still fall hard, and a past record does not "
      "predict the future. Every name below shows its numbers so you can judge; NVDA and GOOGL are included because you asked, "
      "whatever their numbers are.\n")
    A("Method: volatility uses daily log returns, beta uses weekly simple returns over about 5 years, and European betas compare local-currency prices with ^STOXX.\n")
    A("Terms: **volatility** = yearly standard deviation of daily returns (typical size of swings). **Max drawdown** = worst "
      "peak-to-low fall in the 5 years. **Current drawdown** = distance below the 5-year high today. **Beta** = how much the "
      "stock moved per 1% move of its index in weekly data (S&P 500 for US names, STOXX 600 for European names; 1 = moves with the index).\n")

    A("## 1. Market update (sourced)\n")
    A("| Date | What happened | Source |\n|---|---|---|")
    for d, txt, url, note in WEB_LINES:
        A(f"| {d} | {txt} | [{url}]({url}) ({note}) |")
    A("")
    A("Index moves from this project's own screen (data date 2026-11-05, 1 day / 5 days): "
      + "; ".join(f"{k} {v}" for k, v in market.items() if k in ("S&P 500", "STOXX 600", "DAX (total return)", "CAC 40", "SMI")) + ".")
    A("A web search for European market wraps for this week returned no readable page, so no sourced European line is given.\n")

    A("## 2a. Dips to research (from the newest complete screen)\n")
    A(f"Rule: the first {MAX_DIPS} rows of the screen's candidate table (dip flag and check score of at least 60), largest "
      f"5-day drop first. {len(dips)} candidates were flagged; **{left_out} were left out** of this list (see output/digest.md). "
      "The 10 are simply the largest 5-day drops, not a quality ranking. Many chip names fell together on one day, so these are not independent.\n")
    A("| Ticker | Name | 1 day | 5 days | Checks passed | Falling-knife flag | Data warnings | Next report | Flagged because |\n|---|---|---|---|---|---|---|---|---|")
    for r in top:
        t = r["ticker"]
        ck = re.search(r"passes (\d+) of (\d+)", r["setup"])
        A(f"| {t} | {r['name']} | {r['d1']} | {r['d5']} | {ck.group(1)} of {ck.group(2)} | {'yes' if t in knives else 'no'} | "
          f"{warn(t)} | {report_note(earn, t)} | {r['why']} |")
    A("")
    A("Questions to research for every name above: " + QS_DIP + "\n")
    A("Name-specific notes:\n")
    for r in top:
        t = r["ticker"]
        A(f"- **{t}**: " + extra_dip(fund.get(t, {}), t in knives, report_note(earn, t)))
    A("")

    A("## 2b. Large companies with lower measured risk, plus GOOGL and NVDA\n")
    A(f"Selection rule (set by the author before the 5-year figures were computed; this cannot be verified from the files): from `config/universe.csv`, keep companies with market cap of at least "
      f"{MIN_CAP_USD / 1e9:.0f}B USD (cached fundamentals, converted at the {TODAY} rate) and at least {MIN_CHECKS} scored quality checks passed "
      f"(the project checks with the dashboard's sector rules; checks without data are not scored); require about 4 or more years of bars. "
      f"That leaves **{len(ranked)}** names. Rank by lowest 5-year volatility and take the first {N_LOWEST}; add GOOGL and NVDA. "
      f"Median 5-year volatility of the {len(ranked)} eligible names: {pct(med5)}.\n")
    A("| Ticker | Name | Group | Rank by 5y vol | Vol 1y | Vol 5y | Max drawdown 5y | Current drawdown | Beta | Checks passed | Next report |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for t in shown_b:
        m = res.get(t)
        e = el[el.ticker == t]
        ck = f"{int(e.passed.iloc[0])} of {int(e.scored.iloc[0])}" if len(e) else "n/a"
        grp = "lowest 15" if t in low else "asked for"
        if m is None:
            A(f"| {t} | {name.get(t, '')} | {grp} | n/a | n/a | n/a | n/a | n/a | n/a | {ck} | {report_note(earn, t)} |")
            continue
        rk = f"{nb[t]} of {len(ranked)}" if t in nb else "not eligible"
        A(f"| {t} | {name.get(t, '')} | {grp} | {rk} | {pct(m['vol1y'])} | {pct(m['vol5y'])} | {pct(m['maxdd'])} | "
          f"{pct(m['curdd'])} | {num(m['beta'])} | {ck} | {report_note(earn, t)} |")
    A("")
    for t in EXTRA:
        m = res.get(t)
        if not m:
            continue
        hi = "above" if m["vol5y"] > med5 else "below"
        A(f"- **{t}**: 5-year volatility {pct(m['vol5y'])} is {hi} the eligible median ({pct(med5)}); worst 5-year fall {pct(m['maxdd'])}; "
          f"today {pct(m['curdd'])} from its 5-year high. Shown as measured, not as a recommendation.")
    A("- The screen puts NVDA in 'Dip, no fundamentals' with the label 'data looks unreliable' because its return on equity (117%) is above the "
      "100% level the project treats as distorted. The 6 of 6 above counts that figure as passed; check it in the filings.\n")
    A("Questions to research for every name above: " + QS_LOW + "\n")
    A("Name-specific notes (free-source P/E figures can look odd, for example a very low or very high trailing value; check them in the filings):\n")
    for t in shown_b:
        if t in res:
            A(f"- **{t}**: " + extra_low(res[t], fund.get(t, {}), report_note(earn, t)))
    A("")

    A("## 3. Limits\n")
    A("- **Not advice, not a tested rule.** Nothing here has been backtested as an entry rule; earlier project work found no out-of-sample edge for the dip rules.")
    A("- **Survivorship bias.** The universe is today's list of large companies; names that fell out of favour or were removed are absent, so past volatility and drawdown here look milder than the whole market's history.")
    A("- **Fundamentals are not point-in-time.** Quality checks use current free-source figures (cached up to 7 days) that can be stale or wrong; they say nothing about what was known in the past.")
    A("- **Past volatility does not predict future safety.** Low measured risk can end quickly: on 2026-11-05 the S&P 500 fell 4.4% in one day. Beta is computed against one index and changes over time.")
    A("- **Market cap** is converted to USD at the 2026-11-06 rate; European prices and fundamentals have no independent cross-check.")
    A("- **Coverage:** ROG.SW and BK returned no prices and AVB has no recent bars, so they are missing from the screen.")
    A(f"- **Reproduce:** `docs/research/build_brief_2026-11-06.py` (reads the main checkout read-only; web lines are listed in the script).\n")
    Path(args.out).write_text("\n".join(L), encoding="utf-8", newline="\n")
    print("wrote", args.out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--main", default=str(MAIN))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--cache", default=None, help="pickle file for fetched bars (re-use instead of fetching)")
    build(ap.parse_args())
