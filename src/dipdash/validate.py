"""Data-quality checks on pulled prices and fundamentals. Pure functions; results go to output/data_quality.csv."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .config import Settings, Stock
from .exchanges import EXCHANGES, exchange_for, suffix_of
from .fx import PENCE
from .fsio import atomic_write_text
from .screen import is_stale

MAX_JUMP = 0.40          # daily move that more likely means a split / adjustment error than real news
SPIKE = 0.15             # a lone bar this far from BOTH neighbours, which sit close to each other, is a bad tick, not news
SPIKE_NEIGHBOUR_TOL = 0.05
SPIKE_LOW_VOLUME = 0.6      # a bad tick trades on thin volume; a real market-wide reversal day does not
PRICE_SPIKE_REVERTED = 0.20     # one-day close-to-close move this large that the next bar undoes (request: move to [data] in settings.toml)
PRICE_SPIKE_BACK_TOL = 0.03     # "undone" = the close two bars on is within 3 percentage points of the close before the move
PRICE_SPIKE_BARS = 250          # only the newest bars are checked, so old splits and known events do not flood the log
MAX_GAP_WEEKDAYS = 5     # a longer hole between bars means missing data (holiday gaps are at most 4)
MAX_MISSING_SHARE = 0.05

MIN_FUNDAMENTALS_SHARE = 0.8   # share of screened stocks with fundamentals; below it the run reports an error (request: move to [data] in settings.toml)
MIN_EXCHANGE_TICKERS = 2       # a "whole exchange missing" needs at least this many universe tickers on the suffix
MIN_PEERS = 3                  # "lagging versus peers" and per-exchange shares need at least this many tickers on the exchange
PARTIAL_GRACE_MINUTES = 15     # a bar dated today is trusted this long after the exchange's regular close
FUND_KEYS = ("returnOnEquity", "profitMargins", "debtToEquity", "freeCashflow", "revenueGrowth", "marketCap")

SUFFIX_CURRENCY = {s: e.currency for s, e in EXCHANGES.items() if s and e.currency}   # derived view of the exchange registry

LOG_COLUMNS = ["run_at", "ticker", "check", "severity", "detail"]


@dataclass(frozen=True)
class Issue:
    ticker: str
    check: str
    severity: str   # "error" = ticker excluded or data unusable, "warn" = used but suspicious, "info" = for the record
    detail: str


def expected_currency(ticker: str) -> str | None:
    """Trading currency implied by the exchange suffix (no suffix = US/USD); None if the suffix is unknown."""
    ex = exchange_for(ticker)
    return ex.currency if ex else None


def check_price_spike_reverted(ticker: str, close: pd.Series, threshold: float = PRICE_SPIKE_REVERTED,
                               back_tol: float = PRICE_SPIKE_BACK_TOL, bars: int = PRICE_SPIKE_BARS) -> list[Issue]:
    """A one-day close-to-close move of at least `threshold` that the next bar reverses: the close two bars on is back within
    `back_tol` of the close before the move. Often a bad price in the pull, but it can also be a real event, so this is a
    warning only and the prices are never changed. Looks at the newest `bars` closes; a move on the last bar has no next
    bar to compare with and is not flagged. Prices are expected to be adjusted already (splits do not show up as jumps)."""
    c = close.dropna() if close is not None else pd.Series(dtype=float)
    c = c[~c.index.duplicated(keep="last")].sort_index().iloc[-bars:]
    c = c[c > 0]
    if len(c) < 3:
        return []
    v = c.to_numpy(dtype=float)
    move = v[1:-1] / v[:-2] - 1                      # move into bar i (i = 1 .. n-2)
    net = v[2:] / v[:-2] - 1                         # change from the bar before the move to the bar after it
    hit = (np.abs(move) >= threshold) & (np.abs(net) <= back_tol)
    return [Issue(ticker, "price_spike_reverted", "warn",
                  f"close moved {move[i]:+.1%} on {str(c.index[i + 1])[:10]} and was back within {back_tol * 100:.0f} points the next day: "
                  f"possible bad price, check the source (prices unchanged)")
            for i in np.flatnonzero(hit)]


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
    tail = int(close.notna().to_numpy()[::-1].argmax())          # trailing empty closes (close is deduplicated and sorted here)
    if tail:
        # A batch download aligns all tickers on one calendar, so an exchange holiday leaves an empty last row; so does a bad bar.
        issues.append(Issue(ticker, "empty_last_bar", "info",
                            f"last {tail} close(s) empty (from {str(close.index[-tail])[:10]}); using the bar from {str(c.index[-1])[:10]}"))

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
    issues += check_price_spike_reverted(ticker, c)
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


def _label(suffix: str) -> str:
    return suffix or "US"


def _bars_date(close) -> date | None:
    """Date of the newest non-empty close, or None when there is none."""
    try:
        c = close.dropna()
        return pd.Timestamp(c.index[-1]).date() if len(c) else None
    except Exception:
        return None


def check_partial_bars(prices: dict, now: datetime) -> list[Issue]:
    """Partial bars judged by each exchange's own close time. A bar dated the exchange's local day is flagged only while
    that exchange is still open (local time before its close plus PARTIAL_GRACE_MINUTES). `now` should be timezone-aware;
    a naive value is taken as UTC. A suffix with no registry entry falls back to the plain "dated today" rule."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    out: list[Issue] = []
    for t, (close, *_rest) in sorted(prices.items()):
        last = _bars_date(close)
        if last is None:
            continue
        ex = exchange_for(t)
        if ex is None:
            if last >= now.date():
                out.append(Issue(t, "partial_bar", "warn", f"last bar is dated {last}, today: the session may still be open"))
            continue
        local = now.astimezone(ZoneInfo(ex.tz))
        cutoff = datetime.combine(local.date(), ex.close) + timedelta(minutes=PARTIAL_GRACE_MINUTES)
        if last >= local.date() and local.replace(tzinfo=None) < cutoff:
            out.append(Issue(t, "partial_bar", "warn",
                             f"last bar is dated {last} but {ex.name} closes at {ex.close:%H:%M} local time "
                             f"({local:%H:%M} there now): the session may still be open"))
    return out


