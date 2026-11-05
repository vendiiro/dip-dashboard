import csv
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from dipdash.config import Settings, Stock
from dipdash.validate import (check_duplicate_listings, expected_currency, validate_currency, validate_prices,
                              validate_run, write_quality_log)
from synth import dates, geometric, volume

TODAY = date(2026, 10, 30)


def checks(issues):
    return {i.check for i in issues}


def test_clean_series_has_no_issues():
    assert validate_prices("X", geometric(260, 0.0005), TODAY, 4) == []


def test_empty_or_all_nan_is_an_error():
    assert checks(validate_prices("X", pd.Series(dtype=float), TODAY, 4)) == {"no_data"}
    assert checks(validate_prices("X", pd.Series([np.nan] * 5, index=dates(5)), TODAY, 4)) == {"no_data"}


def test_zero_and_negative_prices_are_errors():
    c = geometric(100, 0.001)
    c.iloc[40] = 0.0
    c.iloc[41] = -1.0
    i = [x for x in validate_prices("X", c, TODAY, 4) if x.check == "non_positive_price"]
    assert len(i) == 1 and i[0].severity == "error" and "2 close" in i[0].detail


def test_a_split_like_jump_is_flagged_with_its_date():
    c = geometric(100, 0.0)
    c.iloc[60:] = c.iloc[60:] * 0.5            # a missed 2:1 split: -50% in one day
    i = [x for x in validate_prices("X", c, TODAY, 4) if x.check == "large_move"]
    assert len(i) == 1 and "-50.0%" in i[0].detail and str(c.index[60].date()) in i[0].detail


def test_a_big_but_plausible_move_is_not_flagged():
    c = geometric(100, 0.0)
    c.iloc[60:] = c.iloc[60:] * 0.8
    assert "large_move" not in checks(validate_prices("X", c, TODAY, 4))


def test_a_hole_in_the_data_is_flagged_but_a_holiday_gap_is_not():
    c = geometric(100, 0.001)
    holiday = c.drop(c.index[50:52])           # two missing bars: 3 weekdays advanced
    hole = c.drop(c.index[50:58])              # eight missing bars
    assert "gap" not in checks(validate_prices("X", holiday, TODAY, 4))
    g = [x for x in validate_prices("X", hole, TODAY, 4) if x.check == "gap"]
    assert len(g) == 1 and "9 weekdays" in g[0].detail


def test_many_missing_closes_are_flagged():
    c = geometric(260, 0.001)
    c.iloc[-60:-20] = np.nan
    assert "missing_values" in checks(validate_prices("X", c, TODAY, 4))


def test_trailing_empty_closes_are_recorded_not_silent():
    c = geometric(260, 0.001)                       # last bar 2026-10-29
    c.iloc[-2:] = np.nan
    got = [i for i in validate_prices("X", c, TODAY, 4) if i.check == "empty_last_bar"]
    assert len(got) == 1 and got[0].severity == "info"
    assert "last 2 close(s) empty (from 2026-10-28)" in got[0].detail and "bar from 2026-10-27" in got[0].detail
    c.iloc[-60:-20] = np.nan                        # a hole in the middle is not a trailing empty bar
    c.iloc[-2:] = geometric(2, 0.0, start=50.0, end="2026-10-29").to_numpy()
    assert "empty_last_bar" not in checks(validate_prices("X", c, TODAY, 4))


def test_duplicate_dates_are_an_error_and_unsorted_is_a_warning():
    c = geometric(100, 0.001)
    dup = pd.concat([c, c.iloc[-1:]])
    assert {(i.check, i.severity) for i in validate_prices("X", dup, TODAY, 4)} >= {("duplicate_dates", "error")}
    assert ("unsorted", "warn") in {(i.check, i.severity) for i in validate_prices("X", c.iloc[::-1], TODAY, 4)}


def test_stale_means_older_than_the_limit():
    fresh = geometric(100, 0.001, end="2026-10-26")   # 4 weekdays before Friday 30th
    old = geometric(100, 0.001, end="2026-10-23")
    assert "stale" not in checks(validate_prices("X", fresh, TODAY, 4))
    s = [i for i in validate_prices("X", old, TODAY, 4) if i.check == "stale"]
    assert len(s) == 1 and s[0].severity == "error"


@pytest.mark.parametrize("ticker, ccy", [("AAPL", "USD"), ("BRK-B", "USD"), ("NOKIA.HE", "EUR"), ("SAP.DE", "EUR"),
                                         ("NESN.SW", "CHF"), ("ERIC-B.ST", "SEK"), ("NOVO-B.CO", "DKK"), ("EQNR.OL", "NOK"),
                                         ("BARC.L", None)])
def test_expected_currency(ticker, ccy):
    assert expected_currency(ticker) == ccy


def test_currency_checks():
    assert validate_currency("NOKIA.HE", "EUR") == []
    assert validate_currency("NOKIA.HE", "USD")[0].check == "currency_mismatch"
    assert validate_currency("NOKIA.HE", None)[0].check == "currency_missing"
    assert validate_currency("BARC.L", "GBp")[0].check == "currency_unknown"


def test_duplicate_listings_are_found_by_company_name():
    u = [Stock("SAP", "SAP SE", "US"), Stock("SAP.DE", "SAP  SE", "Europe"), Stock("AAPL", "Apple", "US")]
    d = check_duplicate_listings(u)
    assert [(i.ticker, i.check) for i in d] == [("SAP.DE", "duplicate_listing")] and "SAP" in d[0].detail


