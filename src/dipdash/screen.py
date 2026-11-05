"""Screening rules: dip, falling knife and the setup label. Pure functions on metric dicts.

Rules use the metric values as shown on the dashboard (rounded to 4 decimals).
All thresholds are untested defaults until the backtest supports them.
"""
from __future__ import annotations

from datetime import date

import numpy as np

from .config import DipSettings, FallingKnifeSettings, NewsSettings, Settings
from .fmt import pct

NO_DIP = "No dip"
FALLING_KNIFE = "Falling knife"
NO_FUNDAMENTALS = "Dip, no fundamentals"
QUALITY_DIP = "Quality dip"
LOW_QUALITY = "Dip, low quality"


def dip_reasons(m: dict, dip: DipSettings) -> list[str]:
    """Why the stock counts as a dip (empty list = not a dip)."""
    rules = [("1-day", "r1", dip.drop_1d), ("5-day", "r5", dip.drop_5d), ("below 20-day high", "dd20", dip.drawdown_20d)]
    return [f"{label} {pct(m[k])} (rule: {pct(-limit, 0)})" for label, k, limit in rules
            if m.get(k) is not None and m[k] <= -limit]


def is_dip(m: dict, dip: DipSettings) -> bool:
    return bool(dip_reasons(m, dip))


def is_falling_knife(m: dict, knife: FallingKnifeSettings) -> bool:
    """Below the 200-day average (falling, if required) and far below the 52-week high."""
    vs200, dd52 = m.get("vs200"), m.get("dd52")
    if vs200 is None or dd52 is None or vs200 >= 0:
        return False
    if knife.below_200d_falling and not m.get("s200_falling"):
        return False
    return dd52 <= -knife.drawdown_52w


def setup_label(dip: bool, knife: bool, q_score: int | None, settings: Settings, q_ok: bool = True,
                distorted: bool = False) -> str:
    """The one precedence for the setup label. Not a dip -> No dip; a falling knife outranks quality;
    missing fundamentals (None) never count as passing; distorted fundamentals -> NO_FUNDAMENTALS key
    (shown as "data looks unreliable"; the score is not altered); a failed must-pass rule (q_ok=False) ->
    LOW_QUALITY key ("Dip, fewer checks passed") whatever the score; a score of 0 is a real score.
    Defaults keep the plain score-only behaviour."""
    if not dip:
        return NO_DIP
    if knife:
        return FALLING_KNIFE
    if q_score is None or distorted:
        return NO_FUNDAMENTALS
    if not q_ok:
        return LOW_QUALITY
    return QUALITY_DIP if q_score >= settings.quality.min_score else LOW_QUALITY


# Human-readable enum-level labels (neutral wording). The setup values above are the stable payload keys and are
# not renamed; this map is what a reader-facing list of the enum should show.
SETUP_LABELS = {
    NO_DIP: "No dip",
    FALLING_KNIFE: "Falling knife",
    NO_FUNDAMENTALS: "Dip, no fundamentals",
    QUALITY_DIP: "Dip, more checks passed",
    LOW_QUALITY: "Dip, fewer checks passed",
}
UNRELIABLE_TEXT = "Dip · data looks unreliable"


def setup_text(setup: str, passed: int | None, applicable: int | None, scored: int | None = None,
               distorted: bool = False) -> str:
    """Reader-facing text for a setup label; the enum names stay the stable key.
    The two scored dip labels read "Dip · passes 5 of 6 scored checks" and, when some checks had no data,
    "Dip · passes 3 of 4 scored checks (2 no data)". `scored` = checks that had data (QualityResult.scored);
    None means "all applicable were scored". NO_FUNDAMENTALS with distorted=True -> "Dip · data looks unreliable";
    NO_FUNDAMENTALS otherwise (nothing scored) -> "Dip, no fundamentals". Unknown label -> ValueError;
    without counts the plain "Dip" is returned."""
    if setup in (NO_DIP, FALLING_KNIFE):
        return setup
    if setup == NO_FUNDAMENTALS:
        return UNRELIABLE_TEXT if distorted else setup
    if setup in (QUALITY_DIP, LOW_QUALITY):
        if passed is None or not applicable:
            return "Dip"
        n = applicable if scored is None else scored
        text = f"Dip · passes {passed} of {n} scored checks"
        if n < applicable:
            text += f" ({applicable - n} no data)"
        return text
    raise ValueError(f"unknown setup label {setup!r}")


def classify(m: dict, q_score: int | None, settings: Settings, q_ok: bool = True, distorted: bool = False) -> str:
    """Setup label for a metric dict (see `setup_label`)."""
    return setup_label(is_dip(m, settings.dip), is_falling_knife(m, settings.falling_knife), q_score, settings,
                       q_ok, distorted)


def needs_news(m: dict, news: NewsSettings) -> bool:
    """Fetch headlines only for stocks that fell meaningfully (keeps the run short)."""
    t = news.fetch_if_5d_drop
    return ((m.get("r5") or 0) <= -t or (m.get("r1") or 0) <= -t / 2 or (m.get("dd20") or 0) <= -2 * t)


def trading_days_old(last_bar: date, today: date) -> int:
    """Weekdays from the last bar up to today (holidays are not modelled)."""
    return int(np.busday_count(last_bar, today))


def is_stale(last_bar: date, today: date, max_trading_days: int) -> bool:
    return trading_days_old(last_bar, today) > max_trading_days


def classify_prev(prev: dict | None, q_score: int | None, settings: Settings, q_ok: bool = True,
                  distorted: bool = False) -> str | None:
    """The setup a stock had at the previous close, from the `prev` block of the payload (same fundamentals as today).
    None when there is no previous-close data."""
    if not prev:
        return None
    return setup_label(bool(prev.get("dip")), bool(prev.get("knife")), q_score, settings,
                       q_ok, distorted)
