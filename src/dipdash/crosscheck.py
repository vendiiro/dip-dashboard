"""Cross-check Yahoo closes against an independent source and log differences above a tolerance."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

import pandas as pd

from .validate import Issue

TOLERANCE = 0.01   # relative difference in the close above which a day is reported


@dataclass(frozen=True)
class CrossCheck:
    ticker: str
    source: str
    status: str            # ok | diff | no_overlap | unavailable
    n_common: int = 0
    n_only_ref: int = 0
    n_only_other: int = 0
    max_rel_diff: float = 0.0
    n_over_tol: int = 0
    last_ref: str = ""
    last_other: str = ""


def _day_index(s: pd.Series) -> pd.Series:
    s = s.dropna().astype(float).copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


def compare_closes(ticker: str, source: str, ref: pd.Series, other: pd.Series, tol: float = TOLERANCE) -> CrossCheck:
    """Compare two close series day by day (dates aligned, time zones ignored)."""
    ref, other = _day_index(ref), _day_index(other)
    common = ref.index.intersection(other.index)
    if len(common) == 0:
        return CrossCheck(ticker, source, "no_overlap", n_only_ref=len(ref), n_only_other=len(other),
                          last_ref=str(ref.index[-1].date()) if len(ref) else "",
                          last_other=str(other.index[-1].date()) if len(other) else "")
    rel = (ref[common] / other[common] - 1).abs()
    n_over = int((rel > tol).sum())
    return CrossCheck(ticker, source, "diff" if n_over else "ok", len(common),
                      len(ref.index.difference(other.index)), len(other.index.difference(ref.index)),
                      float(rel.max()), n_over, str(ref.index[-1].date()), str(other.index[-1].date()))


def pick_sample(eligible: list[str], n: int, seed: int) -> list[str]:
    """n random tickers, reproducible for a given seed (the daily run seeds with the date)."""
    return random.Random(seed).sample(sorted(eligible), min(n, len(eligible)))


def run_crosscheck(tickers: list[str], *, fetch_ref: Callable[[str, str, str], pd.Series | None],
                   fetch_other: Callable[[str], tuple[str, Callable[[str, str], pd.Series | None]] | None],
                   today: date, days: int = 60, tol: float = TOLERANCE) -> list[CrossCheck]:
    """fetch_ref(ticker, start, end) -> Yahoo closes (unadjusted). fetch_other(ticker) -> (source name, fn(start, end)) or None."""
    start, end = str(today - timedelta(days=days)), str(today)
    out = []
    for t in tickers:
        spec = fetch_other(t)
        if spec is None:
            out.append(CrossCheck(t, "none", "unavailable"))
            continue
        name, fn = spec
        ref, other = fetch_ref(t, start, end), fn(start, end)
        if ref is None or other is None or len(ref) == 0 or len(other) == 0:
            out.append(CrossCheck(t, name, "unavailable"))
            continue
        out.append(compare_closes(t, name, ref, other, tol))
    return out


def to_issues(results: list[CrossCheck], tol: float = TOLERANCE) -> list[Issue]:
    issues = []
    for r in results:
        if r.status == "ok":
            issues.append(Issue(r.ticker, "crosscheck_ok", "info",
                                f"{r.source}: {r.n_common} days match within {tol:.0%} (max diff {r.max_rel_diff:.4%}); "
                                f"last bar yahoo {r.last_ref}, {r.source} {r.last_other}"))
        elif r.status == "diff":
            issues.append(Issue(r.ticker, "crosscheck_diff", "warn",
                                f"{r.source}: {r.n_over_tol} of {r.n_common} days differ by more than {tol:.0%} (max {r.max_rel_diff:.2%})"))
        elif r.status == "no_overlap":
            issues.append(Issue(r.ticker, "crosscheck_no_overlap", "warn", f"{r.source}: no common dates to compare"))
        else:
            issues.append(Issue(r.ticker, "crosscheck_unavailable", "info", f"no independent source answered ({r.source})"))
    return issues