def test_validate_run_covers_missing_tickers_and_missing_fundamentals():
    u = [Stock("A", "A", "US"), Stock("B", "B", "US"), Stock("C", "C", "US")]
    prices = {"A": (geometric(100, 0.001), volume(100)), "C": (geometric(100, 0.001), None)}
    funds = {"A": {"currency": "USD"}}
    got = {(i.ticker, i.check) for i in validate_run(u, prices, funds, Settings(), TODAY)}
    assert got == {("B", "no_data"), ("C", "no_fundamentals")}


def test_quality_log_is_sorted_by_severity_and_has_a_header(tmp_path):
    from dipdash.validate import Issue
    p = write_quality_log([Issue("B", "x", "info", "i"), Issue("A", "y", "error", "e"), Issue("A", "z", "warn", "w")],
                          tmp_path / "sub" / "dq.csv", datetime(2026, 10, 30, 0, 15))
    rows = list(csv.reader(p.open(encoding="utf-8")))
    assert rows[0] == ["run_at", "ticker", "check", "severity", "detail"]
    assert [r[3] for r in rows[1:]] == ["error", "warn", "info"] and rows[1][0] == "2026-10-30 00:15"


def test_quality_log_with_no_issues_is_just_a_header(tmp_path):
    p = write_quality_log([], tmp_path / "dq.csv")
    assert len(p.read_text().splitlines()) == 1


# ---- spike and revert (a bad price that is too small for the 40% test)
def test_a_lone_bad_price_that_reverts_is_flagged_with_its_date():
    c = geometric(100, 0.0)
    c.iloc[50] = 130.0                                         # +30%, back to 100 the next day
    got = [i for i in validate_prices("X", c, TODAY, 4) if i.check == "spike_revert"]
    assert len(got) == 1 and str(c.index[50].date()) in got[0].detail and got[0].severity == "warn"
    assert "large_move" not in checks(validate_prices("X", c, TODAY, 4))      # the 40% test does not see it
    d = geometric(100, 0.0)
    d.iloc[50] = 70.0                                          # a lone low print
    assert any(i.check == "spike_revert" for i in validate_prices("X", d, TODAY, 4))


def test_real_moves_that_persist_or_only_half_revert_are_not_spikes():
    step = geometric(100, 0.0)
    step.iloc[50:] = 130.0                                     # a +30% day that stays
    pop = geometric(100, 0.0)
    pop.iloc[50] = 125.0
    pop.iloc[51:] = 112.0                                      # +25% then gives back half: neighbours are 12% apart
    for c in (step, pop):
        assert "spike_revert" not in checks(validate_prices("X", c, TODAY, 4))


def bar_between(prev, mid, nxt):
    c = geometric(100, 0.0)
    c.iloc[49], c.iloc[50], c.iloc[51:] = prev, mid, nxt
    return c


def test_the_spike_test_needs_both_neighbours_to_agree_with_each_other_and_to_be_far_from_the_bar():
    # +25% bar, next day only 8% above the day before: the neighbours disagree, so this is news that partly reverted, not a bad price
    assert "spike_revert" not in checks(validate_prices("X", bar_between(100.0, 125.0, 108.0), TODAY, 4))
    # +15.5% over the previous bar but only +12% over the next, neighbours 3% apart: not far enough from the next bar to call it a bad price
    assert "spike_revert" not in checks(validate_prices("X", bar_between(100.0, 115.5, 103.0), TODAY, 4))
    # the same shape made unambiguous: both neighbours equal, bar 20% above both
    assert "spike_revert" in checks(validate_prices("X", bar_between(100.0, 120.0, 100.0), TODAY, 4))


# ---- the spike test uses volume when it has it: a crash-day reversal is not a bad tick
def test_spike_needs_thin_volume_when_volume_is_known():
    from synth import volume
    c = bar_between(100.0, 120.0, 100.0)
    thin = volume(100, 1000.0)
    thin.iloc[50] = 300.0                                       # 0.3 of the usual volume: a bad print
    heavy = volume(100, 1000.0)
    heavy.iloc[50] = 4000.0                                     # 4x the usual volume: a real, violent day
    got = [i for i in validate_prices("X", c, TODAY, 4, thin) if i.check == "spike_revert"]
    assert len(got) == 1 and "thin volume" in got[0].detail
    assert "spike_revert" not in checks(validate_prices("X", c, TODAY, 4, heavy))
    no_vol = [i for i in validate_prices("X", c, TODAY, 4) if i.check == "spike_revert"]
    assert len(no_vol) == 1 and "possible" in no_vol[0].detail                    # without volume it is only a possibility
    assert "spike_revert" not in checks(validate_prices("X", c, TODAY, 4, volume(100, float("nan"))))       # unusable volume: stay quiet, not guess


def test_fetch_issues_have_severity_and_plain_detail():
    from dipdash.validate import fetch_issues
    reasons = {"AAA": "primary source had no data; used the OpenBB fallback", "CCC": "Yahoo returned no rows for this ticker"}
    status = {"AAA": {"stale": True, "age_days": 8.2, "error": "RuntimeError: 429"},
              "BBB": {"stale": False, "age_days": None, "error": "failed after 3 attempts: 404"},
              "DDD": {"stale": False, "age_days": 1.0, "error": None}}
    got = {(i.ticker, i.check): i for i in fetch_issues(reasons, {"AAA": object()}, status)}
    assert got[("AAA", "fetch_failed")].severity == "warn" and got[("CCC", "fetch_failed")].severity == "error"
    assert "8 days old" in got[("AAA", "fundamentals_stale")].detail and "429" in got[("AAA", "fundamentals_stale")].detail
    assert got[("BBB", "fundamentals_missing")].severity == "warn" and ("DDD", "fundamentals_stale") not in got
