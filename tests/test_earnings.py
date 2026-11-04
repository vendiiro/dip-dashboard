"""Earnings dates: classifier, plausibility rules, 7-day cache. No network: the fetch function is injected."""
import json
import time
from datetime import date

import pytest

from dipdash.config import EarningsSettings, Settings, load_settings
from dipdash.earnings import days_between, earnings_context, load_earnings, resolve_dates

ASOF = date(2026, 11, 4)          # a Wednesday
NO_SLEEP = lambda s: None


def row(d, rep):
    return {"d": d, "rep": rep}


GOOD = {"rows": [row("2027-01-28", False), row("2026-11-02", True), row("2026-07-30", True)], "cal": ["2027-01-28"]}


# ---- settings -------------------------------------------------------------------------------------------------
def test_earnings_settings_defaults_match_the_file():
    assert Settings().earnings == EarningsSettings(recent_days=5, soon_days=10)
    assert load_settings().earnings == Settings().earnings


def test_old_settings_file_without_the_section_still_loads(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text("[dip]\ndrop_1d = 0.03\n")
    assert load_settings(p).earnings == EarningsSettings()


# ---- days_between ---------------------------------------------------------------------------------------------
def test_days_between_counts_weekdays_and_keeps_the_sign():
    assert days_between(date(2026, 10, 30), date(2026, 11, 2)) == 1       # Fri -> Mon
    assert days_between(date(2026, 10, 31), date(2026, 11, 2)) == 0       # Sat -> Mon
    assert days_between(date(2026, 10, 28), date(2026, 11, 4)) == 5
    assert days_between(date(2026, 11, 4), date(2026, 10, 28)) == -5


# ---- classifier: reported recently ----------------------------------------------------------------------------
def test_exactly_5_trading_days_ago_is_recent_and_6_is_not():
    five = earnings_context(date(2026, 10, 28), None, ASOF)     # Wed -> Wed = 5
    six = earnings_context(date(2026, 10, 27), None, ASOF)      # Tue -> Wed = 6
    assert five["days_since_last"] == 5 and five["label"] == "reported_recently"
    assert six["days_since_last"] == 6 and six["label"] == "none"


def test_reported_today_is_recent_with_zero_days():
    c = earnings_context(ASOF, None, ASOF)
    assert c["days_since_last"] == 0 and c["label"] == "reported_recently"


def test_weekends_do_not_count_as_trading_days():
    fri = date(2026, 10, 30)
    assert earnings_context(fri, None, date(2026, 11, 6))["days_since_last"] == 5       # Fri -> next Fri
    assert earnings_context(fri, None, date(2026, 11, 6))["label"] == "reported_recently"
    assert earnings_context(fri, None, date(2026, 11, 7))["days_since_last"] == 6       # Saturday: Friday has now passed
    assert earnings_context(fri, None, date(2026, 11, 8))["label"] == "none"            # Sunday adds nothing
    sat = date(2026, 10, 31)                                                           # a weekend report date counts from Monday
    assert earnings_context(sat, None, date(2026, 11, 6))["days_since_last"] == 4


# ---- classifier: reports soon ---------------------------------------------------------------------------------
def test_next_within_10_trading_days_is_soon_and_11_is_not():
    ten = earnings_context(None, date(2026, 11, 18), ASOF)       # Wed -> Wed two weeks = 10
    eleven = earnings_context(None, date(2026, 11, 19), ASOF)
    assert ten["days_until_next"] == 10 and ten["label"] == "reports_soon"
    assert eleven["days_until_next"] == 11 and eleven["label"] == "none"


def test_next_report_on_the_data_date_is_soon_with_zero_days():
    c = earnings_context(None, ASOF, ASOF)
    assert c["days_until_next"] == 0 and c["label"] == "reports_soon"


def test_thresholds_come_from_settings():
    s = EarningsSettings(recent_days=2, soon_days=3)
    assert earnings_context(date(2026, 10, 30), None, ASOF, s)["label"] == "none"            # 3 days > 2
    assert earnings_context(None, date(2026, 11, 9), ASOF, s)["label"] == "reports_soon"     # 3


def test_recent_wins_when_both_apply_and_note_mentions_next():
    c = earnings_context(date(2026, 11, 2), date(2026, 11, 10), ASOF)
    assert c["label"] == "reported_recently" and c["days_until_next"] == 4


# ---- missing / implausible ------------------------------------------------------------------------------------
def test_both_missing_gives_none_with_a_note():
    c = earnings_context(None, None, ASOF)
    assert c["last"] is None and c["next"] is None and c["label"] == "none"
    assert c["days_since_last"] is None and c["days_until_next"] is None and c["note"]


def test_iso_strings_are_accepted_and_output_is_iso():
    c = earnings_context("2026-11-02", "2026-11-12", ASOF)
    assert c["last"] == "2026-11-02" and c["next"] == "2026-11-12"


def test_unparseable_date_is_treated_as_missing_not_an_error():
    c = earnings_context("not a date", None, ASOF)
    assert c["last"] is None and "not a date" in c["note"]


def test_last_report_in_the_future_is_not_trusted():
    c = earnings_context(date(2026, 11, 10), None, ASOF)
    assert c["last"] is None and c["label"] == "none" and "future" in c["note"].lower()


def test_last_report_older_than_140_days_is_stale():
    ok = earnings_context(date(2026, 6, 17), None, ASOF)         # exactly 140 days before
    old = earnings_context(date(2026, 6, 16), None, ASOF)        # 141
    assert ok["last"] == "2026-06-17"
    assert old["last"] is None and "140" in old["note"]


def test_next_report_in_the_past_is_stale():
    c = earnings_context(None, date(2026, 11, 3), ASOF)
    assert c["next"] is None and c["label"] == "none" and "past" in c["note"].lower()


def test_next_report_absurdly_far_away_is_dropped():
    c = earnings_context(None, date(2028, 1, 1), ASOF)
    assert c["next"] is None and c["note"]


# ---- resolve_dates (cached rows -> last / next) ---------------------------------------------------------------
def test_resolve_picks_latest_reported_and_earliest_scheduled():
    r = resolve_dates(GOOD, ASOF)
    assert (r["last"], r["next"]) == ("2026-11-02", "2027-01-28")
    assert r["estimated"] is False


def test_resolve_ignores_a_reported_row_dated_after_the_data_date():
    r = resolve_dates({"rows": [row("2026-11-10", True), row("2026-07-30", True)], "cal": []}, ASOF)
    assert r["last"] == "2026-07-30" and "after the data date" in r["why"]


def test_resolve_ignores_a_stale_calendar_date_and_says_why():
    r = resolve_dates({"rows": [], "cal": ["2026-10-14"]}, ASOF)       # ASML-style: calendar still shows a past date
    assert r["next"] is None and "past" in r["why"]


def test_resolve_uses_calendar_when_rows_have_no_future_row_and_marks_a_range_estimated():
    r = resolve_dates({"rows": [row("2026-07-30", True)], "cal": ["2026-11-10", "2026-11-14"]}, ASOF)
    assert r["next"] == "2026-11-10" and r["estimated"] is True


def test_resolve_scheduled_row_in_the_past_without_eps_is_not_a_report():
    r = resolve_dates({"rows": [row("2026-10-20", False), row("2026-07-30", True)], "cal": []}, ASOF)
    assert r["last"] == "2026-07-30" and r["next"] is None


def test_resolve_empty_data():
    r = resolve_dates({"rows": [], "cal": []}, ASOF)
    assert r["last"] is None and r["next"] is None


# ---- cache / loader -------------------------------------------------------------------------------------------
def fetcher(data, calls):
    def f(t):
        calls.append(t)
        v = data[t]
        if isinstance(v, Exception):
            raise v
        return v
    return f


def run(tickers, path, fetch, now=1_000_000.0, **kw):
    return load_earnings(tickers, path, ASOF, fetch=fetch, now=now, sleep=NO_SLEEP, workers=2, **kw)


def test_first_run_fetches_writes_cache_with_fetch_time_and_returns_context(tmp_path):
    p, calls = tmp_path / "earnings.json", []
    out = run(["AAA"], p, fetcher({"AAA": GOOD}, calls))
    assert calls == ["AAA"]
    assert out["AAA"]["last"] == "2026-11-02" and out["AAA"]["label"] == "reported_recently"
    assert out["AAA"]["stale"] is False and out["AAA"]["error"] is None
    cache = json.loads(p.read_text(encoding="utf-8"))
    assert cache["AAA"]["ts"] == 1_000_000.0 and cache["AAA"]["fetched_at"]
    assert not list(tmp_path.glob("*.tmp"))


def test_fresh_cache_is_not_refetched(tmp_path):
    p, calls = tmp_path / "e.json", []
    run(["AAA"], p, fetcher({"AAA": GOOD}, calls))
    run(["AAA"], p, fetcher({"AAA": GOOD}, calls), now=1_000_000.0 + 6.9 * 86400)
    assert calls == ["AAA"]


def test_expired_cache_is_refetched(tmp_path):
    p, calls = tmp_path / "e.json", []
    run(["AAA"], p, fetcher({"AAA": GOOD}, calls))
    new = {"rows": [row("2027-02-01", False), row("2026-11-03", True)], "cal": []}
    out = run(["AAA"], p, fetcher({"AAA": new}, calls), now=1_000_000.0 + 7.1 * 86400)
    assert calls == ["AAA", "AAA"] and out["AAA"]["last"] == "2026-11-03"


def test_failed_refetch_keeps_old_value_and_marks_it_stale(tmp_path):
    p, calls = tmp_path / "e.json", []
    run(["AAA"], p, fetcher({"AAA": GOOD}, calls))
    out = run(["AAA"], p, fetcher({"AAA": RuntimeError("boom")}, calls), now=1_000_000.0 + 8 * 86400)
    assert out["AAA"]["last"] == "2026-11-02" and out["AAA"]["stale"] is True
    assert "boom" in out["AAA"]["error"]
    kept = json.loads(p.read_text(encoding="utf-8"))["AAA"]
    assert kept["ts"] == 1_000_000.0 and kept["rows"]            # old fetch time and data survive; next run retries


def test_failing_ticker_never_raises_and_others_are_fine(tmp_path):
    p, calls = tmp_path / "e.json", []
    out = run(["BAD", "AAA", "EMPTY"], p, fetcher({"BAD": ValueError("404 not found"), "AAA": GOOD, "EMPTY": {"rows": [], "cal": []}}, calls))
    assert out["AAA"]["label"] == "reported_recently"
    assert out["BAD"]["label"] == "none" and "404" in out["BAD"]["error"] and out["BAD"]["last"] is None
    assert out["EMPTY"]["error"] and "no earnings" in out["EMPTY"]["error"].lower()
    assert set(out) == {"BAD", "AAA", "EMPTY"}


def test_retries_with_growing_backoff_then_succeeds(tmp_path):
    state, sleeps = {"n": 0}, []

    def flaky(t):
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("temporary")
        return GOOD

    out = load_earnings(["AAA"], tmp_path / "e.json", ASOF, fetch=flaky, now=1.0, sleep=sleeps.append, retries=3, workers=1)
    assert state["n"] == 3 and out["AAA"]["error"] is None
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0]


