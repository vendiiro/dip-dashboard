import gzip
from datetime import datetime

import pandas as pd
import pytest

from dipdash.cache import list_raw, load_raw_prices, save_raw_prices
from synth import geometric, volume

NOW = datetime(2026, 10, 30, 0, 15, 7)


def sample():
    return {"AAA": (geometric(30, 0.01), volume(30, 5.0, 9.0)), "BBB": (geometric(20, -0.01, start=50.0), None)}


def test_roundtrip_keeps_values_dates_and_missing_volume(tmp_path):
    src = sample()
    back = load_raw_prices(save_raw_prices(src, "yf", tmp_path, NOW))
    assert list(back) == ["AAA", "BBB"]
    for t in src:
        pd.testing.assert_series_equal(back[t][0], src[t][0], check_freq=False, check_names=False)
    pd.testing.assert_series_equal(back["AAA"][1], src["AAA"][1], check_freq=False, check_names=False)
    assert back["BBB"][1] is None


def test_file_name_is_the_pull_date(tmp_path):
    assert save_raw_prices(sample(), "yf", tmp_path, NOW).name == "2026-10-30.csv.gz"


def test_a_second_pull_on_the_same_day_never_overwrites_the_first(tmp_path):
    first = save_raw_prices(sample(), "yf", tmp_path, NOW)
    before = first.read_bytes()
    second = save_raw_prices({"ZZZ": (geometric(10, 0.01), None)}, "yf", tmp_path, datetime(2026, 10, 30, 9, 0, 0))
    assert second != first and second.name == "2026-10-30_090000.csv.gz"
    assert first.read_bytes() == before
    assert list_raw("yf", tmp_path) == sorted([first, second])


def test_writing_to_an_existing_path_fails_instead_of_overwriting(tmp_path):
    p = tmp_path / "x.csv.gz"
    with gzip.open(p, "xt") as fh:
        fh.write("a")
    with pytest.raises(FileExistsError):
        gzip.open(p, "xt")


def test_sources_are_kept_apart_and_empty_listing_is_fine(tmp_path):
    save_raw_prices(sample(), "yf", tmp_path, NOW)
    assert list_raw("openbb", tmp_path) == []
