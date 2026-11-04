"""Exchange registry: derived views match the old hand-kept tables, and the registry agrees with config and universe."""
import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from dipdash.config import DEFAULT_COUNTRY_INDICES, DEFAULT_INDICES
from dipdash.earnings import EXCHANGE_TZ, exchange_tz
from dipdash.exchanges import EXCHANGES, exchange_for, suffix_of
from dipdash.openbb_source import NORDIC_SUFFIXES, source_for
from dipdash.validate import SUFFIX_CURRENCY, expected_currency

UNIVERSE = Path(__file__).resolve().parents[1] / "config" / "universe.csv"

# frozen copies of the tables as they were before the registry existed
OLD_CURRENCY = {".LS": "EUR", ".MI": "EUR", ".MC": "EUR", ".BR": "EUR", ".AS": "EUR", ".DE": "EUR", ".PA": "EUR", ".HE": "EUR",
                ".SW": "CHF", ".ST": "SEK", ".CO": "DKK", ".OL": "NOK"}
OLD_TZ = {".HE": "Europe/Helsinki", ".AS": "Europe/Amsterdam", ".OL": "Europe/Oslo", ".CO": "Europe/Copenhagen",
          ".ST": "Europe/Stockholm", ".SW": "Europe/Zurich", ".DE": "Europe/Berlin", ".PA": "Europe/Paris",
          ".MI": "Europe/Rome", ".MC": "Europe/Madrid", ".BR": "Europe/Brussels", ".L": "Europe/London"}
OLD_NORDIC = {".HE", ".ST", ".CO"}


def universe_suffixes() -> set[str]:
    with open(UNIVERSE, newline="", encoding="utf-8") as f:
        return {suffix_of(r["ticker"]) for r in csv.DictReader(f)}


def test_currency_view_unchanged():
    assert SUFFIX_CURRENCY == OLD_CURRENCY


def test_tz_view_only_adds_lisbon():
    assert EXCHANGE_TZ == {**OLD_TZ, ".LS": "Europe/Lisbon"}


def test_nordic_view_unchanged():
    assert set(NORDIC_SUFFIXES) == OLD_NORDIC


@pytest.mark.parametrize("ticker,provider", [("AAPL", "nasdaq"), ("BRK-B", "nasdaq"), ("NOKIA.HE", "nasdaq_nordic"),
                                             ("ERIC-B.ST", "nasdaq_nordic"), ("NOVO-B.CO", "nasdaq_nordic"),
                                             ("EQNR.OL", None), ("SAP.DE", None), ("X.ZZ", None)])
def test_source_for(ticker, provider):
    assert source_for(ticker) == provider


def test_universe_suffixes_fully_described():
    sufs = universe_suffixes()
    assert sufs
    for s in sufs:
        ex = EXCHANGES.get(s)
        assert ex is not None, f"suffix {s!r} in universe.csv is not in the registry"
        ZoneInfo(ex.tz)
        assert ex.currency, s
        assert ex.close is not None


def test_registry_index_matches_config():
    configured = {s: spec.symbol for spec in DEFAULT_COUNTRY_INDICES for s in spec.suffixes}
    configured.update({s: spec.symbol for spec in DEFAULT_INDICES for s in spec.suffixes})
    configured[""] = next(spec.symbol for spec in DEFAULT_INDICES if spec.region == "US")
    registry = {s: e.index for s, e in EXCHANGES.items() if e.index}
    assert registry == configured


def test_suffix_of():
    assert suffix_of("AAPL") == ""
    assert suffix_of("BRK-B") == ""
    assert suffix_of("NOKIA.HE") == ".HE"
    assert suffix_of("nokia.he") == ".HE"


def test_lisbon_time_zone_and_day_rollover():
    assert exchange_tz("GALP.LS") == "Europe/Lisbon"
    ny = datetime(2026, 10, 27, 20, 30, tzinfo=ZoneInfo("America/New_York"))
    assert ny.astimezone(ZoneInfo(exchange_tz("GALP.LS"))).date().isoformat() == "2026-10-28"


def test_unknown_suffix():
    assert exchange_for("X.ZZ") is None
    assert expected_currency("X.ZZ") is None
    assert exchange_tz("X.ZZ") == "America/New_York"


def test_us_and_london():
    assert expected_currency("AAPL") == "USD"
    assert exchange_tz("AAPL") == "America/New_York"
    assert expected_currency("SHEL.L") is None   # pounds vs pence not settled (open question Q2)