def test_rate_limit_error_backs_off_longer(tmp_path):
    sleeps_plain, sleeps_rl = [], []
    load_earnings(["A"], tmp_path / "a.json", ASOF, fetch=lambda t: (_ for _ in ()).throw(RuntimeError("x")), now=1.0, sleep=sleeps_plain.append, retries=2, workers=1)
    load_earnings(["A"], tmp_path / "b.json", ASOF, fetch=lambda t: (_ for _ in ()).throw(RuntimeError("429 Too Many Requests")), now=1.0, sleep=sleeps_rl.append, retries=2, workers=1)
    assert sleeps_rl[0] > sleeps_plain[0]


def test_corrupt_cache_file_is_ignored(tmp_path):
    p, calls = tmp_path / "e.json", []
    p.write_text("{not json", encoding="utf-8")
    assert run(["AAA"], p, fetcher({"AAA": GOOD}, calls))["AAA"]["last"] == "2026-11-02"


def test_cache_is_reclassified_against_the_new_data_date(tmp_path):
    p, calls = tmp_path / "e.json", []
    run(["AAA"], p, fetcher({"AAA": GOOD}, calls))
    later = load_earnings(["AAA"], p, date(2026, 11, 12), fetch=fetcher({}, calls), now=1_000_000.0 + 86400, sleep=NO_SLEEP)
    assert later["AAA"]["label"] == "none" and later["AAA"]["days_since_last"] == 8 and calls == ["AAA"]


