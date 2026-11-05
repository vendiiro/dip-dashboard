"""Tests for dipdash.alerts: transition-based trigger alerts (informational, price-only)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from dipdash import alerts as A
from dipdash.metrics import rsi14

ROOT = Path(__file__).resolve().parents[1]
BANNED = re.compile(r"\b(" + "|".join(["bu" + "y", "se" + "ll", "tar" + "get", "ent" + "er", "recom" + "mend"]) + r")(s|ed|ing)?\b" r"|\b(" + "|".join(["sh" + "ould", "bou" + "ght", "so" + "ld", "ent" + "ry", "ent" + "ries"]) + r")\b", re.I)


def ser(values, end="2026-11-03") -> pd.Series:
    idx = pd.bdate_range(end=end, periods=len(values))
    return pd.Series([float(v) for v in values], index=idx)


def row(t="AAA", dip=True, prev_dip=True, q=80, r1=-0.01, r5=-0.05, res5=-0.03, price=100.0, setup="Quality dip"):
    return {"t": t, "name": f"{t} Inc", "q": q, "setup": setup, "r1": r1, "r5": r5, "res5": res5, "price": price,
            "ccy": "USD", "dip": dip, "prev": {"dip": prev_dip}}


def cfg(**kw) -> A.AlertsConfig:
    return A.AlertsConfig(**kw)


def day(c, k=-1) -> str:
    return str(c.index[k].date())


def two_days(rows, c, config=None, earn_prev=None, earn=None):
    """Evaluate the day before the last bar (records state), then the last bar. Returns the alerts of the last day."""
    config = config or cfg()
    _, st = A.evaluate_alerts(rows, {r["t"]: c.iloc[:-1] for r in rows}, A.empty_state(), config, day(c, -2), earn_prev)
    al, st2 = A.evaluate_alerts(rows, {r["t"]: c for r in rows}, st, config, day(c), earn)
    return al, st2


def has(al, cond):
    return [a for a in al if a["condition"] == cond]


# ---------- RSI ----------
def test_rsi_series_hand_computed_period_2():
    # closes 10,9,8,9 -> diffs -1,-1,+1. alpha=1/2, seeded by the first diff (same convention as metrics.rsi14):
    # after d2: up=0, dn=1 -> RSI 0. after d3: up=0.5, dn=0.5 -> RSI 50.
    r = A.rsi_series(ser([10, 9, 8, 9]), period=2)
    assert abs(r.iloc[-1] - 50.0) < 1e-9
    assert abs(r.iloc[-2] - 0.0) < 1e-9


def test_rsi_series_matches_dashboard_rsi14():
    rng = np.random.default_rng(1)
    c = ser(100 + np.cumsum(rng.normal(0, 1, 80)))
    assert abs(A.rsi_series(c, 14).iloc[-1] - rsi14(c)) < 1e-9


def test_rsi_rebound_fires_on_cross_up_only():
    base = [100.0] * 20 + [100.0 - i for i in range(1, 25)]       # long steady fall: RSI(14) near 0
    up = ser(base + [base[-1] + 8])
    r = A.rsi_series(up)
    assert r.iloc[-2] < 30 <= r.iloc[-1]
    al, _ = two_days([row()], up)
    assert has(al, "rsi_rebound")
    still_low = ser(base + [base[-1] - 1])
    al, _ = two_days([row()], still_low)
    assert not has(al, "rsi_rebound")


# ---------- recovery cross ----------
def test_recovery_fires_after_being_below():
    # day before: 95 vs 20-day average 99.75 (below); today 110 vs 100.25 (above)
    c = ser([100.0] * 30 + [95.0, 110.0])
    al, _ = two_days([row()], c)
    rec = has(al, "recovery")
    assert len(rec) == 1
    assert rec[0]["headline"] == "AAA: closed back above its 20-day average"
    assert rec[0]["kind"] == "info"


def test_recovery_needs_close_below_average_the_day_before():
    al, _ = two_days([row()], ser([100.0] * 30 + [105.0]))       # day before: 100 vs average 100, not below
    assert not has(al, "recovery")
    al, _ = two_days([row()], ser([100.0] * 30 + [101.0, 102.0]))   # above for two days, no cross
    assert not has(al, "recovery")


# ---------- transition fires once ----------
def test_condition_fires_once_then_not_again_then_again_after_reset():
    c = ser([100.0] * 70)
    earn = lambda lab, d: {"AAA": {"label": lab, "days_since_last": d, "days_until_next": None}}
    _, st = A.evaluate_alerts([row()], {"AAA": c}, A.empty_state(), cfg(), "2026-11-03")        # quiet first run
    a1, st = A.evaluate_alerts([row()], {"AAA": c}, st, cfg(), "2026-11-04", earn("reported_recently", 1))
    a2, st = A.evaluate_alerts([row()], {"AAA": c}, st, cfg(), "2026-11-05", earn("reported_recently", 2))
    a3, st = A.evaluate_alerts([row()], {"AAA": c}, st, cfg(), "2026-11-06", earn("none", 9))
    a4, st = A.evaluate_alerts([row()], {"AAA": c}, st, cfg(), "2026-11-09", earn("reported_recently", 1))
    assert len(has(a1, "earnings_window")) == 1 and has(a2, "earnings_window") == []
    assert has(a3, "earnings_window") == [] and len(has(a4, "earnings_window")) == 1


def test_first_run_is_quiet_but_records_state_and_summarises_newly_flagged():
    c = ser([100.0] * 30 + [95.0, 110.0])           # a recovery cross exists on this very first day
    rows = [row("AAA", dip=True, prev_dip=False), row("BBB", dip=True, prev_dip=True)]
    prices = {"AAA": c, "BBB": c}
    earn = {"AAA": {"label": "reported_recently", "days_since_last": 1, "days_until_next": None}}
    al, st = A.evaluate_alerts(rows, prices, A.empty_state(), cfg(), "2026-11-03", earn)
    assert [a["condition"] for a in al] == ["newly_flagged_summary"]
    assert al[0]["ticker"] == "*" and "AAA" in al[0]["detail"]
    assert st["initialized"] == "2026-11-03"
    assert st["items"]["AAA|recovery"]["active"] is True
    assert st["items"]["AAA|recovery"]["first_seen"] == "2026-11-03"
    al2, _ = A.evaluate_alerts(rows, prices, st, cfg(), "2026-11-03", earn)      # re-running does not repeat anything
    assert al2 == []


# ---------- level cross ----------
def test_level_cross_up_and_down():
    config = cfg(watch=[A.Watch(ticker="AAA", levels=[A.Level(price=100.0, direction="both")])])
    for c, word, kind in ((ser([98.0] * 30 + [99.0, 101.0]), "above", "info"),
                          (ser([102.0] * 30 + [101.0, 99.0]), "below", "caution")):
        al, _ = two_days([row()], c, config)
        lv = [a for a in al if a["condition"].startswith("level_cross")]
        assert len(lv) == 1 and word in lv[0]["headline"] and lv[0]["kind"] == kind
    up_only = cfg(watch=[A.Watch(ticker="AAA", levels=[A.Level(price=100.0, direction="up")])])
    al, _ = two_days([row()], ser([102.0] * 30 + [101.0, 99.0]), up_only)
    assert not [a for a in al if a["condition"].startswith("level_cross")]


def test_watchlist_ticker_is_evaluated_even_if_not_flagged():
    c = ser([98.0] * 30 + [99.0, 101.0])
    config = cfg(watch=[A.Watch(ticker="ZZZ", levels=[A.Level(price=100.0, direction="up")], note="my note")])
    al, _ = two_days([row("ZZZ", dip=False, prev_dip=False)], c, config)
    assert [a["ticker"] for a in al] == ["ZZZ"]
    al, _ = two_days([row("QQQ", dip=False, prev_dip=False)], c, cfg())          # unflagged and unwatched: nothing
    assert al == []


# ---------- other price conditions ----------
def test_new_low_is_a_caution_and_uses_only_previous_days():
    al, _ = two_days([row()], ser([100.0] * 70 + [99.0]))
    nl = has(al, "new_low")
    assert len(nl) == 1 and nl[0]["kind"] == "caution" and "60" in nl[0]["headline"]
    al, _ = two_days([row()], ser([100.0] * 70 + [100.0]))                       # equal to the old low is not below it
    assert not has(al, "new_low")


def test_drop_continues_needs_prior_flag_and_threshold():
    al, _ = two_days([row(prev_dip=True)], ser([100.0] * 70 + [95.0]))
    assert [a["kind"] for a in has(al, "drop_continues")] == ["caution"]
    al, _ = two_days([row(prev_dip=False)], ser([100.0] * 70 + [95.0]))
    assert not has(al, "drop_continues")
    al, _ = two_days([row(prev_dip=True)], ser([100.0] * 70 + [97.0]))           # -3% is under the 4% default
    assert not has(al, "drop_continues")


def test_newly_and_no_longer_flagged():
    c = ser([100.0] * 70)
    _, st = A.evaluate_alerts([row()], {"AAA": c}, A.empty_state(), cfg(), "2026-11-02")
    al, st2 = A.evaluate_alerts([row("AAA", dip=True, prev_dip=False)], {"AAA": c}, st, cfg(), "2026-11-03")
    assert has(al, "newly_flagged")
    al, _ = A.evaluate_alerts([row("AAA", dip=False, prev_dip=True)], {"AAA": c}, st2, cfg(), "2026-11-04")
    assert has(al, "no_longer_flagged")


# ---------- earnings: only the passed-in context ----------
def test_earnings_window_uses_only_passed_in_context():
    c = ser([100.0] * 70)
    r = row()
    r["earn"] = {"label": "reported_recently", "days_since_last": 1, "days_until_next": None}   # must be ignored
    _, st = A.evaluate_alerts([r], {"AAA": c}, A.empty_state(), cfg(), "2026-11-02")
    al, _ = A.evaluate_alerts([r], {"AAA": c}, st, cfg(), "2026-11-03", None)
    assert not has(al, "earnings_window")
    soon = {"AAA": {"label": "reports_soon", "days_since_last": 40, "days_until_next": 6}}
    al, _ = A.evaluate_alerts([r], {"AAA": c}, st, cfg(), "2026-11-03", soon)
    ew = has(al, "earnings_window")
    assert len(ew) == 1 and "6 trading days" in ew[0]["headline"]
    far = {"AAA": {"label": "none", "days_since_last": 40, "days_until_next": 30}}
    al, _ = A.evaluate_alerts([r], {"AAA": c}, st, cfg(), "2026-11-03", far)
    assert not has(al, "earnings_window")


# ---------- state file ----------
def test_state_roundtrip_and_corrupt_or_missing(tmp_path):
    p = tmp_path / "alerts_state.json"
    st, problem = A.load_state(p)
    assert st == A.empty_state() and problem is None            # a missing file is normal
    p.write_text("{not json", encoding="utf-8")
    st, problem = A.load_state(p)
    assert st == A.empty_state() and "unreadable" in problem
    p.write_text("[1,2]", encoding="utf-8")
    st, problem = A.load_state(p)
    assert st == A.empty_state() and problem
    p.write_text(json.dumps({"version": 1, "initialized": "2026-11-03", "items": {"AAA|x": "bad"}}), encoding="utf-8")
    st, problem = A.load_state(p)
    assert st == A.empty_state() and problem
    good = {"version": 1, "initialized": "2026-11-03", "asof": "2026-11-03",
            "items": {"AAA|recovery": {"active": True, "first_seen": "2026-11-03", "last_changed": "2026-11-03"}}}
    A.save_state(p, good)
    assert A.load_state(p) == (good, None)
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_state_means_quiet_run(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("garbage", encoding="utf-8")
    st, _ = A.load_state(p)
    c = ser([100.0] * 30 + [95.0, 110.0])
    al, st = A.evaluate_alerts([row("AAA", True, True)], {"AAA": c}, st, cfg(), "2026-11-03")
    assert al == [] and st["initialized"] == "2026-11-03"


# ---------- no look-ahead, determinism, order ----------
def test_no_look_ahead_and_deterministic():
    c = ser([100.0] * 30 + [95.0, 110.0, 50.0, 40.0])        # bars after asof must not matter
    asof = day(c, -3)
    _, st = A.evaluate_alerts([row()], {"AAA": c.iloc[:-3]}, A.empty_state(), cfg(), day(c, -4))
    a1, s1 = A.evaluate_alerts([row()], {"AAA": c}, st, cfg(), asof)
    a2, s2 = A.evaluate_alerts([row()], {"AAA": c.iloc[:-2]}, st, cfg(), asof)
    assert a1 == a2 and s1 == s2
    assert has(a1, "recovery")


def test_ranking_caution_last_then_quality_then_move():
    mk = lambda t, kind, q, r5: {"ticker": t, "kind": kind, "context": {"q": q, "r5": r5, "res5": None}, "condition": "x"}
    items = [mk("C1", "caution", 99, -0.2), mk("I1", "info", 50, -0.1), mk("I2", "info", 90, -0.05),
             mk("I3", "info", 90, -0.09), mk("I4", "info", None, -0.3)]
    assert [a["ticker"] for a in A.rank_alerts(items)] == ["I3", "I2", "I1", "I4", "C1"]


# ---------- delivery ----------
def test_markdown_json_and_notification_text(tmp_path):
    al = [{"ticker": f"T{i}", "name": f"T{i} Inc", "condition": "recovery", "kind": "info",
           "headline": f"T{i}: closed back above its 20-day average", "detail": "close 10.00", "context": {}, "asof": "2026-11-03"}
          for i in range(5)]
    md = A.alerts_markdown(al)
    assert md.startswith("## Trigger alerts") and "T4: closed back above" in md and "not investment advice" in md
    assert "No conditions" in A.alerts_markdown([])
    n = A.notification_text(al)
    assert n["title"] == "Dip screen: 5 research conditions met"
    assert n["body"].count("\n") == 3 and "2 more" in n["body"]
    assert A.notification_text([]) is None
    path = A.write_alerts_json(al, tmp_path / "alerts_latest.json", "2026-11-03")
    d = json.loads(path.read_text(encoding="utf-8"))
    assert d["count"] == 5 and d["asof"] == "2026-11-03" and len(d["alerts"]) == 5


def test_config_file_loads_and_watch_override(tmp_path):
    c = A.load_alerts_config(ROOT / "config" / "alerts.toml")
    assert c.defaults.new_low_days == 60 and c.defaults.drop_continues == 0.04
    assert [w.ticker for w in c.watch] == ["NESTE.HE", "AMD", "ASML.AS", "NVDA"]      # the owner's watchlist, no levels or overrides yet
    assert all(not w.levels and not w.overrides for w in c.watch)
    p = tmp_path / "a.toml"
    p.write_text('[defaults]\nnew_low_days = 40\n[[watch]]\nticker = "AMD"\nnew_low_days = 20\nnote = "x"\n'
                 'levels = [{ price = 150.0, direction = "down" }]\n', encoding="utf-8")
    c = A.load_alerts_config(p)
    assert c.defaults.new_low_days == 40 and c.for_ticker("AMD").new_low_days == 20 and c.for_ticker("MSFT").new_low_days == 40
    assert c.watch[0].levels[0].direction == "down" and c.watch[0].note == "x"
    assert A.load_alerts_config(tmp_path / "missing.toml").watch == []


# ---------- old state keys still load; labels are neutral ----------
def test_old_state_keys_still_load_and_suppress_repeat(tmp_path):
    """State written before the label rename (keys 'recovery' and 'rsi_rebound') must load and behave as before."""
    p = tmp_path / "s.json"
    old = {"version": 1, "initialized": "2026-11-02", "asof": "2026-11-02",
           "items": {"AAA|recovery": {"active": True, "first_seen": "2026-11-02", "last_changed": "2026-11-02"},
                     "AAA|rsi_rebound": {"active": False, "first_seen": "2026-11-02", "last_changed": "2026-11-02"}}}
    p.write_text(json.dumps(old), encoding="utf-8")
    st, problem = A.load_state(p)
    assert problem is None and st == old
    assert {"recovery", "rsi_rebound"} <= set(A.CONDITIONS)
    c = ser([100.0] * 30 + [95.0, 110.0])                       # a recovery cross on the data date
    al, new = A.evaluate_alerts([row("AAA", True, True)], {"AAA": c}, st, cfg(), "2026-11-03")
    assert not has(al, "recovery")                              # already active in the old state: stays silent
    assert new["items"]["AAA|recovery"]["first_seen"] == "2026-11-02"
    assert "AAA|recovery" in new["items"]                       # rsi_rebound needs 40 bars; this series has 32


def test_old_config_keys_still_accepted(tmp_path):
    p = tmp_path / "a.toml"
    p.write_text('[defaults]\nconditions = ["recovery", "rsi_rebound"]\n', encoding="utf-8")
    assert A.load_alerts_config(p).defaults.conditions == ("recovery", "rsi_rebound")


def test_visible_alert_text_has_no_forecast_words():
    forecast = re.compile(r"rebound|recover|bounce", re.I)
    base = [100.0] * 20 + [100.0 - i for i in range(1, 25)]
    al = []
    for c in (ser([100.0] * 30 + [95.0, 110.0]), ser(base + [base[-1] + 8])):
        al += two_days([row()], c)[0]
    assert has(al, "recovery") and has(al, "rsi_rebound")
    for a in al:
        assert not forecast.search(a["headline"] + " " + a["detail"]), a
    assert not forecast.search(A.alerts_markdown(al)) and not forecast.search(json.dumps(A.notification_text(al)))
    assert any(a["headline"].endswith("RSI back above 30") for a in has(al, "rsi_rebound"))
    assert any(a["headline"].endswith("back above its 20-day average") for a in has(al, "recovery"))


# ---------- wording ----------
def test_no_banned_words_anywhere():
    rng = np.random.default_rng(3)
    cs = {
        "AAA": ser([100.0] * 30 + [95.0, 110.0]),
        "BBB": ser([100.0] * 70 + [95.0]),
        "CCC": ser([100.0] * 5 + [100.0 - i for i in range(1, 25)] + [80.0]),
        "DDD": ser(100 + np.cumsum(rng.normal(0, 1, 90))),
    }
    config = cfg(watch=[A.Watch(ticker=t, levels=[A.Level(price=p, direction="both")], note="n") for t, p in
                        (("AAA", 100.0), ("BBB", 99.0), ("CCC", 90.0), ("DDD", 100.0))])
    earn = {t: {"label": "reports_soon", "days_since_last": 50, "days_until_next": 3} for t in cs}
    rows = [row(t, True, False) for t in cs]
    _, st = A.evaluate_alerts(rows, {t: s.iloc[:-1] for t, s in cs.items()}, A.empty_state(), config, day(cs["AAA"], -2))
    al, _ = A.evaluate_alerts(rows, cs, st, config, day(cs["AAA"]), earn)
    first, _ = A.evaluate_alerts(rows, cs, A.empty_state(), config, day(cs["AAA"]))
    assert {a["condition"] for a in al} >= {"recovery", "new_low", "level_cross:100.0:up", "earnings_window"}
    texts: list[str] = []
    for a in al + first:
        texts += [a["headline"], a["detail"], a["condition"], json.dumps(a["context"])]
    texts += [A.alerts_markdown(al), json.dumps(A.notification_text(al))]
    for s in texts:
        assert not BANNED.search(s), s
    for f in ("src/dipdash/alerts.py", "config/alerts.toml", "scripts/notify.ps1"):
        txt = (ROOT / f).read_text(encoding="utf-8")
        assert not BANNED.search(txt), (f, BANNED.search(txt).group(0))


def _visible_alert_text(path: str, markers: tuple[str, ...]) -> list[str]:
    """Lines of a UI source file that carry alert wording (the alerts panel, its footer definition, the digest section)."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    lines = (root / path).read_text(encoding="utf-8").splitlines()
    return [ln for ln in lines if any(m in ln for m in markers)]


def test_ui_text_has_no_advice_words():
    tmpl = _visible_alert_text("src/template.html", ("alerts", "Alerts", "Trigger", "Research conditions", "Informational"))
    dig = _visible_alert_text("src/dipdash/digest.py", ("Trigger alerts", "Alerts could not"))
    assert tmpl and dig
    for ln in tmpl + dig:
        assert not BANNED.search(ln), ln
