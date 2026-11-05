from datetime import date

from dipdash.config import Stock
from dipdash.coverage import COLUMNS, build_coverage, coverage_issues
from fakes import FakeYahoo
from synth import geometric

TODAY = date(2026, 10, 30)


def _u(*tickers):
    return [Stock(t, t, "Europe" if "." in t else "US") for t in tickers]


def test_coverage_table_counts_per_exchange(tmp_path):
    tks = ["AAA", "BBB", "S1.ST", "S2.ST", "S3.ST", "S4.ST", "H1.HE", "H2.HE"]
    u = _u(*tks)
    bars = {t: geometric(260, 0.0005, end="2026-10-29") for t in tks if t not in ("H1.HE", "H2.HE")}   # .HE: nothing arrived
    bars["S4.ST"] = geometric(260, 0.0005, end="2026-10-27")                                           # behind the other .ST stocks
    bars["BBB"] = geometric(260, 0.0005, end="2026-10-20")                                             # stale
    fake = FakeYahoo(bars)
    prices = fake.download(tks)
    funds = fake.fundamentals(list(prices), tmp_path / "f.json")
    funds["S3.ST"] = {}
    earn = {"AAA": {"next": "2026-11-05"}, "S1.ST": {"last": "2026-10-20", "next": None}, "S2.ST": {"last": None, "next": None}}
    rows, line = build_coverage(u, prices, funds, earn, TODAY, 4, reasons={"S4.ST": "last bar behind"},
                                status={"S2.ST": {"stale": True}})
    by = {r["label"]: r for r in rows}
    assert [r["label"] for r in rows] == ["US", ".HE", ".ST"] and set(rows[0]) == set(COLUMNS)
    assert {k: by["US"][k] for k in ("expected", "with_bars", "stale", "lagging", "fundamentals", "earnings")} == \
        {"expected": 2, "with_bars": 2, "stale": 1, "lagging": 0, "fundamentals": 2, "earnings": 1}
    assert (by[".ST"]["expected"], by[".ST"]["with_bars"], by[".ST"]["lagging"], by[".ST"]["fundamentals"], by[".ST"]["earnings"]) == (4, 4, 1, 3, 1)
    assert by[".ST"]["fetch_notes"] == 1 and by[".ST"]["fund_stale"] == 1
    assert (by[".HE"]["with_bars"], by[".HE"]["fundamentals"]) == (0, 0)
    assert "\n" not in line and "bars 6/8" in line and ".HE bars 0/2" in line


def test_holiday_does_not_count_as_lagging():
    tks = ["A.PA", "B.PA", "C.PA", "D.PA"]
    prices = {t: (geometric(60, 0.001, end="2026-10-27"), None) for t in tks}
    rows, _ = build_coverage(_u(*tks), prices, {}, {}, date(2026, 10, 28))
    assert rows[0]["lagging"] == 0 and rows[0]["with_bars"] == 4


def test_coverage_issues_flag_thin_exchange_but_leave_missing_ones_to_validate():
    rows = [
        {"label": ".ST", "exchange": "Nasdaq Stockholm", "expected": 10, "with_bars": 5, "earnings": 10},
        {"label": ".HE", "exchange": "Nasdaq Helsinki", "expected": 4, "with_bars": 0, "earnings": 0},
        {"label": "US", "exchange": "NYSE/Nasdaq", "expected": 10, "with_bars": 10, "earnings": 2},
    ]
    got = {(i.ticker, i.check, i.severity) for i in coverage_issues(rows)}
    assert got == {(".ST", "exchange_thin", "warn"), ("US", "earnings_coverage", "info")}


def test_empty_universe_gives_an_empty_table_and_a_line():
    rows, line = build_coverage([], {}, {}, {}, TODAY)
    assert rows == [] and line.startswith("Coverage")
