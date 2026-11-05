"""Informational trigger alerts: "a research condition you set became true". Price-only, daily closes, no network.

These alerts report that a condition changed state at the data date. They never tell anyone to act and are not
investment advice. Wording is neutral on purpose ("closed back above its 20-day average", "condition met").

Design decisions (also logged in docs/decisions.md)
- Conditions (all computed from closes up to and including `asof`; later bars are cut off, so there is no look-ahead):
  "recovery" (shown as "back above its 20-day average": close crosses back above its 20-day simple average, was below it
  the day before), "rsi_rebound" (shown as "RSI back above 30": RSI(14), same Wilder convention as metrics.rsi14, moves
  from below 30 to 30 or above). These two internal keys keep their old names on purpose: they are stored in the alert
  state file (data/alerts_state.json) and config/alerts.toml, so renaming them would break existing state. Only the
  user-visible text is neutral. Other conditions: new_low (close below the lowest close
  of the previous N days, default 60; a caution, not an invalidation of anything), drop_continues (a further 1-day fall
  of at least X%, default 4%, for a stock that was already flagged at the previous close; caution), level_cross
  (user-set price level crossed up or down, in the stock's own currency), earnings_window (from the optional
  `earnings` dict passed in; nothing is fetched and the `earn` field of a row is ignored), newly_flagged and
  no_longer_flagged (relative to the previous snapshot: row["prev"]["dip"]).
- Evaluated set: every currently flagged stock (row["dip"]), every watchlist stock, and, for no_longer_flagged only,
  stocks flagged at the previous close.
- Fire once: state/alerts_state.json style file stores the last known boolean per (ticker, condition). An alert is emitted
  only on false -> true. Cross conditions are true for one bar only, so they fire once by nature; persistent ones
  (new_low window, earnings_window) fire when the state turns true and stay silent until the state has been false in between.
- Quiet first run: with no usable state (missing, corrupt, or wrong shape) nothing is emitted except ONE summary alert
  listing the stocks that are newly flagged versus the previous snapshot. State is still recorded.
- A stock that leaves the evaluated set loses its state (it counts as fresh if it returns). If a stock has no bar on
  `asof` (stale) or the earnings context is not passed, its previous state is carried over unchanged.
- Ranking: info before caution, then quality score descending, then the 5-day residual (else 5-day move) ascending.
- Delivery: alerts_markdown (digest.md section), write_alerts_json (output/alerts_latest.json for the dashboard and
  scripts/notify.ps1), notification_text (ONE summary: count plus top 3 headlines).
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field, fields, replace
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .fsio import atomic_write_text

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "alerts.toml"
DEFAULT_STATE = ROOT / "data" / "alerts_state.json"
CONDITIONS = ("recovery", "rsi_rebound", "new_low", "drop_continues", "earnings_window", "newly_flagged", "no_longer_flagged")
SUMMARY = "newly_flagged_summary"
DIRECTIONS = ("up", "down", "both")
NOTIFY_TOP = 3
MIN_BARS = 40


# ---------------------------------------------------------------- config
@dataclass(frozen=True)
class Defaults:
    conditions: tuple = CONDITIONS
    sma_days: int = 20
    rsi_level: float = 30.0
    new_low_days: int = 60
    drop_continues: float = 0.04
    earnings_recent_days: int = 5
    earnings_soon_days: int = 10


@dataclass(frozen=True)
class Level:
    price: float
    direction: str = "both"


@dataclass(frozen=True)
class Watch:
    ticker: str
    levels: list = field(default_factory=list)
    note: str = ""
    overrides: dict = field(default_factory=dict)


@dataclass
class AlertsConfig:
    defaults: Defaults = field(default_factory=Defaults)
    watch: list = field(default_factory=list)

    def for_ticker(self, ticker: str) -> Defaults:
        for w in self.watch:
            if w.ticker == ticker and w.overrides:
                return replace(self.defaults, **w.overrides)
        return self.defaults

    def watch_for(self, ticker: str) -> Watch | None:
        return next((w for w in self.watch if w.ticker == ticker), None)


def _checked(d: dict, where: str) -> dict:
    names = {f.name for f in fields(Defaults)}
    bad = sorted(set(d) - names)
    if bad:
        raise ValueError(f"alerts config {where}: unknown key(s) {bad}; allowed: {sorted(names)}")
    out = dict(d)
    if "conditions" in out:
        unknown = sorted(set(out["conditions"]) - set(CONDITIONS))
        if unknown:
            raise ValueError(f"alerts config {where}: unknown condition(s) {unknown}; allowed: {list(CONDITIONS)}")
        out["conditions"] = tuple(out["conditions"])
    return out


def load_alerts_config(path: Path | str | None = None) -> AlertsConfig:
    """config/alerts.toml -> AlertsConfig. A missing file gives the defaults and an empty watchlist."""
    p = Path(path) if path else DEFAULT_CONFIG
    if not p.exists():
        return AlertsConfig()
    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    defaults = replace(Defaults(), **_checked(raw.get("defaults", {}), "[defaults]"))
    watch = []
    for w in raw.get("watch", []):
        w = dict(w)
        ticker = w.pop("ticker")
        levels = [Level(float(x["price"]), x.get("direction", "both")) for x in w.pop("levels", [])]
        for lv in levels:
            if lv.direction not in DIRECTIONS:
                raise ValueError(f"alerts config [[watch]] {ticker}: direction must be one of {DIRECTIONS}")
        note = str(w.pop("note", ""))
        watch.append(Watch(ticker, levels, note, _checked(w, f"[[watch]] {ticker}")))
    return AlertsConfig(defaults, watch)


# ---------------------------------------------------------------- state
def empty_state() -> dict:
    return {"version": 1, "initialized": None, "asof": None, "items": {}}


def load_state(path: Path | str) -> tuple[dict, str | None]:
    """(state, problem). A missing file is normal (empty state, no problem). A corrupt one gives an empty
    state and a one-line reason; the caller treats it as a first (quiet) run."""
    p = Path(path)
    if not p.exists():
        return empty_state(), None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return empty_state(), f"state file unreadable ({type(e).__name__}); starting fresh and staying quiet this run"
    items = raw.get("items") if isinstance(raw, dict) else None
    ok = (isinstance(items, dict) and all(isinstance(v, dict) and isinstance(v.get("active"), bool) for v in items.values())
          and isinstance(raw.get("initialized"), (str, type(None))))
    if not ok:
        return empty_state(), "state file has an unexpected shape; starting fresh and staying quiet this run"
    return raw, None


def save_state(path: Path | str, state: dict) -> Path:
    return atomic_write_text(path, json.dumps(state, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- indicators
def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI at every bar (same smoothing and seed as metrics.rsi14). NaN where the price never moved."""
    d = close.diff().dropna()
    alpha = 1 / period
    up = d.clip(lower=0).ewm(alpha=alpha, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=alpha, adjust=False).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = 100 - 100 / (1 + up / dn)
    rsi = rsi.where(dn > 0, 100.0)
    return rsi.where((up > 0) | (dn > 0), np.nan)


