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
from dipdash.data import fetch_fundamentals, fetch_indices, fetch_prices, lagging_tickers, pull_prices
from dipdash.earnings import load_earnings
from dipdash.fx import fetch_fx_to_usd
from dipdash.sources import Sources, live_sources
from dipdash.validate import validate_run
from fakes import FakeYahoo, yf_download_frame
from synth import END, flat, geometric

TODAY = date(2026, 10, 30)          # the Friday after synth.END


def nosleep(_seconds):              # injected wherever backoff or pacing would otherwise wait for real
    pass
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
    prices, source = pull_prices(list(y.prices), s.prices, lambda t: s.fallback_bars(t, "2024-10-30", str(TODAY)), sleep=nosleep)
    assert source == {"AAA": "primary", "DDD": "primary", "BBB.ST": "fallback"}
    assert "CCC" not in prices                                     # no source at all: left out, validate reports no_data
    assert prices["BBB.ST"][0].equals(fb[fb.index >= "2024-10-30"])
    assert sorted(y.called("fallback")) == ["BBB.ST", "CCC"]       # only the tickers the primary missed (pool order is free)
    assert y.called("prices") == [("AAA", "BBB.ST", "CCC", "DDD"), ("BBB.ST", "CCC")]   # one batch, then one second try for the misses


def test_empty_primary_series_falls_back():
    y = fake(empty={"AAA"}, fallback={"AAA": series()})
    _, source = pull_prices(list(y.prices), y.download, lambda t: y.fallback_bars(t, "2000-01-01", str(TODAY)), sleep=nosleep)
    assert source["AAA"] == "fallback"


def test_batch_download_raising_propagates_today():
    # When EVERY batch still fails after the retries, the error is raised: nothing to screen, the caller keeps yesterday's files.
    y = fake(down=True)
    with pytest.raises(RuntimeError, match="network unreachable"):
        pull_prices(list(y.prices), y.download, lambda t: None, sleep=nosleep)
    assert len(y.called("prices")) == 4                          # first try + 3 retries


def test_lag_and_nan_tail_reach_validation_with_severity_and_detail():
    y = fake(lag={"CCC": 6}, nan_tail={"DDD": 2})
    prices, _ = pull_prices(list(y.prices), y.download, sleep=nosleep)
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
    prices, _ = pull_prices(list(y.prices), y.download, sleep=nosleep)
    assert prices["AAA"][0].index.tz is not None
    universe = [Stock("AAA", "AAA", "US")]
    issues = validate_run(universe, {"AAA": prices["AAA"]}, {"AAA": {"currency": "USD", "marketCap": 1e11}}, Settings(), TODAY)
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
    prices, source = pull_prices(["AAA", "BBB.ST"], lambda t: out, lambda t: (series(), None), sleep=nosleep)
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
    fetch_fundamentals(list(y.prices), path, fetch_info=y.info, sleep=nosleep)
    assert len(y.called("info")) == n + 3                        # only the failed ticker is asked again (1 try + 2 retries)
    issues = validate_run([Stock("DDD", "DDD", "US")], {"DDD": (series(), None)}, {"DDD": {**f["DDD"], "marketCap": 1e11}}, Settings(), TODAY)
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


# ---- DATA-3: batched pull, retry, lag re-fetch, fallback pool, reasons -------------------------------------------
def universe(n_us=130, extra=()):
    return {**{f"U{i:03d}": series() for i in range(n_us)}, **{t: series() for t in extra}}


def test_pull_is_split_into_batches_of_60_with_a_pause_between():
    y = fake(prices=universe(130))
    pauses = []
    prices, source = pull_prices(list(y.prices), y.download, sleep=pauses.append)
    assert [len(c) for c in y.called("prices")] == [60, 60, 10] and len(prices) == 130
    assert pauses == [0.5, 0.5]                                  # between batches only; nothing missing, nobody lagging


def test_failed_batch_is_retried_with_exponential_backoff():
    y = fake(prices=universe(70), flaky=2)                       # the first two download calls raise a 429-like error
    waits, reasons = [], {}
    prices, source = pull_prices(list(y.prices), y.download, sleep=waits.append, reasons=reasons)
    assert len(prices) == 70 and set(source.values()) == {"primary"} and reasons == {}
    assert waits[:2] == [2.0, 4.0]                               # 2 s, then 4 s, then the third try works
    assert [len(c) for c in y.called("prices")] == [60, 60, 60, 10]


