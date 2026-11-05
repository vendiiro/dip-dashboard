"""Quality score: share of fundamental checks passed. Thresholds come from settings.toml."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Callable

from .config import QualitySettings, Stock
from .fx import usd_value

MIN_CHECKS_WITH_DATA = 3


@dataclass(frozen=True)
class Check:
    label: str
    key: str
    passes: Callable[[float], bool]


def build_checks(q: QualitySettings) -> list[Check]:
    return [
        Check(f"Return on equity >= {q.roe_min:.0%}", "returnOnEquity", lambda v: v >= q.roe_min),
        Check(f"Net margin >= {q.margin_min:.0%}", "profitMargins", lambda v: v >= q.margin_min),
        Check(f"Debt/equity <= {q.debt_to_equity_max:g}%", "debtToEquity", lambda v: v <= q.debt_to_equity_max),
        Check("Free cash flow positive", "freeCashflow", lambda v: v > 0),
        Check("Revenue growth positive", "revenueGrowth", lambda v: v > 0),
        Check(f"Market cap >= {q.market_cap_min / 1e9:g}B USD", "marketCap", lambda v: v >= q.market_cap_min),
    ]


def _number(v) -> float | None:
    """A finite float, or None for missing / non-numeric / NaN / infinite values."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


# Must-pass rules are named rules, separate from the six scored checks (the scored margin check uses
# margin_min, this one is "margin above zero"). A missing or non-finite value is NOT a failure: it is
# reported in `must_missing`. These are definitions, not tested filters.
MUST_PASS_RULES: dict[str, tuple[str, Callable[[float], bool]]] = {
    "net_margin_positive": ("profitMargins", lambda v: v > 0),
    "fcf_positive": ("freeCashflow", lambda v: v > 0),      # ready for a stricter option, unused by default
}
DEFAULT_MUST_PASS: tuple[str, ...] = ("net_margin_positive",)
DEFAULT_DISTORTED_ROE_ABOVE = 1.0       # ROE above 100% usually means a tiny or negative equity base

Status = str    # "ok" | "thin" | "distorted" | "no_data"


@dataclass(frozen=True)
class QualityResult:
    score: int | None
    checks: list[dict]
    scored: int                 # applicable checks that had data
    applicable: int             # 6 minus the checks that do not apply to the sector
    passed: int
    status: Status
    distorted_why: str | None
    must_failed: tuple[str, ...]
    must_missing: tuple[str, ...]


def quality_detail(fund: dict, q: QualitySettings, fx_to_usd: dict[str, float] | None = None,
                   sector: str | None = None, must_pass: tuple[str, ...] = DEFAULT_MUST_PASS,
                   distorted_roe_above: float = DEFAULT_DISTORTED_ROE_ABOVE) -> QualityResult:
    """The quality score plus how much evidence stands behind it.

    `score` and `checks` are exactly what `quality()` returns (the stored score is never altered).
    Status precedence: no_data (score None) > distorted > thin (scored < applicable) > ok.
    Distorted: ROE above `distorted_roe_above`, or ROE and debt/equity both missing for a sector where
    debt/equity applies (suggests negative equity; `totalDebt` is not fetched yet). Unknown must_pass name -> ValueError.
    """
    for name in must_pass:
        if name not in MUST_PASS_RULES:
            raise ValueError(f"unknown must_pass rule {name!r}; known: {sorted(MUST_PASS_RULES)}")
    score, checks = quality(fund, q, fx_to_usd, sector)
    applicable = sum(1 for c in checks if not c.get("na"))
    scored = sum(1 for c in checks if c["ok"] is not None)
    passed = sum(1 for c in checks if c["ok"] is True)
    by_key = {c["key"]: c for c in checks}

    why = None
    roe, de = by_key["returnOnEquity"], by_key["debtToEquity"]
    if not roe.get("na") and roe["value"] is not None and roe["value"] > distorted_roe_above:
        why = f"return on equity {roe['value']:.0%} is above {distorted_roe_above:.0%}"
    elif not roe.get("na") and not de.get("na") and roe["value"] is None and de["value"] is None:
        why = "return on equity and debt/equity are both missing (possible negative equity)"

    failed, missing = [], []
    for name in must_pass:
        key, rule = MUST_PASS_RULES[name]
        v = _number(fund.get(key))
        if v is None:
            missing.append(name)
        elif not rule(v):
            failed.append(name)

    if score is None:
        status = "no_data"
    elif why:
        status = "distorted"
    elif scored < applicable:
        status = "thin"
    else:
        status = "ok"
    return QualityResult(score, checks, scored, applicable, passed, status, why,
                         tuple(failed), tuple(missing))


def quality(fund: dict, q: QualitySettings, fx_to_usd: dict[str, float] | None = None,
            sector: str | None = None) -> tuple[int | None, list[dict]]:
    """Return (score 0-100 or None, per-check results).

    With a sector, checks that do not apply to it (q.not_applicable) get ok=None and na=True and are
    left out of the score, and the debt/equity limit can be relaxed (q.debt_to_equity_max_by_sector).

    The market-cap check is in USD. With fx_to_usd, the value is converted from the stock's own
    currency (fund["currency"]); if that currency or its rate is unknown the check has no data,
    never a guess. With fx_to_usd=None the value is taken as USD (demo data, tests).

    A check with no data has ok=None and is left out of the score. The score is None
    when fewer than MIN_CHECKS_WITH_DATA checks have data, so thin data never looks like quality.
    """
    fund = dict(fund)
    if fx_to_usd is not None and fund.get("marketCap") is not None:
        fund["marketCap"] = usd_value(fund["marketCap"], fund.get("currency"), fx_to_usd)
    key = (sector or "").strip().casefold()
    skip = {k.casefold(): set(v) for k, v in q.not_applicable.items()}.get(key, set())
    de_max = {k.casefold(): v for k, v in q.debt_to_equity_max_by_sector.items()}.get(key)
    if de_max is not None and de_max > q.debt_to_equity_max:
        q = replace(q, debt_to_equity_max=de_max)
    results, passed, avail = [], 0, 0
    for c in build_checks(q):
        if c.key in skip:
            results.append({"label": c.label, "key": c.key, "ok": None, "value": _number(fund.get(c.key)), "na": True})
            continue
        v = _number(fund.get(c.key))
        if v is None:
            results.append({"label": c.label, "key": c.key, "ok": None, "value": None})
            continue
        avail += 1
        ok = bool(c.passes(v))
        passed += ok
        results.append({"label": c.label, "key": c.key, "ok": ok, "value": v})
    score = round(100 * passed / avail) if avail >= MIN_CHECKS_WITH_DATA else None
    return score, results


def score_universe(funds: dict[str, dict], universe: list[Stock], q: QualitySettings,
                   fx_to_usd: dict[str, float] | None, *, use_sector: bool) -> dict[str, QualityResult]:
    """One quality result per universe stock; the single scoring path for the dashboard and the backtest.

    use_sector=True applies the sector rules in settings (dashboard). use_sector=False scores every stock with
    the same six checks (backtest V3, Iiro's decision 2026-11-05: the backtest gets no sector input).
    """
    return {s.ticker: quality_detail(funds.get(s.ticker, {}), q, fx_to_usd,
                                     sector=s.sector if use_sector else None,
                                     must_pass=q.must_pass, distorted_roe_above=q.distorted_roe_above)
            for s in universe}
