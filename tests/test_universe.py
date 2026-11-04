"""Offline guards for config/universe.csv and offline tests (with fakes) for scripts/verify_universe.py."""
import csv
import importlib.util
import re
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verify_universe", ROOT / "scripts" / "verify_universe.py")
vu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vu)

SECTORS = {"Communication", "Consumer disc.", "Energy", "Financials", "Health care", "Industrials", "Materials",
           "Real Estate", "Staples", "Tech", "Utilities"}
FORMAT = re.compile(r"^[A-Z0-9]{1,6}(-[A-Z]{1,3})?(\.[A-Z]{2})?$")
# TODO(DATA-7): drop this once the exchange registry exposes suffix -> region.
REGION_BY_SUFFIX = {s: ("US" if s == "" else "Nordic" if s in vu.NORDIC_SUFFIXES else "Europe") for s in vu.SUFFIX_CURRENCY}
# Same company on two lines is not allowed; these groups name known share-class / ADR pairs.
SAME_COMPANY = [{"GOOG", "GOOGL"}, {"BRK-A", "BRK-B"}, {"FOX", "FOXA"}, {"NWS", "NWSA"}, {"UA", "UAA"},
                {"NOVO-B.CO", "NVO"}, {"ASML", "ASML.AS"}, {"SAP", "SAP.DE"}, {"SHEL", "SHEL.L"}, {"NVS", "NOVN.SW"},
                {"AZN", "AZN.L"}, {"SNY", "SAN.PA"}, {"TTE", "TTE.PA"}, {"UL", "ULVR.L"}, {"DEO", "DGE.L"}]
NEAR_MATCH_ALLOWED = {frozenset({"nestle", "neste"})}


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def problems(rows: list[dict]) -> list[str]:
    """All offline problems in a universe, as 'check: ticker ...' strings."""
    out = []
    for r in rows:
        t, name, region, sector = r["ticker"], r["name"], r["region"], r["sector"]
        if not FORMAT.match(t) or t != t.strip():
            out.append(f"format: {t!r}")
            continue
        suf = vu.suffix_of(t)
        if suf not in vu.SUFFIX_CURRENCY:
            out.append(f"suffix: {t}")
        elif REGION_BY_SUFFIX[suf] != region:
            out.append(f"region: {t} is {region}, suffix says {REGION_BY_SUFFIX[suf]}")
        if sector not in SECTORS:
            out.append(f"sector: {t} {sector!r}")
        if name != name.strip() or not name:
            out.append(f"name: {t} {name!r}")
    names: dict[str, str] = {}
    for r in rows:
        k = vu.normalize_name(r["name"])
        if k in names:
            out.append(f"duplicate_name: {r['ticker']} and {names[k]}")
        names[k] = r["ticker"]
    tickers = {r["ticker"] for r in rows}
    for g in SAME_COMPANY:
        if len(g & tickers) > 1:
            out.append(f"share_class: {sorted(g & tickers)}")
    roots: dict[tuple, str] = {}
    for r in rows:  # ERIC-A.ST and ERIC-B.ST: same root and exchange means two share classes
        key = (re.split(r"[-.]", r["ticker"])[0], vu.suffix_of(r["ticker"]))
        if key in roots:
            out.append(f"share_class: {roots[key]} and {r['ticker']}")
        roots[key] = r["ticker"]
    return out


def test_real_universe_passes_all_offline_checks():
    assert problems(read_rows(ROOT / "config" / "universe.csv")) == []


def test_near_matching_names_are_only_the_allow_listed_pairs():
    import difflib
    keys = sorted({vu.normalize_name(r["name"]) for r in read_rows(ROOT / "config" / "universe.csv")})
    near = {frozenset({a, b}) for i, a in enumerate(keys) for b in keys[i + 1:]
            if difflib.SequenceMatcher(None, a, b).ratio() >= 0.85}
    assert near <= NEAR_MATCH_ALLOWED, near - NEAR_MATCH_ALLOWED


def _rows(*items):
    return [dict(ticker=t, name=n, region=r, sector=s) for t, n, r, s in items]


