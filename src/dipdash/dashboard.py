"""Build the dashboard payload from prices + fundamentals and inject it into template.html."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from .config import Settings, Stock
from .fsio import atomic_write_text
from .metrics import clean, compute_metrics, history
from .quality import score_universe
from .residual import residual_move
from .screen import classify, dip_reasons, is_falling_knife, is_stale, needs_news, setup_text
from .validate import Issue

TEMPLATE = Path(__file__).resolve().parents[1] / "template.html"
PLACEHOLDER = "__DATA__"
PRICE_SCALE = 100          # hist and spark prices are integers in 1/PRICE_SCALE of the currency unit

Prices = dict[str, tuple[pd.Series, "pd.Series | None"]]


def _suffix(ticker: str) -> str:
    return "." + ticker.rsplit(".", 1)[1].lower() if "." in ticker else ""


def pick_index(ticker: str, region: str, indices: list[dict], fallback_region: str = "Europe") -> dict | None:
    """The market-context index for a stock. Order: an index whose `suffixes` lists the ticker's exchange suffix
    (".ST" -> Stockholm), else the region-level index (no suffixes) for the stock's region, else the index of
    `fallback_region` (Europe-wide) for any non-US stock. None if nothing fits or the index had no data this run."""
    sfx = _suffix(ticker)
    if sfx:
        for i in indices:
            if sfx in [x.lower() for x in i.get("suffixes") or []]:
                return i
    regional = {i["region"]: i for i in indices if not i.get("suffixes")}
    if region in regional:
        return regional[region]
    return regional.get(fallback_region) if sfx and region != "US" else None


def index_r5_on(ix: dict, day: str) -> float | None:
    """The index's 5-bar return ending on `day`, from the recent closes carried in the payload. None if `day` is not there
    (or fewer than 5 earlier bars). Falls back to the latest r5 when the payload has no closes (older payloads)."""
    closes = ix.get("closes")
    if not closes:
        return ix.get("r5") if ix.get("asof") == day else None
    days = sorted(closes)
    if day not in closes or days.index(day) < 5:
        return None
    return clean(closes[day] / closes[days[days.index(day) - 5]] - 1)

# Sector rules are settings, not payload: the page gets the per-stock result, so the payload shape is unchanged.
SECTOR_RULE_KEYS = ("not_applicable", "debt_to_equity_max_by_sector")


def build_payload(universe: list[Stock], prices: Prices, funds: dict, settings: Settings, *,
                  news_fn: Callable[[str], list[dict]] | None = None, demo: bool = False,
                  today: date | None = None, fx_to_usd: dict[str, float] | None = None,
                  indices: list[dict] | None = None, issues: list[Issue] | None = None,
                  now: datetime | None = None, index_history: dict | None = None,
                  earnings: dict | None = None) -> dict:
    """One row per screened stock plus a data_quality list for every ticker that was skipped."""
    today = today or date.today()
    indices = indices or []
    partial = {i.ticker for i in (issues or []) if i.check == "partial_bar"}     # last bar is dated today: the session may still be open
    index_history = index_history or {}
    earnings = earnings or {}
    rows, skipped = [], []
    scored = score_universe(funds, universe, settings.quality, fx_to_usd, use_sector=True)
    for s in universe:
        if s.ticker not in prices:
            skipped.append({"t": s.ticker, "reason": "no_price_data", "detail": "no price data returned"})
            continue
        m = compute_metrics(*prices[s.ticker])
        if not m:
            skipped.append({"t": s.ticker, "reason": "short_history", "detail": "not enough history"})
            continue
        last_bar = date.fromisoformat(m["asof"])
        if is_stale(last_bar, today, settings.data.max_stale_trading_days):
            skipped.append({"t": s.ticker, "reason": "stale", "detail": f"last bar {m['asof']}"})
            continue
        f = funds.get(s.ticker, {})
        qr = scored[s.ticker]
        q, checks = qr.score, qr.checks
        q_ok, distorted = not qr.must_failed, qr.status == "distorted"
        m["knife"] = is_falling_knife(m, settings.falling_knife)
        m["hist"] = history(prices[s.ticker][0])
        m["prev"] = _yesterday(prices[s.ticker], settings)
        ix = pick_index(s.ticker, s.region, indices, settings.context.fallback_region)
        m["idx"] = ix["name"] if ix else None
        m["idx_sym"] = ix["symbol"] if ix else None
        r5ix = index_r5_on(ix, m["asof"]) if ix else None
        m["x5"] = clean(m["r5"] - r5ix) if r5ix is not None and m["r5"] is not None else None
        m["idx_why"] = None if m["x5"] is not None else _no_index_reason(s, ix, m)
        res = {"res1": None, "res5": None, "res5z": None, "beta": None, "beta_raw": None, "beta_side": None,
               "reason": "no index history" if ix else "no index for this stock"}
        if ix and ix["symbol"] in index_history:
            try:
                res = residual_move(prices[s.ticker][0], index_history[ix["symbol"]])
            except Exception as exc:                   # one odd series must never abort the whole run
                res["reason"] = f"residual could not be computed ({type(exc).__name__})"
        m.update({"res1": clean(res["res1"], 4), "res5": clean(res["res5"], 4), "res5z": clean(res["res5z"], 2),
                  "beta": clean(res["beta"], 2), "beta_raw": clean(res.get("beta_raw"), 2), "beta_side": res.get("beta_side"),
                  "res_why": res["reason"]})
        m["earn"] = earnings.get(s.ticker)
        m["partial"] = s.ticker in partial
        m.update({
            "t": s.ticker, "name": s.name, "region": s.region, "sector": s.sector,
            "q": q, "qchecks": checks, "q_scored": qr.scored, "q_applicable": qr.applicable, "q_passed": qr.passed,
            "q_status": qr.status, "q_why": qr.distorted_why, "q_must_failed": list(qr.must_failed),
            "q_must_missing": list(qr.must_missing), "fpe": clean(f.get("forwardPE"), 1), "tpe": clean(f.get("trailingPE"), 1),
            "ccy": f.get("currency") or "", "news": [],
            "dip": bool(dip_reasons(m, settings.dip)), "why": dip_reasons(m, settings.dip),
            "setup": classify(m, q, settings, q_ok=q_ok, distorted=distorted),
        })
        m["setup_text"] = setup_text(m["setup"], qr.passed, qr.applicable, qr.scored, qr.status == "distorted")
        rows.append(m)

    movers = [r for r in rows if needs_news(r, settings.news)]
    if news_fn and movers:
        with ThreadPoolExecutor(6) as ex:
            for r, n in zip(movers, ex.map(lambda r: news_fn(r["t"]), movers)):
                r["news"] = n
    chart_dates = share_chart_axis(rows)
    tz = settings.schedule.timezone
    stamp = (now or datetime.now(ZoneInfo(tz))).strftime("%Y-%m-%d %H:%M")
    return {"generated": stamp, "tz": tz, "demo": demo, "rows": rows, "data_quality": skipped,
            "chart_dates": chart_dates, "price_scale": PRICE_SCALE,
            "fx_to_usd": fx_to_usd or {}, "indices": indices,
            "issues": [asdict(i) for i in (issues or [])],
            "settings": {"dip": asdict(settings.dip), "quality": {k: v for k, v in asdict(settings.quality).items() if k not in SECTOR_RULE_KEYS},
                         "knife": asdict(settings.falling_knife)}}


def _cents(v: float | None) -> int | None:
    return None if v is None else int(round(v * PRICE_SCALE))


def share_chart_axis(rows: list[dict]) -> list[str]:
    """Move every row's chart dates onto one shared axis and return that axis (ISO dates, oldest first).

    The axis is the sorted union of all rows' bar dates. A row's `hist` then keeps no dates: `hist.o` is the axis index of its
    first bar and `c`, `s`, `h` run from there, so item i belongs to `chart_dates[o + i]`; a day on the axis where this stock
    had no bar (an exchange holiday) is null, and the lists stop at the stock's last bar. Prices in `hist` and `spark` become
    integers in hundredths of the currency unit (`price_scale`), which is exactly the 2-decimal rounding they had before."""
    axis = sorted({d for r in rows for d in r["hist"]["d"]})
    pos = {d: i for i, d in enumerate(axis)}
    for r in rows:
        h = r["hist"]
        o = pos[h["d"][0]]
        n = pos[h["d"][-1]] - o + 1
        packed = {"o": o}
        for k in ("c", "s", "h"):
            out: list[int | None] = [None] * n
            for day, v in zip(h["d"], h[k]):
                out[pos[day] - o] = _cents(v)
            packed[k] = out
        r["hist"] = packed
        r["spark"] = [_cents(v) for v in r["spark"]]
    return axis


def _no_index_reason(s: Stock, ix: dict | None, m: dict) -> str:
    """Why a row has no 'vs index' number. Written into the payload so nothing is silently blank."""
    if ix is None:
        return f"no market index for {_suffix(s.ticker) or s.region} (none configured, or it returned no data this run)"
    if m["r5"] is None:
        return "the stock's own 5-day move is not available"
    return f"{ix['name']} has no 5-bar window ending on the stock's last bar {m['asof']}"


def _yesterday(bars: tuple, settings: Settings) -> dict | None:
    """The metrics a stock had at the previous close, for 'new since yesterday'. None if there is too little history."""
    close, volume = bars
    c = close.dropna()
    m = compute_metrics(c.iloc[:-1], volume.reindex(c.index).iloc[:-1] if volume is not None else None)
    if not m:
        return None
    return {k: m[k] for k in ("r1", "r5", "r21", "dd20")} | {"knife": is_falling_knife(m, settings.falling_knife),
                                                             "dip": bool(dip_reasons(m, settings.dip))}


def render_html(payload: dict, template_path: Path = TEMPLATE) -> str:
    """Inject the payload as JSON. '</' is escaped so text in a headline cannot close the script tag."""
    html = template_path.read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c")
    return html.replace(PLACEHOLDER, data)


def write_dashboard(payload: dict, out: Path | str) -> Path:
    return atomic_write_text(out, render_html(payload))
