"""Per-exchange coverage table: how much of the universe actually arrived, by exchange suffix. Pure functions, no network.

    rows, summary = build_coverage(universe, prices, funds, earnings, today, max_stale_trading_days=4, reasons=..., status=...)
    issues = coverage_issues(rows)

Rows are plain dicts (JSON-ready) for run_meta.json and the digest; `summary` is one line for the digest header."""
from __future__ import annotations

from datetime import date

from .config import Stock
from .exchanges import EXCHANGES, suffix_of
from .screen import is_stale
from .validate import Issue, _bars_date, has_fundamentals, lagging_vs_peers

MIN_BARS_SHARE = 0.8          # an exchange with bars for fewer than this share of its tickers gets a warning (not zero: that is exchange_missing)
MIN_EARNINGS_SHARE = 0.5      # earnings dates known for fewer than this share of an exchange is an info line

COLUMNS = ("suffix", "label", "exchange", "expected", "with_bars", "stale", "lagging", "fundamentals", "earnings",
           "fetch_notes", "fund_stale")


def _earnings_known(e) -> bool:
    return isinstance(e, dict) and bool(e.get("last") or e.get("next"))


def build_coverage(universe: list[Stock], prices: dict, funds: dict | None, earnings: dict | None, today: date,
                   max_stale_trading_days: int = 4, reasons: dict | None = None,
                   status: dict | None = None) -> tuple[list[dict], str]:
    """One row per exchange suffix present in the universe (US first, then by suffix). Counts, all over universe tickers:
      expected      tickers in the universe on that suffix
      with_bars     tickers with at least one non-empty close (stale ones included)
      stale         of those, last bar older than max_stale_trading_days (same rule as the screen)
      lagging       of those, last bar behind most of the same exchange (validate.lagging_vs_peers)
      fundamentals  tickers with at least one usable quality input
      earnings      tickers with a known last or next report date
      fetch_notes   tickers with an entry in `reasons` (a failed or rescued fetch)
      fund_stale    tickers whose fundamentals are old and could not be refreshed (`status`, from fetch_fundamentals)
    Returns (rows, one-line summary)."""
    funds, earnings, reasons, status = funds or {}, earnings or {}, reasons or {}, status or {}
    groups: dict[str, list[str]] = {}
    for s in universe:
        groups.setdefault(suffix_of(s.ticker), []).append(s.ticker)

    last = {t: d for t in (x for g in groups.values() for x in g) if t in prices and (d := _bars_date(prices[t][0])) is not None}
    lag = lagging_vs_peers(last)
    rows = []
    for suffix in sorted(groups, key=lambda x: (x != "", x)):
        tks = groups[suffix]
        ex = EXCHANGES.get(suffix)
        rows.append({
            "suffix": suffix,
            "label": suffix or "US",
            "exchange": ex.name if ex else "unknown exchange",
            "expected": len(tks),
            "with_bars": sum(t in last for t in tks),
            "stale": sum(t in last and is_stale(last[t], today, max_stale_trading_days) for t in tks),
            "lagging": sum(t in lag for t in tks),
            "fundamentals": sum(has_fundamentals(funds.get(t)) for t in tks),
            "earnings": sum(_earnings_known(earnings.get(t)) for t in tks),
            "fetch_notes": sum(t in reasons for t in tks),
            "fund_stale": sum(bool((status.get(t) or {}).get("stale")) for t in tks),
        })
    return rows, summarize(rows)


def summarize(rows: list[dict]) -> str:
    """One line: totals, then up to three exchanges with the largest gaps."""
    if not rows:
        return "Coverage: empty universe"
    tot = {k: sum(r[k] for r in rows) for k in ("expected", "with_bars", "stale", "lagging", "fundamentals", "earnings")}
    line = (f"Coverage: bars {tot['with_bars']}/{tot['expected']} (stale {tot['stale']}, lagging {tot['lagging']}), "
            f"fundamentals {tot['fundamentals']}/{tot['expected']}, earnings dates {tot['earnings']}/{tot['expected']}")
    gaps = sorted(((r["expected"] - min(r["with_bars"], r["fundamentals"]), r) for r in rows if r["with_bars"] < r["expected"] or r["fundamentals"] < r["expected"]),
                  key=lambda x: (-x[0], x[1]["label"]))[:3]
    if gaps:
        line += ". Largest gaps: " + "; ".join(
            f"{r['label']} bars {r['with_bars']}/{r['expected']}, fundamentals {r['fundamentals']}/{r['expected']}" for _, r in gaps)
    return line + "."


def coverage_issues(rows: list[dict], min_bars_share: float = MIN_BARS_SHARE, min_earnings_share: float = MIN_EARNINGS_SHARE) -> list[Issue]:
    """Issues for thin exchanges. A fully missing exchange and low fundamentals share are reported by validate.py
    (exchange_missing, fundamentals_coverage); this adds the partial cases that module does not cover."""
    out = []
    for r in rows:
        n = r["expected"]
        if n == 0:
            continue
        if 0 < r["with_bars"] < n and r["with_bars"] / n < min_bars_share:
            out.append(Issue(r["label"], "exchange_thin", "warn",
                             f"only {r['with_bars']} of {n} {r['label']} stocks ({r['exchange']}) have price bars; minimum {min_bars_share:.0%}"))
        if r["with_bars"] and n >= 3 and r["earnings"] / n < min_earnings_share:
            out.append(Issue(r["label"], "earnings_coverage", "info",
                             f"earnings dates known for {r['earnings']} of {n} {r['label']} stocks; the 'reports soon' tag is incomplete there"))
    return out
