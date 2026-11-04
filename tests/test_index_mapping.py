"""Market-context index mapping: ticker suffix -> country index -> region index -> Europe-wide fallback -> '-' with a reason."""
import json
from datetime import date

import pandas as pd
import pytest

from dipdash.config import DEFAULT_COUNTRY_INDICES, IndexSpec, Settings, Stock, load_settings
from dipdash.dashboard import build_payload, index_r5_on, pick_index
from dipdash.data import fetch_indices
from synth import dates, geometric

TODAY = date(2026, 10, 30)


def ix(sym, region, suffixes=(), asof="2026-10-29", r5=-0.02, closes=None):
    return {"symbol": sym, "name": sym, "region": region, "suffixes": list(suffixes), "price": 100.0, "r1": 0.0, "r5": r5,
            "asof": asof, **({"closes": closes} if closes else {})}


IDX = [ix("^GSPC", "US"), ix("^STOXX", "Europe"), ix("^OMXH25", "Nordic", [".HE"]),
       ix("^OMXSPI", "Nordic", [".ST"]), ix("^AEX", "Europe", [".AS"])]


def sym(ticker, region, indices=IDX):
    got = pick_index(ticker, region, indices)
    return got["symbol"] if got else None


def test_suffix_beats_region_and_is_case_insensitive():
    assert sym("ASML.AS", "Europe") == "^AEX"
    assert sym("ERIC-B.ST", "Nordic") == "^OMXSPI"
    assert sym("NESTE.HE", "Nordic") == "^OMXH25"
    assert sym("neste.he", "Nordic") == "^OMXH25"


def test_region_index_then_europe_wide_fallback_then_none():
    assert sym("AAPL", "US") == "^GSPC" and sym("BRK-B", "US") == "^GSPC"
    assert sym("SAP.DE", "Europe") == "^STOXX"          # region index (no DAX in this list)
    assert sym("EQNR.OL", "Nordic") == "^STOXX"         # no Oslo index, Nordic has no region-level index: Europe-wide fallback
    assert pick_index("EQNR.OL", "Nordic", [IDX[0]]) is None      # no Europe index either: nothing, never a US index
    assert pick_index("AAPL", "US", [IDX[1]]) is None


def test_old_style_region_only_config_behaves_as_before():
    old = [ix("^GSPC", "US"), ix("^STOXX", "Europe"), ix("^OMXH25", "Nordic")]       # no suffixes anywhere
    assert sym("ERIC-B.ST", "Nordic", old) == "^OMXH25" and sym("ASML.AS", "Europe", old) == "^STOXX"


def test_r5_is_taken_on_the_stocks_own_date():
    c = {d: 100.0 + i for i, d in enumerate(["2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27",
                                              "2026-10-28", "2026-10-29"])}
    i = ix("^X", "Europe", closes=c, asof="2026-10-29")
    assert index_r5_on(i, "2026-10-29") == pytest.approx(106 / 101 - 1, abs=1e-4)
    assert index_r5_on(i, "2026-10-28") == pytest.approx(105 / 100 - 1, abs=1e-4)
    assert index_r5_on(i, "2026-10-27") is None            # fewer than 5 earlier bars
    assert index_r5_on(i, "2026-11-02") is None            # the index has no bar that day
    assert index_r5_on(ix("^Y", "US", r5=-0.02), "2026-10-29") == -0.02       # old payload without closes: exact date match only
    assert index_r5_on(ix("^Y", "US", r5=-0.02), "2026-10-28") is None


def _index_closes(last="2026-10-29", n=12, daily=0.01):
    s = geometric(n, daily, end=last)
    return {str(d.date()): float(v) for d, v in s.items()}