def test_a_dead_batch_goes_to_the_fallback_and_every_ticker_gets_a_reason():
    # Calls 1-4 are batch 1 (first try + 3 retries) and all raise; batch 2 works.
    y = fake(prices=universe(70), flaky=4, fallback={"U000": series()})
    reasons = {}
    s = y.sources()
    prices, source = pull_prices(list(y.prices), s.prices, lambda t: s.fallback_bars(t, "2000-01-01", str(TODAY)),
                                 sleep=nosleep, reasons=reasons)
    assert set(prices) == {f"U{i:03d}" for i in list(range(60, 70)) + [0]} and source["U000"] == "fallback"
    assert "failed after 4 attempts" in reasons["U001"] and "429" in reasons["U001"] and "fallback had no data" in reasons["U001"]
    assert "used the OpenBB fallback" in reasons["U000"] and "429" in reasons["U000"]        # saved, but the reason is kept for data_quality
    assert "U060" not in reasons


def test_tickers_yahoo_dropped_get_one_second_try():
    y = fake(fail_first={"CCC"})                                 # all-NaN on the first call, fine on the second
    reasons = {}
    prices, source = pull_prices(list(y.prices), y.download, sleep=nosleep, reasons=reasons)
    assert source["CCC"] == "primary" and "CCC" not in reasons
    assert y.called("prices")[1] == ("CCC",)


def test_reasons_say_what_went_wrong_for_each_kind_of_miss():
    y = fake(fail={"CCC"}, empty={"DDD"})
    reasons = {}
    pull_prices(list(y.prices) + ["ZZZ"], y.download, lambda t: None, sleep=nosleep, reasons=reasons)
    assert "only empty (NaN) closes" in reasons["CCC"] and "empty price series" in reasons["DDD"]
    assert "no rows" in reasons["ZZZ"] and all("fallback had no data" in r for r in reasons.values())


def test_a_fallback_that_raises_is_recorded_not_fatal():
    y = fake(fail={"CCC"})

    def boom(t):
        raise ConnectionError("openbb down")

    reasons = {}
    prices, _ = pull_prices(list(y.prices), y.download, boom, sleep=nosleep, reasons=reasons)
    assert "CCC" not in prices and "OpenBB fallback raised ConnectionError: openbb down" in reasons["CCC"]


def test_lagging_pa_ticker_is_refetched_and_newer_bars_replace_the_old():
    prices = {"AIR.PA": series(), "MC.PA": series(), "OR.PA": series(), "SU.PA": series(), "AAA": series()}
    y = fake(prices=prices, lag={"SU.PA": 3}, lag_heals={"SU.PA"})
    reasons = {}
    got, source = pull_prices(list(prices), y.download, sleep=nosleep, reasons=reasons)
    assert got["SU.PA"][0].index[-1] == pd.Timestamp(END)        # the second request returned the missing days
    assert y.called("prices")[1] == ("SU.PA",)                   # only the lagging .PA name, not its peers or the US name
    assert reasons == {}


def test_lag_that_a_refetch_cannot_fix_is_recorded_and_the_old_bars_kept():
    prices = {"AIR.PA": series(), "MC.PA": series(), "SU.PA": series()}
    y = fake(prices=prices, lag={"SU.PA": 3})
    reasons = {}
    got, _ = pull_prices(list(prices), y.download, sleep=nosleep, reasons=reasons)
    assert got["SU.PA"][0].index[-1] == pd.Timestamp(END) - pd.offsets.BDay(3)
    assert "behind its exchange peers" in reasons["SU.PA"] and "no newer bar" in reasons["SU.PA"]


def test_lagging_is_judged_against_the_same_exchange_only():
    d = date
    late = lagging_tickers({"A": d(2026, 10, 29), "B": d(2026, 10, 29), "C": d(2026, 10, 27),
                            "X.PA": d(2026, 10, 28), "Y.PA": d(2026, 10, 28)})
    assert late == {"C": d(2026, 10, 29)}                        # Paris closing a day "earlier" than New York is not lag
    assert lagging_tickers({"X.PA": d(2026, 10, 28)}) == {}      # a group of one has no peers
    assert lagging_tickers({"A": d(2026, 11, 20), "B": d(2026, 10, 29), "C": d(2026, 10, 29)}) == {}   # one future-dated bar


def test_pull_never_writes_raw_files(tmp_path):
    y = fake()
    pull_prices(list(y.prices), y.download, sleep=nosleep)
    assert list(tmp_path.iterdir()) == []                        # saving stays with cache.save_raw_prices ("x" mode)


# ---- DATA-6: fundamentals retry, stale flag, spread ---------------------------------------------------------------
DAY = 86400.0


def test_fundamentals_fetch_is_retried_then_succeeds(tmp_path):
    y = fake(info_flaky={"AAA": 2})
    waits, status = [], {}
    f = fetch_fundamentals(["AAA"], tmp_path / "f.json", fetch_info=y.info, sleep=waits.append, pace=0, status=status, now=1000.0)
    assert f["AAA"]["currency"] == "USD" and waits == [2.0, 4.0] and status["AAA"]["error"] is None