def _closes(bars) -> pd.Series:
    c = bars[0] if isinstance(bars, tuple) else bars
    return c.dropna()


def _fmt_days(n: int) -> str:
    return "today" if n == 0 else f"{n} trading day{'s' if n != 1 else ''}"


# ---------------------------------------------------------------- conditions: each returns (active, headline tail, detail)
def _recovery(c: pd.Series, d: Defaults):
    n = d.sma_days
    if len(c) < n + 1:
        return None
    sma = c.rolling(n).mean()
    prev, now, s_prev, s_now = c.iloc[-2], c.iloc[-1], sma.iloc[-2], sma.iloc[-1]
    active = bool(prev < s_prev and now > s_now)
    return active, f"closed back above its {n}-day average", (
        f"close {now:.2f} vs {n}-day average {s_now:.2f} ({now / s_now - 1:+.1%}); day before {prev:.2f} vs {s_prev:.2f}")


def _rsi_rebound(c: pd.Series, d: Defaults):
    if len(c) < MIN_BARS:
        return None
    r = rsi_series(c)
    prev, now = r.iloc[-2], r.iloc[-1]
    if np.isnan(prev) or np.isnan(now):
        return False, "", ""
    lvl = d.rsi_level
    return bool(prev < lvl <= now), f"RSI back above {lvl:g}", f"RSI(14) {now:.1f} (day before {prev:.1f}); close {c.iloc[-1]:.2f}"


def _new_low(c: pd.Series, d: Defaults):
    n = d.new_low_days
    if len(c) < n + 1:
        return None
    low = c.iloc[-n - 1:-1].min()
    now = c.iloc[-1]
    return bool(now < low), f"closed below its lowest close of the previous {n} days", (
        f"close {now:.2f} vs previous {n}-day low {low:.2f} ({now / low - 1:+.1%})")


def _drop_continues(c: pd.Series, d: Defaults, was_flagged: bool):
    if len(c) < 2:
        return None
    r1 = c.iloc[-1] / c.iloc[-2] - 1
    return bool(was_flagged and r1 <= -d.drop_continues), f"fell a further {abs(r1):.1%} in one day while flagged", (
        f"1-day move {r1:+.1%} (condition: {d.drop_continues:.0%} or more); close {c.iloc[-1]:.2f}, day before {c.iloc[-2]:.2f}")


