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


# ---- atomic JSON writes (fundamentals cache) -------------------------------------------------------------------
def test_atomic_write_replaces_whole_file_and_leaves_no_temp(tmp_path):
    import json
    from dipdash.cache import atomic_write_json
    p = tmp_path / "sub" / "f.json"
    atomic_write_json(p, {"a": 1})
    atomic_write_json(p, {"a": 2})
    assert json.loads(p.read_text()) == {"a": 2} and [x.name for x in p.parent.iterdir()] == ["f.json"]


def test_crash_while_writing_keeps_the_old_file_intact(tmp_path, monkeypatch):
    import json
    import os
    from dipdash import cache
    p = tmp_path / "f.json"
    cache.atomic_write_json(p, {"old": True})

    def crash(fd):                                    # the process dies after the temp file is written but before the swap
        raise OSError("disk unplugged")

    monkeypatch.setattr(os, "fsync", crash)
    with pytest.raises(OSError):
        cache.atomic_write_json(p, {"new": "x" * 10_000})
    assert json.loads(p.read_text()) == {"old": True}             # never half a file
    assert [x.name for x in tmp_path.iterdir()] == ["f.json"]     # and the temp file is cleaned up


def test_crash_during_json_dump_keeps_the_old_file_intact(tmp_path, monkeypatch):
    import json
    from dipdash import cache
    p = tmp_path / "f.json"
    cache.atomic_write_json(p, {"old": True})

    def half_dump(obj, fh):
        fh.write('{"new": [1, 2,')                    # half a document reaches the temp file, then the "crash"
        raise KeyboardInterrupt

    monkeypatch.setattr(cache.json, "dump", half_dump)
    with pytest.raises(KeyboardInterrupt):
        cache.atomic_write_json(p, {"new": 1})
    assert json.loads(p.read_text()) == {"old": True} and len(list(tmp_path.iterdir())) == 1


def test_fundamentals_cache_survives_a_crash_mid_write_and_an_orphan_temp_file(tmp_path, monkeypatch):
    import os
    from dipdash import data
    from fakes import FakeYahoo
    y = FakeYahoo({"AAA": geometric(30, 0.01), "BBB": geometric(30, 0.01)})
    path = tmp_path / "fundamentals.json"
    data.fetch_fundamentals(["AAA"], path, fetch_info=y.info, sleep=lambda s: None, pace=0, now=1000.0)
    before = path.read_text()
    (tmp_path / "fundamentals.json.999.tmp").write_text('{"half')            # what a hard kill leaves behind
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("killed")))
    with pytest.raises(OSError):
        data.fetch_fundamentals(["AAA", "BBB"], path, fetch_info=y.info, sleep=lambda s: None, pace=0, now=2000.0)
    monkeypatch.undo()
    assert path.read_text() == before
    f = data.fetch_fundamentals(["AAA", "BBB"], path, fetch_info=y.info, sleep=lambda s: None, pace=0, now=3000.0)
    assert f["BBB"]["currency"] == "USD"                                       # the next run just works


def test_raw_fundamentals_pull_is_never_overwritten(tmp_path):
    from dipdash.data import save_raw_fundamentals
    a = save_raw_fundamentals({"AAA": {"ts": 1}}, tmp_path, NOW)
    b = save_raw_fundamentals({"AAA": {"ts": 2}}, tmp_path, NOW)               # same second
    assert a != b and a.read_text() != b.read_text()
