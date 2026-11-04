import math

import numpy as np
import pytest

from dipdash.metrics import MIN_BARS, clean, compute_metrics, rsi14
from synth import flat, geometric, volume

D = -0.01


def test_returns_and_drawdowns_match_closed_form():
    m = compute_metrics(geometric(300, D), None)
    assert m["r1"] == pytest.approx((1 + D) - 1, abs=1e-4)
    assert m["r5"] == pytest.approx((1 + D) ** 5 - 1, abs=1e-4)
    assert m["r21"] == pytest.approx((1 + D) ** 21 - 1, abs=1e-4)
    assert m["dd20"] == pytest.approx((1 + D) ** 19 - 1, abs=1e-4)   # max of last 20 bars is 19 bars back
    assert m["dd52"] == pytest.approx((1 + D) ** 251 - 1, abs=1e-4)  # max of last 252 bars is 251 back


def test_vs200_is_price_over_200_day_mean():
    c = geometric(300, D)
    expected = c.iloc[-1] / np.mean(c.iloc[-200:].to_numpy()) - 1
    assert compute_metrics(c, None)["vs200"] == pytest.approx(expected, abs=1e-4)


def test_price_is_last_close_and_asof_is_its_date():
    c = geometric(100, 0.001)
    m = compute_metrics(c, None)
    assert m["price"] == round(c.iloc[-1], 2)
    assert m["asof"] == "2026-10-29"


def test_sparkline_is_last_90_closes():
    c = geometric(300, 0.001)
    m = compute_metrics(c, None)
    assert len(m["spark"]) == 90
    assert m["spark"][-1] == round(c.iloc[-1], 2)


@pytest.mark.parametrize("daily, falling", [(-0.002, True), (0.002, False)])
def test_200_day_average_slope(daily, falling):
    assert compute_metrics(geometric(300, daily), None)["s200_falling"] is falling


def test_slope_is_false_without_enough_history_for_the_comparison():
    assert compute_metrics(geometric(210, -0.002), None)["s200_falling"] is False


def test_too_little_history_returns_none():
    assert compute_metrics(geometric(MIN_BARS - 1, 0.001), None) is None
    assert compute_metrics(geometric(MIN_BARS, 0.001), None) is not None


def test_missing_values_in_close_are_ignored():
    c = geometric(100, 0.001)
    c.iloc[10] = np.nan
    assert compute_metrics(c, None) is not None


def test_volume_spike_is_last_volume_over_previous_20_day_mean():
    m = compute_metrics(geometric(100, 0.001), volume(100, base=100, last=300))
    assert m["volx"] == pytest.approx(3.0)


def test_volume_spike_missing_when_no_volume_or_zero_average():
    assert compute_metrics(geometric(100, 0.001), None)["volx"] is None
    assert compute_metrics(geometric(100, 0.001), volume(100, base=0, last=5))["volx"] is None


def test_flat_price_gives_none_for_rsi_and_zscore_not_an_error():
    m = compute_metrics(flat(100), None)
    assert m["rsi"] is None and m["z5"] is None
    assert m["r5"] == 0


def test_rsi_extremes():
    assert rsi14(geometric(60, 0.01)) == 100.0
    assert rsi14(geometric(60, -0.01)) == pytest.approx(0.0, abs=1e-9)


def test_rsi_of_alternating_moves_is_near_50():
    c = geometric(60, 0.0)
    c = c + np.where(np.arange(60) % 2 == 0, 1.0, -1.0)
    assert 40 < rsi14(c) < 60


def test_rsi_is_nan_for_flat_or_short_series():
    assert math.isnan(rsi14(flat(60)))
    assert math.isnan(rsi14(geometric(10, 0.01)))


@pytest.mark.parametrize("x", [None, float("nan"), float("inf"), -float("inf"), np.float64("nan")])
def test_clean_turns_missing_and_non_finite_into_none(x):
    assert clean(x) is None


def test_clean_rounds():
    assert clean(0.123456, 4) == 0.1235
    assert clean(np.float64(2.0), 2) == 2.0


# ---- chart history and index moves ------------------------------------------
from dipdash.metrics import history, index_move  # noqa: E402


def test_history_has_aligned_series_and_matches_the_screening_numbers():
    c = geometric(460, 0.001)
    h = history(c)
    assert len(h["d"]) == len(h["c"]) == len(h["s"]) == len(h["h"]) == 252
    assert h["d"][-1] == "2026-10-29" and h["c"][-1] == round(c.iloc[-1], 2)
    assert h["s"][-1] == pytest.approx(np.mean(c.iloc[-200:].to_numpy()), abs=0.01)
    assert h["h"][-1] == pytest.approx(c.iloc[-252:].max(), abs=0.01)     # same window as the dd52 metric
    assert all(v is not None for v in h["s"])                              # 460 bars: the average exists on every plotted day


def test_history_marks_days_without_an_average_as_none_and_handles_short_series():
    h = history(geometric(260, 0.001))
    assert h["s"][0] is None and h["s"][-1] is not None
    short = history(geometric(30, 0.001))
    assert len(short["c"]) == 30 and set(short["s"]) == {None} and set(short["h"]) == {None}   # high needs 60 bars


def test_index_move_matches_closed_form():
    m = index_move(geometric(10, -0.01, start=1000.0))
    assert m["r1"] == pytest.approx(-0.01, abs=1e-4) and m["r5"] == pytest.approx(0.99 ** 5 - 1, abs=1e-4)
    assert m["asof"] == "2026-10-29" and m["price"] == round(1000 * 0.99 ** 9, 1)


def test_index_move_needs_six_bars():
    assert index_move(geometric(5, 0.01)) is None and index_move(geometric(6, 0.01)) is not None