def _level(c: pd.Series, lv: Level, direction: str, ccy: str):
    if len(c) < 2:
        return None
    prev, now = c.iloc[-2], c.iloc[-1]
    if direction == "up":
        active, word = bool(prev < lv.price <= now), "above"
    else:
        active, word = bool(prev >= lv.price > now), "below"
    return active, f"closed {word} the {lv.price:.2f} level you set", (
        f"close {now:.2f} {ccy}, day before {prev:.2f}; level {lv.price:.2f}".replace("  ", " "))


def _earnings(e: dict, d: Defaults):
    since, until = e.get("days_since_last"), e.get("days_until_next")
    if since is not None and since <= d.earnings_recent_days:
        return True, f"reported {_fmt_days(since)}{'' if since == 0 else ' ago'}", f"last report {e.get('last') or 'date n/a'}; price moves nearby may reflect it"
    if until is not None and until <= d.earnings_soon_days:
        return True, f"reports in {_fmt_days(until)}", f"next report {e.get('next') or 'date n/a'}; price moves nearby may reflect it"
    return False, "", ""


# ---------------------------------------------------------------- evaluation
def _context(r: dict) -> dict:
    return {k: r.get(k) for k in ("price", "r1", "r5", "res5", "q", "setup")}


def rank_alerts(alerts: list[dict]) -> list[dict]:
    def key(a):
        c = a.get("context") or {}
        q = c.get("q")
        move = c.get("res5") if c.get("res5") is not None else c.get("r5")
        return (a.get("condition") != SUMMARY, a.get("kind") == "caution", -(q if q is not None else -1),
                move if move is not None else 0.0, a.get("ticker", ""), a.get("condition", ""))
    return sorted(alerts, key=key)


def evaluate_alerts(rows: list[dict], prices: dict, state: dict, config: AlertsConfig, asof: str,
                    earnings: dict | None = None) -> tuple[list[dict], dict]:
    """Pure: (alerts, new_state). `rows` are dashboard payload rows, `prices` {ticker: close Series or (close, volume)},
    `state` from load_state, `asof` the ISO data date, `earnings` an optional {ticker: earnings_context dict}."""
    ts, old_items = pd.Timestamp(asof), dict(state.get("items", {}))
    first_run = not state.get("initialized")
    items: dict[str, dict] = {}
    alerts: list[dict] = []
    newly: list[str] = []

    def record(t: str, cond: str, active: bool, row: dict, kind: str, headline: str, detail: str, note: str = ""):
        key = f"{t}|{cond}"
        old = old_items.get(key)
        was = bool(old and old.get("active"))
        items[key] = {"active": active, "first_seen": (old or {}).get("first_seen", asof),
                      "last_changed": asof if (old is None or was != active) else old.get("last_changed", asof)}
        if active and not was and not first_run:
            a = {"ticker": t, "name": row.get("name", ""), "condition": cond, "kind": kind, "headline": f"{t}: {headline}",
                 "detail": detail, "context": _context(row), "asof": asof}
            if note:
                a["note"] = note
            alerts.append(a)

    def carry(t: str, conds: tuple[str, ...], max_age_days: int | None = None):
        for k, v in old_items.items():
            tk, _, cond = k.partition("|")
            if tk == t and cond.split(":")[0] in conds:
                if max_age_days is not None:
                    try:
                        if (ts - pd.Timestamp(v.get("last_changed", asof))).days > max_age_days:
                            continue
                    except Exception:
                        continue
                items[k] = v

    for row in rows:
        t = row["t"]
        watch = config.watch_for(t)
        flagged = bool(row.get("dip"))
        prev_flagged = bool((row.get("prev") or {}).get("dip"))
        if not (flagged or watch or prev_flagged):
            # Not evaluated today. Keep the state of the long-lasting conditions for a while, so a stock that flickers out of
            # the flagged set and back does not announce the same earnings window or the same low again.
            carry(t, ("earnings_window", "new_low"), max_age_days=15)
            continue
        d = config.for_ticker(t)
        on = set(d.conditions)
        note = watch.note if watch else ""
        ccy = row.get("ccy") or ""
        if row.get("prev") is not None:
            if "newly_flagged" in on:
                act = flagged and not prev_flagged
                record(t, "newly_flagged", act, row, "info", "newly flagged by the screen", "meets the dip rules at this close; was not flagged at the previous close", note)
                if act:
                    newly.append(t)
            if "no_longer_flagged" in on:
                record(t, "no_longer_flagged", prev_flagged and not flagged, row, "info", "no longer flagged by the screen",
                       "does not meet the dip rules at this close; was flagged at the previous close", note)
        if not (flagged or watch):
            continue
        price_conds = ("recovery", "rsi_rebound", "new_low", "drop_continues", "level_cross")
        bars = prices.get(t)
        c = _closes(bars)[lambda s: s.index <= ts] if bars is not None else None
        if c is None or len(c) == 0 or c.index[-1] != ts:
            carry(t, price_conds)                      # no bar on the data date: keep the old state, say nothing
        else:
            checks = {"recovery": lambda: _recovery(c, d), "rsi_rebound": lambda: _rsi_rebound(c, d), "new_low": lambda: _new_low(c, d),
                      "drop_continues": lambda: _drop_continues(c, d, prev_flagged)}
            for cond, fn in checks.items():
                if cond in on and (res := fn()) is not None:
                    kind = "caution" if cond in ("new_low", "drop_continues") else "info"
                    record(t, cond, res[0], row, kind, res[1], res[2], note)
            if watch:
                for lv in watch.levels:
                    for direction in (("up", "down") if lv.direction == "both" else (lv.direction,)):
                        if (res := _level(c, lv, direction, ccy)) is not None:
                            record(t, f"level_cross:{lv.price}:{direction}", res[0], row, "info" if direction == "up" else "caution",
                                   res[1], res[2], note)
        if "earnings_window" in on:
            e = (earnings or {}).get(t)
            if e is None:
                carry(t, ("earnings_window",))
            else:
                res = _earnings(e, d)
                record(t, "earnings_window", res[0], row, "info", res[1], res[2], note)

    if first_run and newly:
        shown = ", ".join(sorted(newly)[:10]) + (f" and {len(newly) - 10} more" if len(newly) > 10 else "")
        alerts.append({"ticker": "*", "name": "", "condition": SUMMARY, "kind": "info",
                       "headline": f"{len(newly)} candidate{'s' if len(newly) != 1 else ''} newly flagged by the screen",
                       "detail": f"newly flagged versus the previous close: {shown}. First run: other conditions are recorded, not announced.",
                       "context": {}, "asof": asof})
    new_state = {"version": 1, "initialized": state.get("initialized") or asof, "asof": asof, "items": items}
    return rank_alerts(alerts), new_state


