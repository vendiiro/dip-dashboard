import json
import subprocess
import sys
from datetime import date

import pytest

from dipdash.cli import main
from dipdash.config import ROOT, Settings, Stock
from dipdash.dashboard import TEMPLATE, build_payload, render_html
from dipdash.demo import demo_inputs
from dipdash.config import load_universe
from synth import flat, geometric, slide, volume

S = Settings()
TODAY = date(2026, 10, 30)
GOOD = {"returnOnEquity": 0.2, "profitMargins": 0.15, "debtToEquity": 80, "freeCashflow": 1e9,
        "revenueGrowth": 0.05, "marketCap": 1e11, "forwardPE": 18.04, "currency": "EUR"}
UNI = [Stock("DIP", "Dipper", "US", "Tech"), Stock("CALM", "Calm Co", "Europe", "Staples"),
       Stock("OLD", "Old Bars", "US"), Stock("SHORT", "Short", "US"), Stock("GONE", "Gone", "US")]


def inputs():
    prices = {
        "DIP": (slide(), volume(260)),
        "CALM": (geometric(260, 0.0005), volume(260)),
        "OLD": (geometric(260, 0.0005, end="2026-10-20"), None),
        "SHORT": (geometric(30, 0.0005), None),
    }
    return prices, {"DIP": GOOD, "CALM": GOOD, "OLD": GOOD}


def test_rows_skips_and_reasons():
    p = build_payload(UNI, *inputs(), S, today=TODAY)
    assert [r["t"] for r in p["rows"]] == ["DIP", "CALM"]
    assert {d["t"]: d["reason"] for d in p["data_quality"]} == {
        "OLD": "stale", "SHORT": "short_history", "GONE": "no_price_data"}


def test_dip_row_is_flagged_with_reasons_and_setup():
    row = build_payload(UNI, *inputs(), S, today=TODAY)["rows"][0]
    assert row["dip"] and row["setup"] == "Quality dip" and row["q"] == 100
    assert any("5-day" in w for w in row["why"])
    assert row["sector"] == "Tech" and row["fpe"] == 18.0 and row["ccy"] == "EUR"


def test_calm_row_is_not_a_dip():
    row = build_payload(UNI, *inputs(), S, today=TODAY)["rows"][1]
    assert not row["dip"] and row["why"] == [] and row["setup"] == "No dip"


def test_missing_fundamentals_do_not_break_a_row():
    prices, funds = inputs()
    row = build_payload(UNI, prices, {}, S, today=TODAY)["rows"][0]
    assert row["q"] is None and row["setup"] == "Dip, no fundamentals" and row["ccy"] == ""


def test_news_is_fetched_only_for_fallers():
    calls = []

    def news(t):
        calls.append(t)
        return [{"title": "h", "src": "s", "url": ""}]

    p = build_payload(UNI, *inputs(), S, news_fn=news, today=TODAY)
    assert calls == ["DIP"]
    assert p["rows"][0]["news"][0]["title"] == "h" and p["rows"][1]["news"] == []


def test_payload_is_strict_json_even_for_flat_prices():
    prices = {"FLAT": (flat(100), None)}
    p = build_payload([Stock("FLAT", "Flat", "US")], prices, {}, S, today=TODAY)
    json.dumps(p, allow_nan=False)
    assert p["rows"][0]["rsi"] is None


def test_settings_change_the_outcome():
    from dataclasses import replace
    strict = replace(S, dip=replace(S.dip, drop_5d=0.20))
    assert build_payload(UNI, *inputs(), strict, today=TODAY)["rows"][0]["dip"] is False


# ---- rendering --------------------------------------------------------------
def test_render_roundtrips_payload_through_a_template(tmp_path):
    t = tmp_path / "t.html"
    t.write_text("<script>const DATA = __DATA__;</script>")
    payload = {"rows": [{"t": "ÅÄÖ", "news": [{"title": 'He said "hi" & left'}]}]}
    out = render_html(payload, t)
    body = out.split("const DATA = ")[1].rsplit(";</script>", 1)[0]
    assert json.loads(body) == payload


def test_headline_cannot_close_the_script_tag(tmp_path):
    t = tmp_path / "t.html"
    t.write_text("<script>const DATA = __DATA__;</script>")
    evil = {"rows": [{"news": [{"title": "</script><script>alert(1)</script>"}]}]}
    out = render_html(evil, t)
    assert out.count("</script>") == 1
    assert json.loads(out.split("const DATA = ")[1].rsplit(";</script>", 1)[0]) == evil


def test_real_template_has_exactly_one_placeholder():
    assert TEMPLATE.read_text(encoding="utf-8").count("__DATA__") == 1


