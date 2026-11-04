"""Themes (config/themes.toml): loading, validation against the universe, and how they reach the dashboard payload."""
import pytest

from dipdash.config import Stock, Theme, load_themes, load_universe
from dipdash.dashboard import build_payload
from dipdash.demo import demo_inputs
from dipdash.config import Settings


def write(tmp_path, text):
    p = tmp_path / "themes.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_shipped_themes_only_use_universe_tickers():
    uni = load_universe()
    themes = load_themes(universe=uni)            # raises on any ticker missing from universe.csv
    assert len(themes) >= 10
    ids = {t.id for t in themes}
    assert {"ai", "semis", "pharma"} <= ids
    assert "LLY" in next(t for t in themes if t.id == "pharma").tickers


def test_missing_file_means_no_themes(tmp_path):
    assert load_themes(tmp_path / "nope.toml") == []


def test_unknown_ticker_is_an_error(tmp_path):
    p = write(tmp_path, '[[theme]]\nid="x"\nname="X"\ntickers=["AAA","ZZZ"]\n')
    with pytest.raises(ValueError, match="ZZZ"):
        load_themes(p, [Stock("AAA", "A", "US")])


@pytest.mark.parametrize("body,msg", [
    ('[[theme]]\nid="x"\nname="X"\n[[theme]]\nid="x"\nname="Y"\n', "duplicate"),
    ('[[theme]]\nid="x"\nname="X"\ntickers=["A","A"]\n', "twice"),
    ('[[theme]]\nid="x"\nname="X"\ncolour="red"\n', "unknown key"),
    ('[[theme]]\nname="X"\n', "id"),
])
def test_bad_theme_files_fail_loudly(tmp_path, body, msg):
    with pytest.raises((ValueError, TypeError), match=msg):
        load_themes(write(tmp_path, body))


def test_payload_tags_rows_and_lists_themes():
    uni = [Stock("AAA", "A", "US", "Tech"), Stock("BBB", "B", "US", "Health care")]
    prices, funds = demo_inputs(uni)
    th = [Theme("ai", "AI", "d", ("AAA",)), Theme("both", "Both", "", ("AAA", "BBB"))]
    p = build_payload(uni, prices, funds, Settings(), themes=th)
    by = {r["t"]: r for r in p["rows"]}
    assert by["AAA"]["themes"] == ["ai", "both"] and by["BBB"]["themes"] == ["both"]
    assert p["themes"][0] == {"id": "ai", "name": "AI", "desc": "d", "tickers": ["AAA"]}


def test_themes_never_change_the_screen():
    uni = [Stock("AAA", "A", "US", "Tech")]
    prices, funds = demo_inputs(uni)
    a = build_payload(uni, prices, funds, Settings())["rows"][0]
    b = build_payload(uni, prices, funds, Settings(), themes=[Theme("x", "X", "", ("AAA",))])["rows"][0]
    for k in ("dip", "why", "q", "setup", "knife"):
        assert a[k] == b[k]