# ---------------------------------------------------------------- delivery
def alerts_markdown(alerts: list[dict]) -> str:
    """The digest.md section."""
    out = ["## Trigger alerts\n",
           "Research conditions that became true at this data date. Informational only, not investment advice: each line "
           "reports that a condition changed state, nothing more.\n"]
    if not alerts:
        out.append("No conditions changed state since the last run.\n")
        return "\n".join(out)
    for a in alerts:
        tag = " [caution]" if a["kind"] == "caution" else ""
        note = f" Note: {a['note']}" if a.get("note") else ""
        out.append(f"- **{a['headline']}**{tag}. {a['detail'][:1].upper() + a['detail'][1:]}.{note}")
    out.append("")
    return "\n".join(out)


def write_alerts_json(alerts: list[dict], path: Path | str, asof: str) -> Path:
    """output/alerts_latest.json, also the list the dashboard can embed and notify.ps1 reads."""
    return atomic_write_text(path, json.dumps({"asof": asof, "count": len(alerts), "alerts": alerts}, indent=1, ensure_ascii=False) + "\n")


def notification_text(alerts: list[dict]) -> dict | None:
    """ONE summary notification: the count plus the top three headlines. None when there is nothing to report."""
    if not alerts:
        return None
    n = len(alerts)
    lines = [a["headline"] if len(a["headline"]) <= 70 else a["headline"][:67] + "..." for a in alerts[:NOTIFY_TOP]]   # Windows cuts balloon text near 255 characters
    if n > NOTIFY_TOP:
        lines.append(f"+{n - NOTIFY_TOP} more in digest.md")
    return {"title": f"Dip screen: {n} research condition{'s' if n != 1 else ''} met", "body": "\n".join(lines)}


def run_alerts(rows: list[dict], prices: dict, asof: str, *, state_path: Path | str = DEFAULT_STATE,
               config_path: Path | str | None = None, earnings: dict | None = None,
               json_path: Path | str | None = None) -> tuple[list[dict], str | None]:
    """Load config and state, evaluate, save state and (optionally) the JSON list. Returns (alerts, state problem)."""
    state, problem = load_state(state_path)
    alerts, new_state = evaluate_alerts(rows, prices, state, load_alerts_config(config_path), asof, earnings)
    save_state(state_path, new_state)
    if json_path:
        write_alerts_json(alerts, json_path, asof)
    return alerts, problem