# ---- demo + CLI -------------------------------------------------------------
def test_demo_inputs_cover_the_universe_and_are_reproducible():
    u = load_universe()
    (p1, f1), (p2, f2) = demo_inputs(u), demo_inputs(u)
    assert list(p1) == [s.ticker for s in u] and f1 == f2
    assert p1["AAPL"][0].equals(p2["AAPL"][0])


def test_demo_run_writes_a_dashboard(tmp_path):
    out = tmp_path / "sub" / "demo.html"
    assert main(["--demo", "--out", str(out)]) == 0
    html = out.read_text(encoding="utf-8")
    assert "__DATA__" not in html and '"demo": true' in html and html.count('"t": "') >= 60


def test_legacy_wrapper_still_runs(tmp_path):
    out = tmp_path / "w.html"
    r = subprocess.run([sys.executable, str(ROOT / "src" / "dip_screener.py"), "--demo", "--out", str(out)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert out.exists() and "Wrote" in r.stdout


def test_custom_universe_and_settings_flags(tmp_path):
    u = tmp_path / "u.csv"
    u.write_text("ticker,name,region\nAAA,Alpha,US\nBBB,Beta,US\n")
    out = tmp_path / "o.html"
    assert main(["--demo", "--universe", str(u), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").count('"t": "') == 2        # one per stock row


# ---- price pull with fallback + currency-aware payload -----------------------
def test_pull_prices_uses_the_fallback_only_for_missing_or_empty_tickers():
    from dipdash.data import pull_prices
    good = (geometric(60, 0.001), None)
    primary = lambda ts: {"A": good, "B": (geometric(5, 0.0).iloc[0:0], None), "C": None}
    asked = []
    fallback = lambda t: asked.append(t) or ((good if t != "D" else None))
    prices, source = pull_prices(["A", "B", "C", "D"], primary, fallback)
    assert asked == ["B", "C", "D"]
    assert source == {"A": "primary", "B": "fallback", "C": "fallback"} and set(prices) == {"A", "B", "C"}


def test_pull_prices_without_a_fallback_returns_what_the_primary_gave():
    from dipdash.data import pull_prices
    prices, source = pull_prices(["A", "B"], lambda ts: {"A": (geometric(60, 0.001), None)})
    assert list(prices) == ["A"] and source == {"A": "primary"}


def test_payload_converts_market_cap_to_usd_and_records_the_rates():
    sek = {**GOOD, "currency": "SEK", "marketCap": 150e9}     # about 15B USD: fails the 20B check
    uni = [Stock("DIP", "Dipper", "Nordic")]
    p = build_payload(uni, {"DIP": (slide(), volume(260))}, {"DIP": sek}, S, today=TODAY, fx_to_usd={"SEK": 0.1})
    assert p["fx_to_usd"] == {"SEK": 0.1} and p["rows"][0]["q"] == 83
    p2 = build_payload(uni, {"DIP": (slide(), volume(260))}, {"DIP": sek}, S, today=TODAY, fx_to_usd={"SEK": 0.2})
    assert p2["rows"][0]["q"] == 100


def test_demo_run_writes_a_quality_log_next_to_the_dashboard(tmp_path):
    assert main(["--demo", "--out", str(tmp_path / "d.html")]) == 0
    log = tmp_path / "data_quality.demo.csv"
    assert log.read_text().startswith("run_at,ticker,check,severity,detail")
    assert not (tmp_path / "data_quality.csv").exists()          # a demo run never touches the real log
    assert len(log.read_text().splitlines()) == 1                 # and the demo data itself is clean (no currency warnings)


# ---- payload extras for the dashboard ---------------------------------------
from datetime import datetime  # noqa: E402

from dipdash.config import IndexSpec  # noqa: E402
from dipdash.data import fetch_indices  # noqa: E402
from dipdash.validate import Issue  # noqa: E402

IDX = [{"symbol": "^X", "name": "Idx US", "region": "US", "price": 100.0, "r1": -0.01, "r5": -0.02, "asof": "2026-10-29"}]


def test_each_row_carries_chart_history_and_yesterdays_state():
    row = build_payload(UNI, *inputs(), S, today=TODAY)["rows"][0]
    assert len(row["hist"]["c"]) == 252 and row["hist"]["c"][-1] == row["price"]
    assert row["prev"]["r5"] > row["r5"]                  # the slide continued on the last day
    assert set(row["prev"]) == {"r1", "r5", "r21", "dd20", "knife", "dip"}


def test_yesterday_is_the_same_stock_one_bar_earlier():
    prices, funds = inputs()
    from dipdash.metrics import compute_metrics
    close, vol = prices["DIP"]
    expected = compute_metrics(close.iloc[:-1], vol.iloc[:-1])
    prev = build_payload(UNI, prices, funds, S, today=TODAY)["rows"][0]["prev"]
    assert prev["r5"] == expected["r5"] and prev["dd20"] == expected["dd20"]


def test_a_stock_with_too_little_history_for_yesterday_has_no_prev():
    from dipdash.config import Stock
    prices = {"S": (geometric(MIN_ROWS := 60, 0.001), None)}
    row = build_payload([Stock("S", "S", "US")], prices, {}, S, today=TODAY)["rows"][0]
    assert row["prev"] is None


def test_move_vs_index_uses_the_region_index_and_needs_the_same_bar_date():
    p = build_payload(UNI, *inputs(), S, today=TODAY, indices=IDX)
    dip, calm = p["rows"]
    assert dip["idx"] == "Idx US" and dip["x5"] == pytest.approx(dip["r5"] - (-0.02), abs=1e-4)
    assert calm["idx"] is None and calm["x5"] is None            # CALM is a Europe stock: no index for its region
    late = [{**IDX[0], "asof": "2026-10-28"}]
    assert build_payload(UNI, *inputs(), S, today=TODAY, indices=late)["rows"][0]["x5"] is None


def test_payload_echoes_thresholds_issues_and_timestamp():
    now = datetime(2026, 10, 30, 0, 15)
    p = build_payload(UNI, *inputs(), S, today=TODAY, now=now, issues=[Issue("OLD", "stale", "error", "x")])
    assert p["generated"] == "2026-10-30 00:15" and p["tz"] == "Europe/Helsinki"
    assert p["settings"]["dip"]["drop_5d"] == 0.07 and p["settings"]["quality"]["min_score"] == 60
    assert p["settings"]["knife"]["drawdown_52w"] == 0.35
    assert p["issues"] == [{"ticker": "OLD", "check": "stale", "severity": "error", "detail": "x"}]
    json.dumps(p, allow_nan=False)


def test_fetch_indices_keeps_working_ones_and_skips_failures():
    specs = [IndexSpec("^A", "A", "US"), IndexSpec("^B", "B", "Europe"), IndexSpec("^C", "C", "Nordic"), IndexSpec("^D", "D", "US")]

    def fake(sym):
        if sym == "^B":
            raise RuntimeError("down")
        return None if sym == "^C" else geometric(10, 0.01, start=100.0)

    got = fetch_indices(specs, fake)
    assert [g["symbol"] for g in got] == ["^A", "^D"]
    assert got[0]["name"] == "A" and got[0]["region"] == "US" and got[0]["asof"] == "2026-10-29"


# ---- residual and earnings fields in the payload ----------------------------------------------------------------
def test_rows_carry_residual_and_earnings_fields_and_degrade_to_none_with_a_reason():
    prices, funds = inputs()
    rows = build_payload(UNI, prices, funds, S, today=TODAY)["rows"]
    r = next(x for x in rows if x["t"] == "DIP")
    assert r["res5"] is None and r["beta"] is None and r["res_why"] and r["earn"] is None      # nothing supplied: no guess
    ctx = {"DIP": {"last": "2026-10-28", "next": None, "days_since_last": 2, "days_until_next": None, "label": "reported_recently",
                   "note": "", "estimated": False, "stale": False, "error": None, "fetched_at": None}}
    r2 = next(x for x in build_payload(UNI, prices, funds, S, today=TODAY, earnings=ctx)["rows"] if x["t"] == "DIP")
    assert r2["earn"]["label"] == "reported_recently"
    json.dumps(build_payload(UNI, prices, funds, S, today=TODAY, earnings=ctx))                # stays valid JSON


def test_a_failing_residual_never_aborts_the_payload(monkeypatch):
    import dipdash.dashboard as d
    monkeypatch.setattr(d, "residual_move", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    prices, funds = inputs()
    idx = [{"symbol": "^GSPC", "name": "S&P 500", "region": "US", "suffixes": [], "price": 1.0, "r1": 0.0, "r5": 0.0, "asof": "2026-10-30", "closes": {}}]
    rows = build_payload(UNI, prices, funds, S, today=TODAY, indices=idx, index_history={"^GSPC": prices["DIP"][0]})["rows"]
    assert any("could not be computed" in (x["res_why"] or "") for x in rows)


def test_rows_with_a_partial_bar_issue_are_marked_partial():
    from dipdash.validate import Issue
    prices, funds = inputs()
    issues = [Issue("DIP", "partial_bar", "warn", "last bar is dated today")]
    rows = {r["t"]: r for r in build_payload(UNI, prices, funds, S, today=TODAY, issues=issues)["rows"]}
    assert rows["DIP"]["partial"] is True and rows["CALM"]["partial"] is False