def test_raw_pull_is_kept_and_never_overwritten(tmp_path):
    p, calls, raw = tmp_path / "e.json", [], tmp_path / "raw"
    run(["AAA"], p, fetcher({"AAA": GOOD}, calls), raw_dir=raw)
    first = sorted(raw.glob("*.json"))
    assert len(first) == 1
    before = first[0].read_bytes()
    run(["AAA"], p, fetcher({"AAA": GOOD}, calls), now=1_000_000.0 + 8 * 86400, raw_dir=raw)
    assert first[0].read_bytes() == before and len(list(raw.glob("*.json"))) == 2


def test_estimated_flag_is_carried_to_the_output(tmp_path):
    data = {"rows": [row("2026-07-30", True)], "cal": ["2026-11-10", "2026-11-14"]}
    out = run(["AAA"], tmp_path / "e.json", fetcher({"AAA": data}, []))
    assert out["AAA"]["next"] == "2026-11-10" and out["AAA"]["estimated"] is True and out["AAA"]["label"] == "reports_soon"


# ---- regressions from the independent review (2026-11-04) -----------------------------------------------------
def test_a_report_scheduled_after_the_fetch_is_fetched_again_not_hidden_by_a_fresh_cache(tmp_path):
    p = tmp_path / "e.json"
    day = 86400.0
    t0 = 1_000_000.0                                     # 1970-01-12: the dates below are chosen relative to it
    from datetime import datetime
    fetched = datetime.fromtimestamp(t0).date()
    sched = fetched                                       # scheduled on the day we fetched, no EPS yet
    calls: list[str] = []
    first = {"A": {"rows": [row(sched.isoformat(), False), row("1969-10-01", True)], "cal": []}}
    load_earnings(["A"], p, fetched, fetch=fetcher(first, calls), now=t0, sleep=NO_SLEEP, workers=1)
    assert calls == ["A"]
    later = {"A": {"rows": [row(sched.isoformat(), True), row("1969-10-01", True)], "cal": []}}
    out = load_earnings(["A"], p, date(fetched.year, fetched.month, fetched.day + 2), fetch=fetcher(later, calls),
                        now=t0 + 2 * day, sleep=NO_SLEEP, workers=1)
    assert calls == ["A", "A"]                            # fetched again although the cache was only 2 days old
    assert out["A"]["last"] == sched.isoformat()