def test_fundamentals_failure_after_retries_has_a_reason_and_no_entry(tmp_path):
    y = fake(fail={"CCC"})
    status = {}
    f = fetch_fundamentals(["CCC"], tmp_path / "f.json", fetch_info=y.info, sleep=nosleep, pace=0, status=status, now=1000.0)
    assert f == {"CCC": {}} and "failed after 3 attempts" in status["CCC"]["error"] and "404" in status["CCC"]["error"]
    assert status["CCC"]["stale"] is False and status["CCC"]["age_days"] is None


def test_stale_flag_only_when_older_than_the_cache_age_and_not_refreshable(tmp_path):
    path, y = tmp_path / "f.json", fake()
    t0 = 1_000_000.0
    fetch_fundamentals(["AAA", "CCC"], path, fetch_info=y.info, sleep=nosleep, pace=0, now=t0)
    down = fake(fail={"AAA", "CCC"})                             # the info endpoint is dead from now on
    status = {}
    f = fetch_fundamentals(["AAA", "CCC"], path, fetch_info=down.info, sleep=nosleep, pace=0, now=t0 + 7 * DAY, status=status)
    assert f["AAA"]["currency"] == "USD"                         # old value kept
    assert status["AAA"]["stale"] is False and status["AAA"]["error"] is not None   # due for refresh, failed, still inside 7 days
    status = {}
    fetch_fundamentals(["AAA"], path, fetch_info=down.info, sleep=nosleep, pace=0, now=t0 + 8 * DAY, status=status)
    assert status["AAA"]["stale"] is True and round(status["AAA"]["age_days"]) == 8 and "404" in status["AAA"]["error"]
    status = {}
    fetch_fundamentals(["AAA"], path, fetch_info=y.info, sleep=nosleep, pace=0, now=t0 + 8 * DAY, status=status)
    assert status["AAA"]["stale"] is False and status["AAA"]["fetched_at"]


def test_refreshes_are_spread_over_the_week(tmp_path):
    names = [f"T{i:03d}" for i in range(348)]
    y = fake(prices={t: series() for t in names})
    path, per_night = tmp_path / "f.json", []
    t0 = 2_000_000.0
    for night in range(28):
        before = len(y.called("info"))
        fetch_fundamentals(names, path, fetch_info=y.info, sleep=nosleep, pace=0, now=t0 + night * DAY)
        per_night.append(len(y.called("info")) - before)
    assert per_night[0] == 348 and sum(per_night[1:4]) == 0      # cold start fetches all; nothing is due in the first 3 days
    later = per_night[4:]
    assert max(later) <= 100                                     # capped at about 2/7 of the list per night
    assert sum(1 for n in later if n > 0) >= 15                  # refreshes happen on many different nights
    status = {}
    fetch_fundamentals(names, path, fetch_info=y.info, sleep=nosleep, pace=0, now=t0 + 28 * DAY, status=status)
    assert not any(s["stale"] for s in status.values()) and max(s["age_days"] for s in status.values()) <= 7


def test_refresh_age_is_deterministic_and_inside_bounds():
    ages = {t: data.refresh_age_days(t) for t in (f"T{i}" for i in range(200))}
    assert set(ages.values()) == {4, 5, 6, 7}
    assert data.refresh_age_days("AAA") == data.refresh_age_days("AAA") == ages.get("AAA", data.refresh_age_days("AAA"))
    assert data.refresh_age_days("AAA", 7, 7) == 7


def test_requests_are_paced_across_threads(tmp_path):
    y = fake(prices={f"T{i}": series() for i in range(5)})
    waits = []
    fetch_fundamentals(list(y.prices), tmp_path / "f.json", fetch_info=y.info, sleep=waits.append, pace=0.25, workers=4, now=1.0)
    assert len(waits) >= 3 and all(0 < w <= 1.0 + 1e-6 for w in waits)    # threads queue up behind the pacer instead of bursting


def test_unreadable_cache_is_kept_aside_and_rebuilt(tmp_path):
    path = tmp_path / "f.json"
    path.write_text('{"AAA": {"ts": 1, "d"')                     # a half-written file from an older, non-atomic version
    f = fetch_fundamentals(["AAA"], path, fetch_info=fake().info, sleep=nosleep, pace=0, now=1000.0)
    assert f["AAA"]["currency"] == "USD" and list(tmp_path.glob("f.json.bad-*"))
    assert "AAA" in __import__("json").loads(path.read_text())