GOOD = ("AAPL", "Apple", "US", "Tech")


@pytest.mark.parametrize("bad,check", [
    (("BRK.B", "Berkshire", "US", "Financials"), "format"),
    (("X.L", "Xco", "US", "Tech"), "format"),
    (("SAP.XX", "Sapx", "Europe", "Tech"), "suffix"),
    (("NOKIA.HE", "Nokia", "Europe", "Tech"), "region"),
    (("MSFT", "Microsoft", "US", "Tech "), "sector"),
    (("MSFT", "Microsoft", "US", "Technology"), "sector"),
    (("MSFT ", "Microsoft", "US", "Tech"), "format"),
])
def test_planted_bad_row_is_caught(bad, check, tmp_path):
    p = tmp_path / "u.csv"
    with p.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "name", "region", "sector"])
        w.writerows([GOOD, bad])
    found = problems(read_rows(p))
    assert found and all(f.startswith(check) for f in found), found


def test_two_alphabet_lines_are_caught():
    found = problems(_rows(("GOOG", "Alphabet Inc.", "US", "Communication"), ("GOOGL", "Alphabet", "US", "Communication")))
    assert any(f.startswith("duplicate_name") for f in found) and any(f.startswith("share_class") for f in found)


def test_two_classes_of_one_nordic_company_are_caught():
    found = problems(_rows(("ERIC-A.ST", "Ericsson A", "Nordic", "Tech"), ("ERIC-B.ST", "Ericsson B", "Nordic", "Tech")))
    assert any(f.startswith("share_class") for f in found)


def test_normalize_name_drops_legal_suffixes_and_punctuation():
    assert vu.normalize_name("Alphabet Inc.") == vu.normalize_name("ALPHABET") == "alphabet"
    assert vu.normalize_name("Nestle") != vu.normalize_name("Neste")


# ---- verify_universe: pure logic ----------------------------------------------------------------------------

TODAY = date(2026, 11, 4)  # a Wednesday
RATES = {"EUR": 1.1, "SEK": 0.1}
OK_INFO = {"longName": "Apple Inc.", "quoteType": "EQUITY", "exchange": "NMS", "currency": "USD", "marketCap": 3e12}
OK_BARS = {"first": date(2021, 11, 4), "last": date(2026, 11, 3), "count": 1250}


def classify(ticker="AAPL", name="Apple", info=OK_INFO, bars=OK_BARS, **kw):
    kw.setdefault("rates", RATES)
    return vu.classify_row(ticker, name, info, bars, TODAY, **kw)


def test_ok_row():
    r = classify()
    assert r["status"] == "ok" and r["market_cap_usd"] == 3_000_000_000_000 and r["bar_count"] == 1250


def test_every_status_value_can_be_produced():
    produced = {
        "ok": classify(),
        "no_bars": classify(bars={}),
        "stale": classify(bars={**OK_BARS, "last": date(2026, 10, 20)}),
        "not_equity": classify(info={**OK_INFO, "quoteType": "ETF"}),
        "name_mismatch": classify(name="Zzzz Qqqq"),
        "currency_mismatch": classify(info={**OK_INFO, "currency": "EUR"}),
        "under_20b": classify(info={**OK_INFO, "marketCap": 5e9}),
        "duplicate_name": classify(dup_names={"apple"}),
        "fetch_error": classify(info=None, bars=None),
    }
    assert set(produced) == set(vu.STATUSES)
    for status, row in produced.items():
        assert status in row["status"].split(";"), (status, row["status"])
    assert produced["ok"]["status"] == "ok"


def test_flags_are_joined_with_semicolons():
    r = classify(info={**OK_INFO, "quoteType": "ETF", "marketCap": 1e9}, bars={})
    assert set(r["status"].split(";")) == {"not_equity", "under_20b", "no_bars"}


def test_market_cap_is_converted_and_missing_cap_is_not_a_flag():
    r = classify("SAP.DE", "SAP", {**OK_INFO, "longName": "SAP SE", "currency": "EUR", "marketCap": 15e9})
    assert r["market_cap_usd"] == 16_500_000_000 and r["status"] == "under_20b"
    r = classify(info={**OK_INFO, "marketCap": None})
    assert r["status"] == "ok" and "market cap unavailable" in r["detail"]


