"""DATA-1 half 1: the Sources bundle, the FakeYahoo test double, and the existing seams driven by it. No network:
an autouse tripwire makes `import yfinance` / `import openbb` fail, so any accidental real call errors loudly."""
import dataclasses
import os
import subprocess
import sys
import types
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from dipdash import data, earnings, fx, openbb_source
from dipdash.config import IndexSpec, Settings, Stock
from dipdash.data import fetch_fundamentals, fetch_indices, fetch_prices, pull_prices
from dipdash.earnings import load_earnings
from dipdash.fx import fetch_fx_to_usd
from dipdash.sources import Sources, live_sources
from dipdash.validate import validate_run
from fakes import FakeYahoo, yf_download_frame
from synth import END, flat, geometric

TODAY = date(2026, 10, 30)          # the Friday after synth.END
SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", None)        # None in sys.modules: `import yfinance` raises ImportError
    monkeypatch.setitem(sys.modules, "openbb", None)


def series(n=300, daily=0.001):
    return geometric(n, daily)


def fake(**kw) -> FakeYahoo:
    prices = kw.pop("prices", None) or {t: series() for t in ("AAA", "BBB.ST", "CCC", "DDD")}
    return FakeYahoo(prices, **kw)


# ---- the bundle ------------------------------------------------------------------------------------------------
def test_importing_sources_and_building_live_sources_loads_no_network_library():
    code = ("import sys, dipdash.sources as s; b = s.live_sources(); "
            "print(sorted(m for m in sys.modules if m.split('.')[0] in ('yfinance', 'openbb')))")
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert out.stdout.strip() == "[]"


def test_live_sources_are_the_real_functions():
    s = live_sources()
    assert s.name == "live"
    assert s.prices is data.fetch_prices and s.fundamentals is data.fetch_fundamentals
    assert s.fallback_bars is openbb_source.fetch_bars and s.raw_closes is data.fetch_raw_closes
    assert s.fx is fx._yahoo_last_close and s.index is data._yahoo_index_close
    assert s.earnings is earnings.fetch_yfinance and s.news is data.fetch_news


def test_sources_is_frozen_and_complete():
    s = fake().sources()
    assert s.name == "fake"
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.prices = None
    assert all(callable(getattr(s, f.name)) for f in dataclasses.fields(Sources) if f.name != "name")


# ---- prices --------------------------------------------------------------------------------------------------
def test_primary_failure_uses_fallback_and_tags_it():
    fb = series(300, 0.002)
    y = fake(fail={"BBB.ST", "CCC"}, fallback={"BBB.ST": fb})
    s = y.sources()
    prices, source = pull_prices(list(y.prices), s.prices, lambda t: s.fallback_bars(t, "2024-10-30", str(TODAY)))
    assert source == {"AAA": "primary", "DDD": "primary", "BBB.ST": "fallback"}
    assert "CCC" not in prices                                     # no source at all: left out, validate reports no_data
    assert prices["BBB.ST"][0].equals(fb[fb.index >= "2024-10-30"])
    assert y.called("fallback") == ["BBB.ST", "CCC"]               # only the tickers the primary missed
    assert y.called("prices") == [("AAA", "BBB.ST", "CCC", "DDD")]  # one batch call


def test_empty_primary_series_falls_back():
    y = fake(empty={"AAA"}, fallback={"AAA": series()})
    _, source = pull_prices(list(y.prices), y.download, lambda t: y.fallback_bars(t, "2000-01-01", str(TODAY)))
    assert source["AAA"] == "fallback"


def test_batch_download_raising_propagates_today():
    # Pins current behaviour for half 2: pull_prices does not catch a primary that raises (real yf.download rarely does).
    y = fake(down=True)
    with pytest.raises(RuntimeError, match="network unreachable"):
        pull_prices(list(y.prices), y.download, lambda t: None)


def test_lag_and_nan_tail_reach_validation_with_severity_and_detail():
    y = fake(lag={"CCC": 6}, nan_tail={"DDD": 2})
    prices, _ = pull_prices(list(y.prices), y.download)
    assert prices["CCC"][0].index[-1] == pd.Timestamp(END) - pd.offsets.BDay(6)
    assert prices["DDD"][0].iloc[-2:].isna().all() and prices["DDD"][0].index[-1] == pd.Timestamp(END)
    funds = {t: {"currency": c} for t, c in (("AAA", "USD"), ("BBB.ST", "SEK"), ("CCC", "USD"), ("DDD", "USD"))}
    universe = [Stock(t, t, "US") for t in prices]
    got = {(i.ticker, i.check): i for i in validate_run(universe, prices, funds, Settings(), TODAY)}
    assert got[("CCC", "stale")].severity == "error" and "older than" in got[("CCC", "stale")].detail
    assert got[("DDD", "empty_last_bar")].severity == "info" and "last 2 close(s) empty" in got[("DDD", "empty_last_bar")].detail
    assert not any(t == "AAA" for t, _ in got)


def test_tz_aware_mode_still_validates_by_date():
    y = fake(tz="America/New_York")
    prices, _ = pull_prices(list(y.prices), y.download)
    assert prices["AAA"][0].index.tz is not None
    universe = [Stock("AAA", "AAA", "US")]
    issues = validate_run(universe, {"AAA": prices["AAA"]}, {"AAA": {"currency": "USD"}}, Settings(), TODAY)
    assert issues == []


