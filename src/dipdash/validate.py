"""Data-quality checks on pulled prices and fundamentals. Pure functions; results go to output/data_quality.csv."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Settings, Stock
from .fsio import atomic_write_text
from .screen import is_stale

MAX_JUMP = 0.40          # daily move that more likely means a split / adjustment error than real news
SPIKE = 0.15             # a lone bar this far from BOTH neighbours, which sit close to each other, is a bad tick, not news
SPIKE_NEIGHBOUR_TOL = 0.05
SPIKE_LOW_VOLUME = 0.6      # a bad tick trades on thin volume; a real market-wide reversal day does not
MAX_GAP_WEEKDAYS = 5     # a longer hole between bars means missing data (holiday gaps are at most 4)
MAX_MISSING_SHARE = 0.05

SUFFIX_CURRENCY = {".LS": "EUR", ".MI": "EUR", ".MC": "EUR", ".BR": "EUR", ".AS": "EUR", ".DE": "EUR", ".PA": "EUR", ".HE": "EUR", ".SW": "CHF",
                   ".ST": "SEK", ".CO": "DKK", ".OL": "NOK"}

LOG_COLUMNS = ["run_at", "ticker", "check", "severity", "detail"]


@dataclass(frozen=True)
class Issue:
    ticker: str
    check: str
    severity: str   # "error" = ticker excluded or data unusable, "warn" = used but suspicious, "info" = for the record
    detail: str


def expected_currency(ticker: str) -> str | None:
    """Trading currency implied by the exchange suffix (no suffix = US/USD); None if the suffix is unknown."""
    if "." not in ticker:
        return "USD"
    return SUFFIX_CURRENCY.get("." + ticker.rsplit(".", 1)[1])


def validate_prices(ticker: str, close: pd.Series, today: date, max_stale_trading_days: int, volume: pd.Series | None = None) -> list[Issue]:
    issues: list[Issue] = []
    if close is None or len(close.dropna()) == 0:
        return [Issue(ticker, "no_data", "error", "no price bars returned")]
    if close.index.duplicated().any():
        issues.append(Issue(ticker, "duplicate_dates", "error", f"{int(close.index.duplicated().sum())} duplicated bar date(s)"))
        close = close[~close.index.duplicated(keep="last")]
    if not close.index.is_monotonic_increasing:
        issues.append(Issue(ticker, "unsorted", "warn", "bars were not in date order; sorted for the checks"))
        close = close.sort_index()

    window = close.iloc[-252:]
    missing = float(window.isna().mean())
    if missing > MAX_MISSING_SHARE:
        issues.append(Issue(ticker, "missing_values", "warn", f"{missing:.0%} of the last {len(window)} closes are empty"))
    c = close.dropna()

    bad = c[c <= 0]
    if len(bad):
        issues.append(Issue(ticker, "non_positive_price", "error", f"{len(bad)} close(s) <= 0, first on {str(bad.index[0])[:10]}"))
    r = c.pct_change().dropna()
    r = r[np.isfinite(r)]
    for d, v in r[r.abs() > MAX_JUMP].items():
        issues.append(Issue(ticker, "large_move", "warn", f"{v:+.1%} on {str(d)[:10]}: check for a split or adjustment error"))
    if len(c) > 2:                                  # spike and revert: invisible to the 40% test when the bad bar is "only" 15-40% off
        v = c.to_numpy()
        prev, mid, nxt = v[:-2], v[1:-1], v[2:]
        with np.errstate(divide="ignore", invalid="ignore"):                      # a zero price is reported by its own check above
            bad = (np.abs(mid / prev - 1) > SPIKE) & (np.abs(mid / nxt - 1) > SPIKE) & ((mid > prev) == (mid > nxt)) & (np.abs(nxt / prev - 1) < SPIKE_NEIGHBOUR_TOL)
        vol = volume.reindex(c.index).to_numpy(dtype=float) if volume is not None else None
        for i in np.flatnonzero(bad):
            when = c.index[i + 1]
            if vol is not None:
                recent = vol[max(0, i + 1 - 20):i + 1]
                recent = recent[~np.isnan(recent)]
                if len(recent) < 5 or np.isnan(vol[i + 1]) or vol[i + 1] >= SPIKE_LOW_VOLUME * np.median(recent):
                    continue                                    # heavy volume: a real reversal day (a crash rebound), not a bad tick
            note = "likely a bad price: thin volume" if vol is not None else "possible bad price: check the volume"
            issues.append(Issue(ticker, "spike_revert", "warn", f"{mid[i] / prev[i] - 1:+.1%} on {str(when)[:10]} and back the next day, {note}"))
    if len(c) > 1:
        days = c.index.values.astype("datetime64[D]")
        gaps = np.busday_count(days[:-1], days[1:])
        for i in np.flatnonzero(gaps > MAX_GAP_WEEKDAYS):
            issues.append(Issue(ticker, "gap", "warn", f"{int(gaps[i])} weekdays without a bar before {str(c.index[i + 1])[:10]}"))

    last = pd.Timestamp(c.index[-1]).date()
    if is_stale(last, today, max_stale_trading_days):
        issues.append(Issue(ticker, "stale", "error", f"last bar {last} is older than {max_stale_trading_days} trading days; skipped"))
    return issues


def check_partial_bar(ticker: str, close: pd.Series, today: date) -> list[Issue]:
    """A last bar dated today may still be forming: a manual run during the session reads it as if the day were over.
    The nightly run (00:15 Helsinki, after both the US and European closes) never sees this."""
    c = close.dropna()
    if len(c) and pd.Timestamp(c.index[-1]).date() >= today:
        return [Issue(ticker, "partial_bar", "warn", f"last bar is dated {pd.Timestamp(c.index[-1]).date()}, today: the session may still be open")]
    return []


def validate_currency(ticker: str, fund_currency: str | None) -> list[Issue]:
    exp = expected_currency(ticker)
    if exp is None:
        return [Issue(ticker, "currency_unknown", "info", f"no currency rule for the suffix of {ticker}")]
    if not fund_currency:
        return [Issue(ticker, "currency_missing", "warn", f"no currency reported (expected {exp})")]
    if fund_currency != exp:
        return [Issue(ticker, "currency_mismatch", "warn", f"fundamentals say {fund_currency}, exchange suffix implies {exp}")]
    return []


def _norm_name(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def check_duplicate_listings(universe: list[Stock]) -> list[Issue]:
    """Same company name listed twice (e.g. an ADR and its home line): keep one primary listing."""
    seen: dict[str, str] = {}
    out = []
    for s in universe:
        k = _norm_name(s.name)
        if k in seen:
            out.append(Issue(s.ticker, "duplicate_listing", "warn", f"same company name as {seen[k]}; keep one primary listing"))
        else:
            seen[k] = s.ticker
    return out


def validate_run(universe: list[Stock], prices: dict, funds: dict, settings: Settings, today: date) -> list[Issue]:
    issues = check_duplicate_listings(universe)
    for s in universe:
        if s.ticker not in prices:
            issues.append(Issue(s.ticker, "no_data", "error", "ticker missing from the price pull"))
            continue
        issues += validate_prices(s.ticker, prices[s.ticker][0], today, settings.data.max_stale_trading_days, prices[s.ticker][1])
        issues += check_partial_bar(s.ticker, prices[s.ticker][0], today)
        if s.ticker in funds:
            issues += validate_currency(s.ticker, funds[s.ticker].get("currency"))
        else:
            issues.append(Issue(s.ticker, "no_fundamentals", "warn", "no fundamentals returned"))
    return issues


def write_quality_log(issues: list[Issue], path: Path | str, run_at: datetime | None = None) -> Path:
    """Write the latest run's issues (the file is replaced each run; dated copies are kept by the daily run)."""
    stamp = (run_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    order = {"error": 0, "warn": 1, "info": 2}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(LOG_COLUMNS)
    for i in sorted(issues, key=lambda i: (order.get(i.severity, 3), i.ticker, i.check)):
        w.writerow([stamp, i.ticker, i.check, i.severity, i.detail])
    return atomic_write_text(path, buf.getvalue())