def test_a_passed_scheduled_date_without_eps_is_noted_even_when_an_older_report_exists():
    r = resolve_dates({"rows": [row("2026-11-02", False), row("2026-07-30", True)], "cal": []}, date(2026, 11, 5))
    assert r["last"] == "2026-07-30" and "scheduled date passed" in r["why"]


@pytest.mark.parametrize("bad", [{"rows": ["x"]}, {"ts": "x", "rows": [], "cal": []}, {"ts": 1.0, "rows": [{"d": 5}], "cal": [3]}, [], "junk"])
def test_malformed_cache_entries_never_raise(tmp_path, bad):
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"A": bad}))
    out = load_earnings(["A"], p, ASOF, fetch=fetcher({"A": {"rows": [], "cal": []}}, []), now=1_000_000.0, sleep=NO_SLEEP, workers=1)
    assert out["A"]["label"] == "none"


def test_a_calendar_date_equal_to_the_last_report_is_not_the_next_report():
    # Yahoo's calendar can still list the report that has just happened (seen for AMD, 2026-11-03).
    r = resolve_dates({"rows": [row("2026-11-03", True), row("2026-08-04", True)], "cal": ["2026-11-03"]}, date(2026, 11, 3))
    assert r["last"] == "2026-11-03" and r["next"] is None
    r2 = resolve_dates({"rows": [row("2026-11-03", True), row("2027-02-03", False)], "cal": ["2026-11-03"]}, date(2026, 11, 3))
    assert r2["next"] == "2027-02-03"