def lagging_vs_peers(last_dates: dict[str, date]) -> dict[str, tuple[date, int]]:
    """Tickers whose newest bar is older than the reference date of their own exchange.
    The reference is the newest date that a strict majority of the exchange's tickers have reached. Needs at least
    MIN_PEERS tickers on the exchange. If all peers share one last date (an exchange holiday) nobody is returned.
    Result: {ticker: (reference date, weekdays behind)}."""
    groups: dict[str, list[tuple[str, date]]] = {}
    for t, d in last_dates.items():
        groups.setdefault(suffix_of(t), []).append((t, d))
    out: dict[str, tuple[date, int]] = {}
    for members in groups.values():
        if len(members) < MIN_PEERS:
            continue
        ref = sorted((d for _, d in members), reverse=True)[len(members) // 2]
        for t, d in members:
            behind = int(np.busday_count(d, ref)) if d < ref else 0
            if behind >= 1:
                out[t] = (ref, behind)
    return out


def check_lagging_vs_peers(prices: dict) -> list[Issue]:
    """'Lagging versus peers': the stock's last bar is older than that of most stocks on the same exchange."""
    last = {t: d for t, v in prices.items() if (d := _bars_date(v[0])) is not None}
    return [Issue(t, "lagging_vs_peers", "warn",
                  f"last bar {last[t]} is {n} weekday(s) behind most {_label(suffix_of(t))} stocks ({ref}); the data may be late")
            for t, (ref, n) in sorted(lagging_vs_peers(last).items())]


def has_fundamentals(d) -> bool:
    """True when the entry carries at least one of the numbers the quality score reads."""
    if not isinstance(d, dict):
        return False
    for k in FUND_KEYS:
        v = d.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v:
            return True
    return False


def _has_bars(prices: dict, t: str) -> bool:
    return t in prices and _bars_date(prices[t][0]) is not None


def check_exchange_coverage(universe: list[Stock], prices: dict) -> list[Issue]:
    """A whole exchange missing: at least MIN_EXCHANGE_TICKERS universe tickers share a suffix and none has any bars.
    Usually a wrong suffix, a Yahoo outage for that market or a dropped batch, not 8 separate bad tickers."""
    groups: dict[str, list[str]] = {}
    for s in universe:
        groups.setdefault(suffix_of(s.ticker), []).append(s.ticker)
    out = []
    for suffix, tks in sorted(groups.items()):
        if len(tks) >= MIN_EXCHANGE_TICKERS and not any(_has_bars(prices, t) for t in tks):
            ex = EXCHANGES.get(suffix)
            out.append(Issue(_label(suffix), "exchange_missing", "error",
                             f"no price bars for any of the {len(tks)} {_label(suffix)} stocks"
                             f"{f' ({ex.name})' if ex else ''}: the whole exchange is missing from this run"))
    return out


def check_fundamentals_coverage(universe: list[Stock], prices: dict, funds: dict,
                                min_share: float = MIN_FUNDAMENTALS_SHARE) -> list[Issue]:
    """Share of stocks that have bars AND usable fundamentals. Below `min_share` overall is an error (the quality
    score is mostly 'no data'); a single exchange below it, while the whole is fine, is a warning."""
    screened = [s.ticker for s in universe if _has_bars(prices, s.ticker)]
    if not screened:
        return []
    have = [t for t in screened if has_fundamentals(funds.get(t))]
    share = len(have) / len(screened)
    if share < min_share:
        return [Issue("*", "fundamentals_coverage", "error",
                      f"only {len(have)} of {len(screened)} stocks ({share:.0%}) have fundamentals; minimum {min_share:.0%}. "
                      f"Quality scores for the rest read 'no data'")]
    out = []
    groups: dict[str, list[str]] = {}
    for t in screened:
        groups.setdefault(suffix_of(t), []).append(t)
    for suffix, tks in sorted(groups.items()):
        if len(tks) < MIN_PEERS:
            continue
        n = sum(has_fundamentals(funds.get(t)) for t in tks)
        if n / len(tks) < min_share:
            out.append(Issue(_label(suffix), "fundamentals_coverage", "warn",
                             f"only {n} of {len(tks)} {_label(suffix)} stocks have fundamentals; minimum {min_share:.0%}"))
    return out


def _fx_code(ccy: str | None) -> str | None:
    if not ccy:
        return None
    return "GBP" if ccy in PENCE else ccy.upper()


def check_fx_rates(universe: list[Stock], prices: dict, funds: dict, rates: dict | None) -> list[Issue]:
    """A currency in use (reported by fundamentals, else implied by the suffix) with no USD rate. `rates` is the dict from
    fx.fetch_fx_to_usd; None means FX was not fetched at all (demo mode) and nothing is checked."""
    if rates is None:
        return []
    used: dict[str, list[str]] = {}
    for s in universe:
        if s.ticker not in prices:
            continue
        ccy = _fx_code((funds.get(s.ticker) or {}).get("currency")) or _fx_code(expected_currency(s.ticker))
        if ccy and ccy != "USD":
            used.setdefault(ccy, []).append(s.ticker)
    out = []
    for ccy, tks in sorted(used.items()):
        if not rates.get(ccy):
            shown = ", ".join(tks[:4]) + (f" and {len(tks) - 4} more" if len(tks) > 4 else "")
            out.append(Issue(ccy, "fx_missing", "error",
                             f"no USD rate for {ccy} ({len(tks)} stocks: {shown}): their market cap cannot be converted, "
                             f"so the size check reads 'no data'"))
    return out


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


def fetch_issues(reasons: dict[str, str], prices: dict, fund_status: dict | None = None) -> list[Issue]:
    """Plain-language issues for failed fetches. `reasons` is filled by data.pull_prices, `fund_status` by
    data.fetch_fundamentals. A ticker with no bars at all is an error; one that was rescued (fallback, re-fetch) or only lags
    is a warn; an old fundamentals entry that could not be refreshed is a warn. Not wired into the run yet."""
    out = [Issue(t, "fetch_failed", "warn" if t in prices else "error", why) for t, why in sorted(reasons.items())]
    for t, st in sorted((fund_status or {}).items()):
        if st.get("stale"):
            out.append(Issue(t, "fundamentals_stale", "warn",
                             f"fundamentals are {st['age_days']:.0f} days old (cache limit 7) and could not be refreshed: {st.get('error') or 'no reason recorded'}"))
        elif st.get("error") and st.get("age_days") is None:
            out.append(Issue(t, "fundamentals_missing", "warn", f"fundamentals could not be fetched: {st['error']}"))
    return out


def validate_run(universe: list[Stock], prices: dict, funds: dict, settings: Settings, today: date,
                 now: datetime | None = None, fx_rates: dict | None = None) -> list[Issue]:
    """All per-ticker and run-level checks. `now` (timezone-aware) switches the partial-bar test to each exchange's close
    time; without it the old "dated today" rule runs. `fx_rates` is the dict from fx.fetch_fx_to_usd (None = not fetched,
    no FX check). The fundamentals minimum comes from settings.data.min_fundamentals_share when that field exists."""
    issues = check_duplicate_listings(universe)
    for s in universe:
        if s.ticker not in prices:
            issues.append(Issue(s.ticker, "no_data", "error", "ticker missing from the price pull"))
            continue
        issues += validate_prices(s.ticker, prices[s.ticker][0], today, settings.data.max_stale_trading_days, prices[s.ticker][1])
        if now is None:
            issues += check_partial_bar(s.ticker, prices[s.ticker][0], today)
        if s.ticker in funds:
            issues += validate_currency(s.ticker, funds[s.ticker].get("currency"))
        else:
            issues.append(Issue(s.ticker, "no_fundamentals", "warn", "no fundamentals returned"))
    if now is not None:
        issues += check_partial_bars({s.ticker: prices[s.ticker] for s in universe if s.ticker in prices}, now)
    issues += check_lagging_vs_peers({s.ticker: prices[s.ticker] for s in universe if s.ticker in prices})
    issues += check_exchange_coverage(universe, prices)
    issues += check_fundamentals_coverage(universe, prices, funds, getattr(settings.data, "min_fundamentals_share", MIN_FUNDAMENTALS_SHARE))
    issues += check_fx_rates(universe, prices, funds, fx_rates)
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