def test_stock_one_day_behind_the_index_is_compared_on_its_own_date():
    """The real bug: Yahoo's European bar for the latest day was missing, the index had it, and the strict date check blanked the row."""
    closes = _index_closes(last="2026-10-30")                       # index is a day ahead of the stock
    idx = ix("^AEX", "Europe", [".AS"], asof="2026-10-30", r5=0.0510, closes=closes)
    stock = Stock("ASML.AS", "ASML", "Europe")
    prices = {"ASML.AS": (geometric(260, 0.0), None)}                  # flat, last bar 2026-10-29
    row = build_payload([stock], prices, {}, Settings(), today=TODAY, indices=[idx])["rows"][0]
    expected_r5 = geometric(12, 0.01, end="2026-10-29").iloc[-1] / geometric(12, 0.01, end="2026-10-29").iloc[-6] - 1
    assert row["idx"] == "^AEX" and row["idx_sym"] == "^AEX" and row["idx_why"] is None
    assert row["x5"] == pytest.approx(0.0 - expected_r5, abs=1e-4)
    assert row["asof"] == "2026-10-29"


def test_missing_index_gives_a_dash_and_a_written_reason_never_a_number():
    stock = Stock("EQNR.OL", "Equinor", "Nordic")
    prices = {"EQNR.OL": (geometric(260, 0.001), None)}
    row = build_payload([stock], prices, {}, Settings(), today=TODAY, indices=[])["rows"][0]
    assert row["idx"] is None and row["x5"] is None and ".ol" in row["idx_why"]
    json.dumps(row, allow_nan=False)
    row = build_payload([stock], prices, {}, Settings(), today=TODAY, indices=None)["rows"][0]       # no indices at all must not crash
    assert row["x5"] is None


def test_index_without_the_stocks_date_explains_itself():
    idx = ix("^STOXX", "Europe", asof="2026-10-27", closes=_index_closes(last="2026-10-27"))
    row = build_payload([Stock("SAP.DE", "SAP", "Europe")], {"SAP.DE": (geometric(260, 0.001), None)}, {}, Settings(),
                        today=TODAY, indices=[idx])["rows"][0]
    assert row["x5"] is None and row["idx"] == "^STOXX" and "2026-10-29" in row["idx_why"]


def test_payload_indices_keep_their_old_fields_and_add_suffixes_and_closes():
    fake = lambda s: geometric(20, 0.01, start=100.0)
    got = fetch_indices(DEFAULT_COUNTRY_INDICES[:1], fake)[0]
    assert {"symbol", "name", "region", "price", "r1", "r5", "asof"} <= set(got)
    assert list(got["suffixes"]) == [".ST"] and len(got["closes"]) == 12 and got["asof"] in got["closes"]
    json.dumps(got, allow_nan=False)


def test_settings_file_maps_every_universe_suffix_and_matches_code_defaults():
    from dipdash.config import load_universe
    s = load_settings()
    assert s.country_indices == DEFAULT_COUNTRY_INDICES and s.context.fallback_region == "Europe"
    assert [i.symbol for i in s.all_indices][:3] == ["^GSPC", "^STOXX", "^OMXH25"] and len(s.all_indices) == 10
    payload_ix = [{**i.__dict__, "suffixes": list(i.suffixes)} for i in s.all_indices]
    for st in load_universe():
        assert pick_index(st.ticker, st.region, payload_ix, s.context.fallback_region), st.ticker
    assert sym("NOVO-B.CO", "Nordic", payload_ix) == "^OMXC25" and sym("EQNR.OL", "Nordic", payload_ix) == "OSEBX.OL"


def test_country_indices_section_parses_and_a_typo_is_an_error(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text('[context]\nfallback_region = "Nordic"\n[[country_indices]]\nsymbol = "^Z"\nname = "Z"\nregion = "Europe"\nsuffixes = [".MI"]\n')
    s = load_settings(p)
    assert s.country_indices == (IndexSpec("^Z", "Z", "Europe", (".MI",)),) and s.context.fallback_region == "Nordic"
    p.write_text('[[country_indices]]\nsymbol = "^Z"\nname = "Z"\nregion = "Europe"\nsufixes = [".MI"]\n')
    with pytest.raises(ValueError, match="sufixes"):
        load_settings(p)
