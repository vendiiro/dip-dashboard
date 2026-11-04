"""Browser checks of the dashboard template (Rule 2 in CLAUDE.md). Skipped if Playwright or a Chromium is not available.

Set DIP_CHROMIUM=/path/to/chrome to use an existing browser; otherwise Playwright's own install is used.
"""
import os

import pytest

pw = pytest.importorskip("playwright.sync_api")

from dipdash.cli import main  # noqa: E402

NET_IGNORE = ("ERR_TUNNEL", "ERR_NAME_NOT_RESOLVED", "ERR_CONNECTION", "ERR_BLOCKED", "ERR_INTERNET_DISCONNECTED")


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=os.environ.get("DIP_CHROMIUM") or None)
        except Exception as e:                                   # no browser installed
            pytest.skip(f"no Chromium available: {str(e)[:80]}")
        yield b
        b.close()


@pytest.fixture(scope="module")
def demo_html(tmp_path_factory):
    out = tmp_path_factory.mktemp("dash") / "demo.html"
    assert main(["--demo", "--out", str(out)]) == 0
    return out.resolve().as_uri()


def open_page(browser, url, w=1280, h=900, scheme="light"):
    page = browser.new_page(viewport={"width": w, "height": h}, color_scheme=scheme)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # The web-font stylesheet is optional; a blocked font host (offline, sandbox proxy) is not a page error.
    page.on("console", lambda m: m.type == "error" and not any(x in m.text for x in NET_IGNORE) and "font" not in m.text.lower() and errors.append(m.text))
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("#tiles .tile")
    return page, errors


@pytest.mark.parametrize("w, h", [(1280, 900), (390, 844)])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_renders_without_errors_or_sideways_scroll(browser, demo_html, w, h, scheme):
    page, errors = open_page(browser, demo_html, w, h, scheme)
    assert errors == []
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    assert page.locator("#body tr.row").count() > 0
    page.close()