def test_name_score_threshold():
    assert vu.name_score("Apple", "Apple Inc.") == 1.0
    assert vu.name_score("Mercedes-Benz", "Mercedes-Benz Group AG") == 1.0
    assert vu.name_score("Apple", "Banana Republic") < 0.6


# ---- verify_universe: driver with fakes ---------------------------------------------------------------------

def _write_universe(path, rows):
    path.write_text("ticker,name,region,sector\n" + "".join(f"{t},{n},US,Tech\n" for t, n in rows))


def _run(tmp_path, bars_fn, info_fn, **kw):
    u, out = tmp_path / "u.csv", tmp_path / "v.csv"
    if not u.exists():
        _write_universe(u, [("AAA", "Aaa"), ("BBB", "Bbb"), ("CCC", "Ccc")])
    code = vu.run(u, out, sleep=0, today=TODAY, fx_last=lambda s: 1.0, bars_fn=bars_fn, info_fn=info_fn, **kw)
    return code, read_rows(out)


def test_driver_writes_all_columns_and_rows(tmp_path):
    code, rows = _run(tmp_path, lambda ts: {t: OK_BARS for t in ts}, lambda t: {**OK_INFO, "longName": t.capitalize()})
    assert code == 0 and [r["ticker"] for r in rows] == ["AAA", "BBB", "CCC"]
    assert list(rows[0]) == vu.COLUMNS and all(r["verified_at"] for r in rows)


def test_driver_exit_0_with_flags_and_2_when_network_is_down(tmp_path):
    code, rows = _run(tmp_path, lambda ts: {}, lambda t: {**OK_INFO, "longName": t.capitalize()})
    assert code == 0 and all("no_bars" in r["status"] for r in rows)
    (tmp_path / "v.csv").unlink()

    def boom(ts):
        raise OSError("down")
    code, rows = _run(tmp_path, boom, lambda t: None)
    assert code == 2 and all(r["status"] == "fetch_error" for r in rows)


def test_driver_resumes_and_retries_only_fetch_errors(tmp_path):
    calls, down = [], ["BBB"]

    def info(t):
        calls.append(t)
        return None if t in down else {**OK_INFO, "longName": t.capitalize()}
    bars = lambda ts: {t: OK_BARS for t in ts if t != "BBB"}  # noqa: E731
    _run(tmp_path, bars, info)
    assert calls == ["AAA", "BBB", "CCC"]
    calls.clear()
    down.clear()
    code, rows = _run(tmp_path, lambda ts: {t: OK_BARS for t in ts}, info)
    assert calls == ["BBB"] and [r["ticker"] for r in rows] == ["AAA", "CCC", "BBB"]
    assert rows[-1]["status"] == "ok"


def test_driver_never_removes_a_ticker_and_respects_limit_and_tickers(tmp_path):
    _, rows = _run(tmp_path, lambda ts: {}, lambda t: None, limit=2)
    assert len(rows) == 2
    (tmp_path / "v.csv").unlink()
    _, rows = _run(tmp_path, lambda ts: {}, lambda t: None, tickers=["CCC"])
    assert [r["ticker"] for r in rows] == ["CCC"]


def test_driver_batches_downloads(tmp_path):
    sizes = []
    _run(tmp_path, lambda ts: sizes.append(len(ts)) or {}, lambda t: None, batch=2)
    assert sizes == [2, 1]


def test_duplicate_names_in_the_universe_are_flagged(tmp_path):
    u = tmp_path / "u.csv"
    _write_universe(u, [("GOOG", "Alphabet Inc."), ("GOOGL", "Alphabet")])
    _, rows = _run(tmp_path, lambda ts: {t: OK_BARS for t in ts}, lambda t: {**OK_INFO, "longName": "Alphabet Inc."})
    assert all("duplicate_name" in r["status"] for r in rows)


def test_help_runs():
    with pytest.raises(SystemExit) as e:
        vu.main(["--help"])
    assert e.value.code == 0