def test_fetch_prices_parses_a_yf_download_shaped_frame(monkeypatch):
    bars = {"AAA": (series(), flat(300, 1e6)), "BBB.ST": (series(), flat(300, 2e5))}
    seen = {}

    def download(tickers, **kw):
        seen.update(kw)
        return yf_download_frame(bars, missing={"BBB.ST"})

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=download))
    out = fetch_prices(["AAA", "BBB.ST", "ZZZ"], start="2024-10-30")
    assert seen["auto_adjust"] is True and seen["group_by"] == "ticker" and seen["start"] == "2024-10-30"
    assert out["AAA"][0].equals(bars["AAA"][0]) and out["AAA"][1].equals(bars["AAA"][1])
    assert out["BBB.ST"][0].isna().all()                      # Yahoo's failed ticker: all-NaN, then pull_prices falls back
    assert "ZZZ" not in out                                    # not in the frame at all: omitted
    prices, source = pull_prices(["AAA", "BBB.ST"], lambda t: out, lambda t: (series(), None))
    assert source == {"AAA": "primary", "BBB.ST": "fallback"}


def test_fetch_prices_single_ticker_flat_frame(monkeypatch):
    c = series()
    frame = pd.DataFrame({"Close": c, "Volume": flat(300, 5.0)})
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=lambda *a, **k: frame))
    out = fetch_prices(["AAA"])
    assert out["AAA"][0].equals(c)


# ---- fundamentals through the real cache ------------------------------------------------------------------------
def test_fundamentals_seam_uses_cache_and_reports_missing_currency(tmp_path):
    y = fake(fail={"CCC"}, no_currency={"DDD"}, fund={"AAA": {"returnOnEquity": 0.31}})
    path = tmp_path / "fundamentals.json"
    f = y.sources().fundamentals(list(y.prices), path)
    assert f["AAA"]["returnOnEquity"] == 0.31 and f["AAA"]["currency"] == "USD"
    assert f["BBB.ST"]["currency"] == "SEK"
    assert f["CCC"] == {}                                       # a failed info call: empty, not a crash
    assert f["DDD"]["currency"] is None
    assert len(list((tmp_path / "raw" / "yfinance_fundamentals").glob("*.json"))) == 1
    n = len(y.called("info"))
    fetch_fundamentals(list(y.prices), path, fetch_info=y.info)
    assert len(y.called("info")) == n + 1                       # only the failed ticker is asked again; the rest is cached
    issues = validate_run([Stock("DDD", "DDD", "US")], {"DDD": (series(), None)}, {"DDD": f["DDD"]}, Settings(), TODAY)
    assert [(i.check, i.severity) for i in issues] == [("currency_missing", "warn")]


def test_fundamentals_default_needs_yfinance_only_when_fetching(tmp_path):
    path = tmp_path / "fundamentals.json"
    fetch_fundamentals(["AAA"], path, fetch_info=fake().info)
    assert fetch_fundamentals(["AAA"], path)["AAA"]["currency"] == "USD"   # all cached: the default fetcher is never called


# ---- indices, FX, earnings, news -------------------------------------------------------------------------------
def test_index_absent_is_omitted_and_history_filled_for_the_rest():
    y = fake(index={"^GSPC": series(500)}, tz="America/New_York")
    specs = [IndexSpec("^GSPC", "S&P 500", "US"), IndexSpec("^OMXS30", "OMXS30", "Nordic")]
    hist: dict = {}
    rows = fetch_indices(specs, fetch_close=y.sources().index, history=hist)
    assert [r["symbol"] for r in rows] == ["^GSPC"] and set(hist) == {"^GSPC"}
    assert len(hist["^GSPC"]) == 500 and len(rows[0]["closes"]) == 12
    assert y.called("index") == ["^GSPC", "^OMXS30"]


def test_fx_pair_absent_is_omitted():
    y = fake(fx={"SEK": 0.095, "GBP": 1.3})
    rates = fetch_fx_to_usd(["USD", "SEK", "GBp", "CHF", None], fetch_last=y.sources().fx)
    assert rates == {"SEK": 0.095, "GBP": 1.3}
    assert sorted(y.called("fx")) == ["CHFUSD=X", "GBPUSD=X", "SEKUSD=X"]


def test_earnings_failure_is_recorded_not_raised(tmp_path):
    y = fake(fail={"CCC"}, earnings={"AAA": {"rows": [{"d": "2026-10-20", "rep": True}], "cal": ["2027-01-25"]}})
    got = load_earnings(["AAA", "CCC"], tmp_path / "earnings.json", TODAY, fetch=y.sources().earnings,
                        sleep=lambda s: None, now=1_793_000_000.0)
    assert got["AAA"]["last"] == "2026-10-20" and got["AAA"]["error"] is None
    assert "earnings unavailable" in got["CCC"]["error"]


def test_news_and_raw_closes():
    y = fake(fail={"CCC"}, news={"AAA": [{"title": "t", "src": "s", "url": "u"}]})
    s = y.sources()
    assert s.news("AAA") == [{"title": "t", "src": "s", "url": "u"}] and s.news("DDD") == []
    with pytest.raises(RuntimeError):
        s.news("CCC")
    rc = s.raw_closes("AAA", "2026-10-01", "2026-10-29")
    assert rc.index[0] >= pd.Timestamp("2026-10-01") and rc.index[-1] < pd.Timestamp("2026-10-29")
    assert s.raw_closes("CCC", "2026-10-01", "2026-10-29") is None