def test_default_view_uses_the_settings_rule_and_opens_the_top_candidate(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    assert page.input_value("#win") == "any" and page.is_hidden("#droplab")   # default rules: the single slider is hidden
    assert page.locator("tr.row.open").count() == 1 and page.locator("td.detail").count() == 1
    page.close()


def test_show_filter_changes_the_row_count(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    dips = page.locator("#body tr.row").count()
    page.click("#show button[data-v=all]")
    assert page.locator("#body tr.row").count() == page.evaluate("DATA.rows.length") > dips
    page.click("#show button[data-v=quality]")
    assert 0 < page.locator("#body tr.row").count() <= dips
    page.close()


def test_search_and_region_filters(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    page.click("#show button[data-v=all]")
    page.fill("#q", "nokia")
    assert page.locator("#body tr.row").count() == 1 and "NOKIA.HE" in page.inner_text("#body tr.row")
    page.fill("#q", "no such company")
    assert page.is_visible("#empty") and "No stocks match" in page.inner_text("#empty")
    page.fill("#q", "")
    page.click("#region button[data-v=Nordic]")
    assert page.locator("#body tr.row").count() == page.evaluate("DATA.rows.filter(r => r.region === 'Nordic').length")
    page.close()


def test_clicking_a_row_opens_and_closes_its_detail(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    rows = page.locator("#body tr.row")
    second = rows.nth(1)
    second.click()
    assert page.locator("tr.row.open").count() == 1 and second.get_attribute("aria-expanded") == "true"
    assert "quality checks" in page.inner_text("td.detail").lower()      # headings are upper-cased by CSS
    page.locator("#body tr.row").nth(1).click()
    assert page.locator("td.detail").count() == 0
    page.close()


def test_single_window_mode_enables_the_slider_and_changes_the_dips(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    before = page.inner_text("#tabletitle")
    page.select_option("#win", "r1")
    assert page.is_enabled("#drop") and page.input_value("#drop") == "4"
    page.fill("#drop", "12")
    page.dispatch_event("#drop", "input")
    assert page.inner_text("#tabletitle") != before
    page.close()


def test_sorting_toggles_direction_and_marks_the_header(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    page.click("#show button[data-v=all]")
    page.click("#head th:has-text('Price')")
    prices = lambda: [float(t.split()[0]) for t in page.locator("#body tr.row td:nth-child(2)").all_inner_texts()]
    desc = prices()
    assert desc == sorted(desc, reverse=True)
    page.click("#head th:has-text('Price')")
    assert prices() == sorted(desc)
    page.close()


def test_data_quality_badge_opens_its_panel(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    assert page.is_hidden("#dqpanel")
    page.click("#dqbtn")
    assert page.is_visible("#dqpanel") and "Data quality for this run" in page.inner_text("#dqpanel")
    page.close()


def test_untrusted_text_is_not_interpreted_as_html(browser, tmp_path):
    """A headline or company name containing markup must show as text and add no elements."""
    from dipdash.config import Settings, Stock
    from dipdash.dashboard import build_payload, write_dashboard
    from synth import slide, volume
    from datetime import date
    evil = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=1</script>'
    p = build_payload([Stock("EVIL", evil, "US", evil)], {"EVIL": (slide(), volume(260))}, {}, Settings(),
                      news_fn=lambda t: [{"title": evil, "src": evil, "url": "javascript:alert(1)"}], today=date(2026, 10, 30))
    out = write_dashboard(p, tmp_path / "evil.html")
    page, errors = open_page(browser, out.resolve().as_uri())
    assert page.evaluate("window.__pwned") is None and errors == []
    assert page.locator("#body img").count() == 0
    assert evil in page.inner_text("#body tr.row")
    assert page.locator("td.detail a").count() == 0                  # a javascript: URL is not made a link
    page.close()


SHOWN = "[...document.querySelectorAll('#body tr.row .tk')].map(e => [e.childNodes[1].textContent, !!e.querySelector('.new')])"


def test_default_dip_count_equals_the_python_rule(browser, demo_html):
    """The page and the nightly digest must agree: rows shown under 'All dips' are exactly the payload rows flagged `dip`."""
    page, _ = open_page(browser, demo_html)
    expected = page.evaluate("DATA.rows.filter(r => r.dip).map(r => r.t).sort()")
    shown = sorted(t for t, _ in page.evaluate(SHOWN))
    assert shown == expected and len(expected) > 0
    page.close()


def test_new_since_yesterday_tile_matches_the_rows_marked_new(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    more = page.locator("#tiles .tile").nth(1).locator(".chipmore")
    if more.count():
        more.click()                                              # the tile shows the first few chips; expand to see them all
    chips = sorted(page.locator("#tiles .tile").nth(1).locator(".chip").all_inner_texts())
    marked = sorted(t for t, new in page.evaluate(SHOWN) if new)
    assert chips == marked and len(chips) > 0
    page.close()


def test_each_default_rule_alone_flags_a_stock_on_the_page(browser, tmp_path):
    """One stock per rule, each flagged by that rule only. A page that implements just one window would miss two of them."""
    import pandas as pd
    from datetime import date
    from dipdash.config import Settings, Stock
    from dipdash.dashboard import build_payload, write_dashboard
    from synth import dates, volume

    def series(moves):                      # 260 flat bars at 100, then the given multipliers for the last len(moves) bars
        v = [100.0] * (260 - len(moves))
        for m in moves:
            v.append(v[-1] * m)
        return pd.Series(v, index=dates(260))

    stocks = {
        "ONE_DAY": series([0.95]),                                   # -5% today: 1-day rule only (5-day -5%, 20-day high -5%)
        "FIVE_DAY": series([0.984] * 5),                             # five falls of 1.6%: 5-day -7.7%, 1-day -1.6%, 20-day high -7.7%
        "HIGH_20D": series([0.97] * 5 + [1.0] * 10),                 # -14% ten to fifteen bars ago, flat since: 20-day high rule only
        "CALM": series([1.0]),
    }
    p = build_payload([Stock(t, t, "US") for t in stocks], {t: (c, volume(260)) for t, c in stocks.items()}, {}, Settings(),
                      today=date(2026, 10, 30))
    why = {r["t"]: [w.split()[0] for w in r["why"]] for r in p["rows"]}
    assert why == {"ONE_DAY": ["1-day"], "FIVE_DAY": ["5-day"], "HIGH_20D": ["below"], "CALM": []}
    page, errors = open_page(browser, write_dashboard(p, tmp_path / "rules.html").resolve().as_uri())
    shown = sorted(t for t, _ in page.evaluate(SHOWN))
    assert shown == ["FIVE_DAY", "HIGH_20D", "ONE_DAY"]
    assert errors == []
    page.close()


def test_many_identical_warnings_show_as_one_line_in_the_data_quality_panel(browser, tmp_path):
    from datetime import date
    from dipdash.config import Settings, Stock
    from dipdash.dashboard import build_payload, write_dashboard
    from dipdash.validate import Issue
    from synth import slide, volume
    iss = [Issue(f"S{i}", "partial_bar", "warn", "last bar is dated today") for i in range(8)] + [Issue("X", "spike_revert", "warn", "a")]
    p = build_payload([Stock("A", "A", "US")], {"A": (slide(), volume(260))}, {}, Settings(), today=date(2026, 10, 30), issues=iss)
    page, errors = open_page(browser, write_dashboard(p, tmp_path / "w.html").resolve().as_uri())
    page.click("#dqbtn")
    items = page.locator("#dqpanel li").all_inner_texts()
    assert errors == [] and len(items) == 2
    assert "(8 stocks) partial bar" in items[0] and "S0, S1" in items[0]
    page.close()


def _count_rows(page):
    return page.locator("#body tr.row").count()


def test_theme_focus_narrows_the_table_and_is_kept_in_the_link(browser, demo_html):
    page, errors = open_page(browser, demo_html)
    page.click('#show button[data-v="all"]')
    total = _count_rows(page)
    page.click('.th[data-id="pharma"]')
    pharma = _count_rows(page)
    assert 0 < pharma < total
    tickers = page.eval_on_selector_all("#body tr.row", "rs => rs.map(r => r.dataset.t)")
    assert "LLY" in tickers and "NVDA" not in tickers
    assert "focus=pharma" in page.evaluate("location.hash")
    page.click('.th[data-id="ai"]')                               # several themes combine (union)
    assert _count_rows(page) > pharma
    page.click('.th[data-id=""]')                                 # "All stocks" clears the focus
    assert _count_rows(page) == total
    assert errors == []


def test_size_filter_only_keeps_big_companies(browser, demo_html):
    page, errors = open_page(browser, demo_html)
    page.click('#show button[data-v="all"]')
    total = _count_rows(page)
    page.click('#size button[data-v="5e11"]')
    big = _count_rows(page)
    assert 0 < big < total
    page.goto(demo_html.split("#")[0] + "#focus=semis&size=100000000000")   # a bookmarked view restores itself
    page.reload(); page.wait_for_selector("#tiles .tile")
    assert page.get_attribute('.th[data-id="semis"]', "aria-pressed") == "true"
    assert page.get_attribute('#size button[data-v="1e11"]', "aria-pressed") == "true"
    assert errors == []
