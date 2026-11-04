"""Quality score: share of fundamental checks passed. Thresholds come from settings.toml."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Callable

from .config import QualitySettings
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


# Sector adjustments. Leverage is the business model of a bank or insurer, and free cash flow is not a
# meaningful figure for them, so those checks do not apply (left out of the score, not failed).
# Utilities and real-estate companies carry high debt by design, so their debt/equity limit is relaxed. These are judgement calls,
# untested like every other threshold until a backtest supports them.
NOT_APPLICABLE: dict[str, frozenset[str]] = {   # keys lower-case: sectors are matched case-insensitively
    "financials": frozenset({"debtToEquity", "freeCashflow"}),
}
DEBT_TO_EQUITY_MAX_BY_SECTOR: dict[str, float] = {"utilities": 300.0, "real estate": 300.0}


def _number(v) -> float | None:
    """A finite float, or None for missing / non-numeric / NaN / infinite values."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def quality(fund: dict, q: QualitySettings, fx_to_usd: dict[str, float] | None = None,
            sector: str | None = None) -> tuple[int | None, list[dict]]:
    """Return (score 0-100 or None, per-check results).

    With a sector, checks that do not apply to it (see NOT_APPLICABLE) get ok=None and na=True and are
    left out of the score, and the debt/equity limit can be relaxed (DEBT_TO_EQUITY_MAX_BY_SECTOR).

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
    skip = NOT_APPLICABLE.get(key, frozenset())
    de_max = DEBT_TO_EQUITY_MAX_BY_SECTOR.get(key)
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
