from datetime import date

import pandas as pd
import pytest

from dipdash.crosscheck import compare_closes, pick_sample, run_crosscheck, to_issues
from dipdash.openbb_source import nordic_symbol, source_for, us_symbol
from synth import dates, geometric

TODAY = date(2026, 10, 30)


def test_identical_series_match():
    c = geometric(30, 0.01)
    r = compare_closes("A", "nasdaq", c, c.copy())
    assert (r.status, r.n_common, r.max_rel_diff, r.n_over_tol) == ("ok", 30, 0.0, 0)


def test_tiny_differences_pass_and_big_ones_are_counted():
    c = geometric(30, 0.01)
    o = c.copy()
    o.iloc[5] *= 1.004          # 0.4%: inside the 1% tolerance
    o.iloc[10] *= 1.02          # 2%: outside
    o.iloc[20] *= 0.97          # 3%: outside
    r = compare_closes("A", "nasdaq", c, o)
    assert r.status == "diff" and r.n_over_tol == 2
    assert r.max_rel_diff == pytest.approx(1 / 0.97 - 1, abs=1e-6)


def test_a_missing_day_on_one_side_is_reported_not_compared():
    c = geometric(30, 0.01)
    r = compare_closes("A", "cboe", c, c.iloc[:-1])
    assert (r.status, r.n_common, r.n_only_ref, r.n_only_other) == ("ok", 29, 1, 0)
    assert r.last_ref == "2026-10-29" and r.last_other == "2026-10-28"


def test_time_zones_and_times_of_day_do_not_break_alignment():
    c = geometric(30, 0.01)
    o = c.copy()
    o.index = o.index.tz_localize("America/New_York") + pd.Timedelta(hours=16)
    assert compare_closes("A", "nasdaq", c, o).n_common == 30


def test_no_common_dates():
    r = compare_closes("A", "x", geometric(10, 0.01, end="2026-01-30"), geometric(10, 0.01))
    assert r.status == "no_overlap" and r.n_common == 0


def test_sample_is_reproducible_capped_and_within_the_eligible_set():
    el = [f"T{i}" for i in range(20)]
    a, b = pick_sample(el, 5, seed=20261030), pick_sample(el, 5, seed=20261030)
    assert a == b and len(set(a)) == 5 and set(a) <= set(el)
    assert pick_sample(el, 5, seed=1) != a
    assert len(pick_sample(["A", "B"], 5, seed=1)) == 2 and pick_sample([], 5, seed=1) == []


NORDIC = {".HE", ".ST", ".CO", ".OL"}
MIXED = [f"T{i}" for i in range(20)] + ["NOKIA.HE", "ERIC-B.ST", "NOVO-B.CO", "EQNR.OL"]


def test_sample_has_a_nordic_name_for_many_seeds():
    from dipdash.exchanges import suffix_of
    for seed in range(100):
        assert any(suffix_of(t) in NORDIC for t in pick_sample(MIXED, 5, seed=seed)), seed


def test_sample_is_reproducible_with_nordic_names():
    assert pick_sample(MIXED, 5, seed=20261030) == pick_sample(MIXED, 5, seed=20261030)
    assert len(set(pick_sample(MIXED, 5, seed=7))) == 5


def test_sample_with_no_nordic_eligible_still_works():
    us = [f"T{i}" for i in range(20)]
    s = pick_sample(us, 5, seed=3)
    assert len(s) == 5 and set(s) <= set(us) and s == pick_sample(us, 5, seed=3)


def test_run_crosscheck_handles_ok_diff_and_unavailable():
    c = geometric(30, 0.01)
    bad = c * 1.05
    ref = lambda t, s, e: c
    other = {"OK": ("nasdaq", lambda s, e: c), "BAD": ("nasdaq", lambda s, e: bad),
             "EMPTY": ("nasdaq", lambda s, e: None)}
    res = run_crosscheck(["OK", "BAD", "EMPTY", "NONE"], fetch_ref=ref, fetch_other=lambda t: other.get(t), today=TODAY)
    assert [(r.ticker, r.status) for r in res] == [("OK", "ok"), ("BAD", "diff"), ("EMPTY", "unavailable"), ("NONE", "unavailable")]
    sev = {i.ticker: (i.check, i.severity) for i in to_issues(res)}
    assert sev == {"OK": ("crosscheck_ok", "info"), "BAD": ("crosscheck_diff", "warn"),
                   "EMPTY": ("crosscheck_unavailable", "info"), "NONE": ("crosscheck_unavailable", "info")}


def test_the_date_window_is_passed_to_both_sources():
    seen = []
    c = geometric(30, 0.01)
    run_crosscheck(["A"], fetch_ref=lambda t, s, e: seen.append((s, e)) or c,
                   fetch_other=lambda t: ("n", lambda s, e: seen.append((s, e)) or c), today=TODAY, days=60)
    assert seen == [("2026-08-31", "2026-10-30")] * 2


@pytest.mark.parametrize("ticker, src", [("AAPL", "nasdaq"), ("BRK-B", "nasdaq"), ("NOKIA.HE", "nasdaq_nordic"),
                                         ("ERIC-B.ST", "nasdaq_nordic"), ("NOVO-B.CO", "nasdaq_nordic"),
                                         ("ASML.AS", None), ("SAP.DE", None), ("NESN.SW", None), ("EQNR.OL", None)])
def test_which_provider_serves_which_ticker(ticker, src):
    assert source_for(ticker) == src


def test_symbol_mapping():
    assert nordic_symbol("ERIC-B.ST") == "ERIC B" and nordic_symbol("NOKIA.HE") == "NOKIA" and nordic_symbol("MAERSK-B.CO") == "MAERSK B"
    assert us_symbol("BRK-B") == "BRK.B"
