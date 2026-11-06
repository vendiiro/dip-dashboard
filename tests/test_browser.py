"""Browser checks of the dashboard template (Rule 2 in CLAUDE.md). Skipped if Playwright or a Chromium is not available.

Set DIP_CHROMIUM=/path/to/chrome to use an existing browser; otherwise Playwright's own install is used.
"""
import os

import pytest

pw = pytest.importorskip("playwright.sync_api")

from dipdash.cli import main  # noqa: E402


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
    # The Google Fonts stylesheet is optional (offline the page uses system fonts). Answer it with an empty sheet so a sandbox
    # or CI machine without internet does not turn a blocked font request into a failing console error.
    page.route("**/fonts.googleapis.com/**", lambda route: route.fulfill(status=200, content_type="text/css", body=""))
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and "font" not in m.text.lower() and errors.append(m.text))
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("#tiles .tile")
    return page, errors


def expand_rows(page):
    """Desktop shows the first 25 rows; press "Show all N stocks" when there is such a button (a filter change folds the list back)."""
    more = page.locator("[data-testid=rows-more]")
    if more.count():
        more.click()


@pytest.mark.parametrize("w, h", [(1280, 900), (390, 844)])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_renders_without_errors_or_sideways_scroll(browser, demo_html, w, h, scheme):
    page, errors = open_page(browser, demo_html, w, h, scheme)
    assert errors == []
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    assert page.locator("#body tr.row" if w > 600 else "#cards .sc").count() > 0      # the other layout is not built
    page.close()


def test_default_view_uses_the_settings_rule_and_starts_collapsed(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    assert page.input_value("#win") == "any" and page.is_hidden("#droplab")   # the slider is hidden under the default rules
    assert page.locator("tr.row.open").count() == 0 and page.locator("td.detail").count() == 0   # table first, details on click
    page.close()


def test_brief_and_compact_columns(browser, demo_html):
    page, errors = open_page(browser, demo_html)
    brief = page.inner_text("#brief")
    assert "Today in brief" in brief and "screened stocks are flagged as dips" in brief and "not a forecast" in brief
    assert "follows the filters below" not in brief                                  # it does not follow region or search
    assert "Dip and quality counts follow the window and quality settings; the rest covers all screened stocks" in brief
    assert not any(w in brief.lower() for w in ("buy", "sell", "top pick"))
    default_cols = page.locator("#head th").count()
    assert default_cols == 10 and page.is_visible("#head th:has-text('90 days')")      # sparkline column is in the default set
    assert page.locator("#head th:has-text('Vol')").count() == 0
    page.click("#colbtn")
    assert page.locator("#head th").count() == 14 and page.locator("#head th:has-text('Vol')").count() == 1
    assert page.inner_text("#colbtn") == "Fewer columns"
    first = page.locator("#body tr.row").first
    first.click()
    assert page.locator("td.detail").first.get_attribute("colspan") == "14"
    assert errors == []
    page.close()


def test_show_filter_changes_the_row_count(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    rowsel = page.locator("#body tr.row")
    dips = page.evaluate("DATA.rows.filter(r => r.dip).length")    # the table shows at most 25 of them; "Show all" is pressed below where the count matters
    total = page.evaluate("DATA.rows.length")
    page.click("#show button[data-v=all]")
    expand_rows(page)
    pw.expect(rowsel).to_have_count(total)
    assert total > dips
    pw.expect(page.locator("#show button[data-v=all] .ct")).to_have_text(str(total))
    page.click("#show button[data-v=quality]")
    expand_rows(page)
    n_quality = page.evaluate("DATA.rows.filter(r => window.__dipView(r.t).rank === 4).length")
    pw.expect(rowsel).to_have_count(n_quality)
    assert 0 < n_quality <= dips
    assert n_quality == page.evaluate("DATA.rows.filter(r => window.__dipView(r.t).rank === 4).length")
    assert n_quality == page.evaluate("DATA.rows.filter(r => r.setup === 'Quality dip').length")   # page and nightly label agree
    pw.expect(page.locator("[data-testid=tile-quality] .big")).to_have_text(str(n_quality))
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
    expand_rows(page)
    nordic = page.evaluate("DATA.rows.filter(r => r.region === 'Nordic').length")
    assert page.locator("#body tr.row").count() == nordic
    assert 0 < nordic < page.evaluate("DATA.rows.length")
    page.close()


def test_clicking_a_row_opens_and_closes_its_detail(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    rows = page.locator("#body tr.row")
    second = rows.nth(1)
    second.click()
    assert page.locator("tr.row.open").count() == 1 and second.locator(".tkbtn").get_attribute("aria-expanded") == "true"
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
    def prices():
        expand_rows(page)
        return [float(t.split()[0]) for t in page.locator("#body tr.row td[data-k=price]").all_inner_texts()]
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


SHOWN = "[...document.querySelectorAll('#body tr.row')].map(tr => [tr.dataset.t, !!tr.querySelector('[data-testid=new-badge]')])"


def test_default_dip_count_equals_the_python_rule(browser, demo_html):
    """The page and the nightly digest must agree: rows shown under 'All dips' are exactly the payload rows flagged `dip`."""
    page, _ = open_page(browser, demo_html)
    expected = page.evaluate("DATA.rows.filter(r => r.dip).map(r => r.t).sort()")
    expand_rows(page)
    shown = sorted(t for t, _ in page.evaluate(SHOWN))
    assert shown == expected and len(expected) > 0
    page.close()


def test_new_since_yesterday_tile_matches_the_rows_marked_new(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    tile = page.locator("[data-testid=tile-new]")
    expand_rows(page)
    more = tile.locator("[data-testid=tile-chip-more]")
    if more.count():                                    # the tile shows 8 chips; open "+N more" to read them all
        more.click()
    chips = sorted(tile.locator("[data-testid=tile-chip]").all_inner_texts())
    marked = sorted(t for t, new in page.evaluate(SHOWN) if new)
    assert chips == marked and len(chips) == int(tile.locator(".big").inner_text()) > 0
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


def test_filter_counts_chips_reset_and_detail_order(browser, demo_html):
    page, errors = open_page(browser, demo_html)
    assert page.is_hidden("#activebar")                                              # no chips while everything is at its default
    n_all = int(page.locator("#show button[data-v=all] .ct").inner_text())
    n_dips = int(page.locator("#show button[data-v=dips] .ct").inner_text())
    assert n_all >= n_dips > 0                                                       # live count beside each option
    page.click("#region button[data-v=US]")
    assert page.is_visible("#activebar") and "Region: US" in page.inner_text("#activebar")
    assert int(page.locator("#show button[data-v=dips] .ct").inner_text()) <= n_dips  # counts follow the other filters
    page.fill("#q", "zzzzqq")                                                        # no match: written empty state with a reset
    assert page.is_visible("#empty") and page.is_visible("#resetbtn")
    page.click("#resetbtn")
    assert page.is_hidden("#activebar") and page.is_hidden("#empty") and page.input_value("#q") == ""
    page.locator("#body tr.row").first.click()                                        # detail: flagged-because strip first, key numbers, more context
    d = page.inner_text("td.detail").lower()
    assert d.index("flagged because") < d.index("1 year") and "key numbers" in d and "more context" in d
    assert page.locator("td.detail .extra:visible").count() == 0
    page.click("td.detail button:has-text('More context')")
    assert page.locator("td.detail .extra:visible").count() > 0
    assert errors == []
    page.close()


# ---------------------------------------------------------------- FE-3 stale banner, FE-4 visible failure, FE-7 small fixes
def variant_html(tmp_path, demo_html, js, name="v.html"):
    """A copy of the demo page whose DATA is changed by `js` (run right after `const DATA = ...;`)."""
    from pathlib import Path
    from urllib.parse import urlparse
    from urllib.request import url2pathname
    html = Path(url2pathname(urlparse(demo_html).path)).read_text(encoding="utf-8")
    i = html.index("const DATA = ")
    j = html.index("\n", i)
    out = tmp_path / name
    out.write_text(html[:j + 1] + js + "\n" + html[j + 1:], encoding="utf-8")
    return out.resolve().as_uri()


def open_at(browser, url, when, w=1280, h=900):
    """Open with the browser clock fixed at `when` (ISO, local time) so the stale check is deterministic."""
    from datetime import datetime
    page = browser.new_page(viewport={"width": w, "height": h})
    page.clock.install(time=datetime.fromisoformat(when))
    page.route("**/fonts.googleapis.com/**", lambda route: route.fulfill(status=200, content_type="text/css", body=""))
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("#tiles .tile")
    return page, errors


def newest_asof(page):
    return page.evaluate("DATA.rows.map(r => r.asof).sort().at(-1)")


def test_stale_banner_names_the_date_when_prices_are_over_two_weekdays_old(browser, demo_html, tmp_path):
    from datetime import date, timedelta
    url = variant_html(tmp_path, demo_html, "DATA.demo = false;")
    page, errors = open_at(browser, url, "2026-01-01T12:00:00")
    asof = date.fromisoformat(newest_asof(page))
    page.close()

    def plus_weekdays(d, n):
        while n:
            d += timedelta(days=1)
            n -= d.weekday() < 5
        return d

    late = plus_weekdays(asof, 5)
    page, errors = open_at(browser, url, f"{late.isoformat()}T10:00:00")
    assert page.is_visible("[data-testid=stale]") and page.get_attribute("#stale", "role") == "status"
    text = page.inner_text("#stale")
    day = f"{asof.strftime('%a')} {asof.day} {asof.strftime('%b')}"
    assert day in text and "5 weekdays ago" in text and "may have failed" in text and "not today" in text
    assert not any(w in text.lower() for w in ("buy", "sell"))
    assert errors == []
    page.close()
    for n in (0, 2):                                                    # same day, or 2 weekdays later: no banner
        page, _ = open_at(browser, url, f"{plus_weekdays(asof, n).isoformat()}T10:00:00")
        assert page.is_hidden("[data-testid=stale]")
        page.close()
    page, _ = open_at(browser, url, f"{plus_weekdays(asof, 3).isoformat()}T10:00:00")   # 3 weekdays: banner
    assert page.is_visible("[data-testid=stale]")
    page.close()


def test_demo_page_never_shows_the_stale_banner(browser, demo_html):
    page, _ = open_at(browser, demo_html, "2030-06-03T10:00:00")
    assert page.is_hidden("[data-testid=stale]")
    page.close()


def test_a_broken_row_is_skipped_and_named_in_a_visible_alert(browser, demo_html, tmp_path):
    js = "{ const r = DATA.rows.find(x => x.dip); r.spark = null; window.__broken = r.t; }"
    page, errors = open_page(browser, variant_html(tmp_path, demo_html, js))
    t = page.evaluate("window.__broken")
    assert [e for e in errors if not e.startswith("dashboard: could not draw")] == []    # caught and logged, no uncaught error
    assert page.is_visible("[role=alert]#fail") and t in page.inner_text("#fail")
    assert "could not draw part of the screen" in page.inner_text("#fail")
    assert page.locator(f"#body tr.row[data-t='{t}']").count() == 0 and page.locator("#body tr.row").count() > 0
    assert "s-crit" in page.get_attribute("#dqbtn", "class") and "1 stock failed to draw" in page.inner_text("#dqbtn")
    assert page.locator("#hist svg").count() == 1 and page.locator("#sect svg").count() == 1   # the rest is drawn
    page.close()


def test_a_broken_chart_leaves_the_detail_and_the_table(browser, demo_html, tmp_path):
    js = "{ const r = DATA.rows.find(x => x.dip); r.hist = null; window.__broken = r.t; }"
    page, errors = open_page(browser, variant_html(tmp_path, demo_html, js))
    t = page.evaluate("window.__broken")
    assert page.is_hidden("#fail")                                      # nothing broken until the detail is opened
    page.click(f"#body tr.row[data-t='{t}']")
    assert [e for e in errors if not e.startswith("dashboard: could not draw")] == [] and page.locator("td.detail").count() == 1
    assert "1-year chart could not be drawn" in page.inner_text("td.detail") and "key numbers" in page.inner_text("td.detail").lower()
    assert t in page.inner_text("#fail") and "1-year chart" in page.inner_text("#fail")
    page.close()


def test_a_data_file_that_is_not_valid_javascript_still_shows_a_message(browser, demo_html, tmp_path):
    from pathlib import Path
    from urllib.parse import urlparse
    from urllib.request import url2pathname
    html = Path(url2pathname(urlparse(demo_html).path)).read_text(encoding="utf-8")
    i = html.index("const DATA = ")
    bad = tmp_path / "cut.html"
    bad.write_text(html[:i + 200] + html[html.index("\n", i):], encoding="utf-8")    # payload cut short mid-line
    page = browser.new_page()
    page.route("**/fonts.googleapis.com/**", lambda route: route.fulfill(status=200, content_type="text/css", body=""))
    page.goto(bad.resolve().as_uri(), wait_until="load")
    assert page.is_visible("#fail") and "could not read its data file" in page.inner_text("#fail")
    page.close()


def test_noscript_message(browser, demo_html):
    ctx = browser.new_context(java_script_enabled=False)
    page = ctx.new_page()
    page.route("**/fonts.googleapis.com/**", lambda route: route.fulfill(status=200, content_type="text/css", body=""))
    page.goto(demo_html, wait_until="domcontentloaded")
    assert "This dashboard needs JavaScript" in page.inner_text("main") and "output/digest.md" in page.inner_text("main")
    ctx.close()


def test_payload_setup_stays_a_string_and_the_view_is_separate(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    assert page.evaluate("DATA.rows.every(r => typeof r.setup === 'string' && !('view' in r))")
    assert page.evaluate("typeof window.__dipView(DATA.rows[0].t).rank") == "number"
    page.close()


def test_detail_chart_draws_when_a_stock_has_a_holiday_gap_in_hist(browser, demo_html, tmp_path):
    # a null in hist.c/s/h is an axis day without a bar (exchange holiday): the chart skips it, draws every other point and does not fail
    js = ("{ const r = DATA.rows.find(x => x.dip), h = r.hist, k = 120; "
          "window.__n = h.c.length; window.__t = r.t; window.__after = DATA.chart_dates[h.o + k + 1]; "
          "h.c[k] = null; h.s[k] = null; h.h[k] = null; }")
    page, errors = open_page(browser, variant_html(tmp_path, demo_html, js))
    t, n = page.evaluate("window.__t"), page.evaluate("window.__n")
    page.click(f"#body tr.row[data-t='{t}']")
    assert errors == [] and page.is_hidden("#fail") and page.locator("td.detail svg[role=img]").count() == 1
    d = page.get_attribute("td.detail svg[role=img] path[stroke-width='1.8']", "d")
    assert d.count("L") + d.count("M") == n - 1 and d.startswith("M") and d.count("M") == 1      # one unbroken line over the other days
    assert page.locator("td.detail .enddot").count() == 1
    page.close()


def test_end_dots_are_coloured_by_direction(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    page.click("#show button[data-v=all]")
    expand_rows(page)
    up = page.evaluate("DATA.rows.find(r => r.hist.c.at(-1) > r.hist.c[0] && r.spark.at(-1) > r.spark[0]).t")
    down = page.evaluate("DATA.rows.find(r => r.hist.c.at(-1) < r.hist.c[0] && r.spark.at(-1) < r.spark[0]).t")
    for t, d in ((up, "up"), (down, "down")):
        row = page.locator(f"#body tr.row[data-t='{t}']")
        assert row.locator(".enddot").get_attribute("data-dir") == d
        row.click()
        assert page.locator("td.detail .enddot").get_attribute("data-dir") == d
        assert page.locator("td.detail .enddot").get_attribute("fill") == f"var(--{d})"
        row.click()
    page.close()


def test_detail_chart_axis_names_the_currency_and_foot_notes_are_styled(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    page.locator("#body tr.row").first.click()
    ccy = page.evaluate("DATA.rows.find(r => r.t === document.querySelector('tr.row.open').dataset.t).ccy")
    cap = page.text_content("td.detail svg .axcap")
    assert cap == "Price" + (f", {ccy}" if ccy else "")
    page.evaluate("document.querySelector('td.detail').append(Object.assign(document.createElement('div'), {className: 'foot', id: 'probe'}))")
    assert page.evaluate("getComputedStyle(document.getElementById('probe')).fontSize") == "12.5px"
    page.close()


def test_charts_redraw_when_the_width_changes(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    page.locator("#body tr.row").first.click()
    before = page.get_attribute("td.detail svg[role=img]", "width")
    page.set_viewport_size({"width": 700, "height": 900})
    page.wait_for_function(f"document.querySelector('td.detail svg[role=img]').getAttribute('width') !== '{before}'", timeout=3000)
    assert int(page.get_attribute("td.detail svg[role=img]", "width")) < int(before)
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    page.close()


def test_stock_buttons_are_tap_sized_without_taller_rows(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    h = page.evaluate("document.querySelector('#body tr.row .tkbtn').getBoundingClientRect().height")
    row = page.evaluate("document.querySelector('#body tr.row').getBoundingClientRect().height")
    assert h >= 40 and row < 70
    page.close()


def test_phone_shows_ten_cards_then_a_show_all_button(browser, demo_html):
    page, errors = open_page(browser, demo_html, 390, 844)
    n = page.evaluate("DATA.rows.filter(r => r.dip).length")
    assert n > 10
    assert page.locator("#cards .sc").count() == 10
    more = page.locator("[data-testid=cards-more]")
    assert more.inner_text() == f"Show all {n} stocks" and more.bounding_box()["height"] >= 40
    more.focus()
    page.keyboard.press("Enter")
    assert page.locator("#cards .sc").count() == n
    assert page.evaluate("document.activeElement.dataset.testid") == "cards-more"   # focus stays on the button
    page.click("#ctltoggle")
    page.click("#show button[data-v=all]")                                          # a filter change folds the list back
    assert page.locator("#cards .sc").count() == 10
    page.fill("#q", "nokia")
    assert page.locator("#cards .sc").count() == 1 and page.locator("[data-testid=cards-more]").count() == 0
    assert errors == []
    page.close()


def test_setup_label_shows_setup_text_and_keys_on_the_enum(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    page.click("#show button[data-v=all]")
    for t, text in page.evaluate("DATA.rows.map(r => [r.t, r.setup_text])")[:40]:
        badge = page.locator(f"#body tr.row[data-t='{t}'] td[data-k=setup] .badge")
        if badge.count():
            assert text in badge.inner_text()
    assert "Quality dip" not in page.inner_text("#body")                              # the enum is a key, not a label
    assert page.evaluate("DATA.rows.some(r => /^Dip · passes \\d+ of \\d+ scored checks( \\(\\d+ no data\\))?$/.test(r.setup_text))")
    page.close()


def test_default_order_is_size_of_drop_and_user_sort_still_works(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    page.click("#show button[data-v=all]")
    vals = page.evaluate("[...document.querySelectorAll('#body tr.row')].map(tr => DATA.rows.find(r => r.t === tr.dataset.t).r5).filter(v => v != null)")
    assert len(vals) > 5 and vals == sorted(vals)                                     # biggest drop first, whatever the label
    assert "Size of drop (default)" in page.inner_html("#sortsel")
    page.click("#head th:has-text('Price')")
    assert page.locator("#head th[aria-sort=descending], #head th[aria-sort=ascending]").count() == 1
    page.close()


def test_footer_explains_scored_distorted_and_net_margin(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    page.click("[data-testid=defs-toggle]")                                           # the definitions are closed until asked for
    foot = page.inner_text("footer").lower()
    for need in ("scored on n/6", "distorted", "above 100%", "net margin above 0", "listed as missing, not as failed", "definitions, not tests", "return on equity", "score-based label"):
        assert need in foot
    assert not any(w in foot for w in ("top pick", "recommend", "you should buy"))
    page.close()


def test_distorted_and_no_fundamentals_states_render(browser, demo_html):
    page, errors = open_page(browser, demo_html)
    page.evaluate("""() => { const r = DATA.rows.find(x => x.dip && x.q != null && !x.knife); r.q_status = 'distorted'; r.q_why = 'ROE and debt/equity are both missing'; window.__t = r.t; document.getElementById('q').dispatchEvent(new Event('input')); }""")
    t = page.evaluate("window.__t")
    expand_rows(page)
    badge = page.locator(f"#body tr.row[data-t='{t}'] .badge")
    assert "Dip · data looks unreliable" in badge.inner_text() and "ROE and debt/equity are both missing" in badge.get_attribute("title")
    title = badge.get_attribute("title")
    assert "no fundamentals" not in title.lower().replace("dip, no fundamentals", "") and "unreliable" in title   # data exists, so the tip must not say it is missing
    assert "nightly screen labels" not in title
    page.locator(f"#body tr.row[data-t='{t}']").click()
    assert "distorted" in page.inner_text("td.detail").lower()
    assert errors == []
    page.close()


def test_default_sort_note_shows_until_a_column_is_chosen(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    note = page.locator("#sortnote")
    assert note.is_visible() and note.inner_text() == "Sorted by size of drop. You can also sort by quality score or 5d vs index."
    assert page.locator("#head th[aria-sort=ascending], #head th[aria-sort=descending]").count() == 0
    page.click("#head th:has-text('Price')")
    assert note.is_hidden() and page.locator("#head th[aria-sort=ascending], #head th[aria-sort=descending]").count() == 1
    page.click("#show button[data-v=all]")                                            # a filter change returns to the default order
    assert note.is_visible()
    page.close()


def test_scroll_cue_shows_only_while_the_table_scrolls_sideways(browser, demo_html):
    page, _ = open_page(browser, demo_html, 1100, 800)
    assert page.locator("#scrollcue").is_hidden()
    page.click("#colbtn")
    assert page.evaluate("document.querySelector('.scroll').classList.contains('hs')") and page.locator("#scrollcue").is_visible()
    page.click("#colbtn")
    assert page.locator("#scrollcue").is_hidden()
    page.close()


def test_market_adjusted_row_shows_no_rough_note_and_shows_se(browser, demo_html, tmp_path):
    js = ("{ const r = DATA.rows.find(x => x.dip); r.res5 = -0.031; r.res5z = -1.2; r.beta = 1.2; r.beta_raw = 1.2; r.beta_side = null;"
          " r.beta_se = 0.1; r.mkt_adj = true; r.res_why = null; window.__forced = r.t; }")
    page, errors = open_page(browser, variant_html(tmp_path, demo_html, js))
    t = page.evaluate("window.__forced")
    page.click("#colbtn")
    row = page.locator(f"#body tr.row[data-t='{t}']")
    assert "rough" not in row.inner_text()
    row.click()
    page.click("td.detail button.more")
    detail = page.inner_text("td.detail")
    assert "rough" not in detail and "±0.10" in detail
    assert errors == []
    page.close()


@pytest.mark.parametrize("n, check, drop_region, cls, icon, label", [
    (1, "fetch_failed", None, "s-note", "•", "1 stock left out"),
    (4, "stale", None, "s-note", "•", "4 stocks left out"),                 # below the threshold: max(5, 5% of 348) = 18
    (30, "fetch_failed", None, "s-crit", "✕", "30 stocks left out"),
    (1, "fetch_failed", "Nordic", "s-crit", "✕", "1 stock left out"),        # a whole region has no rows
    (1, "bad_run", None, "s-crit", "✕", "1 other note"),                     # not stock-level: a real error
])
def test_status_pill_is_red_only_for_a_real_problem(browser, demo_html, tmp_path, n, check, drop_region, cls, icon, label):
    js = ("DATA.issues = DATA.rows.slice(0, %d).map(r => ({severity: 'error', check: '%s', ticker: r.t, detail: 'x'}));" % (n, check)
          + ("DATA.rows = DATA.rows.filter(r => r.region !== '%s');" % drop_region if drop_region else ""))
    page, errors = open_page(browser, variant_html(tmp_path, demo_html, js))
    assert cls in page.get_attribute("#dqbtn", "class") and page.inner_text("#dqic") == icon
    assert label in page.inner_text("#dqbtn")
    assert errors == []
    page.close()


def test_phone_opened_card_shows_checks_and_numbers_before_the_chart(browser, demo_html):
    ph, _ = open_page(browser, demo_html, 390, 844)
    ph.locator("#cards .schead").first.click()
    ys = ph.evaluate("(() => { const d = document.querySelector('#cards .scdetail'); const top = s => [...d.querySelectorAll('h3')].find(h => h.textContent.startsWith(s)).getBoundingClientRect().top; "
                     "return [d.querySelector('.whystrip') ? d.querySelector('.whystrip').getBoundingClientRect().top : -1, top('Quality checks'), top('Key numbers'), top('1 year'), top('Headlines')]; })()")
    assert ys[1] < ys[2] < ys[3] < ys[4] and ys[0] < ys[1]
    ph.close()


def test_phone_sort_chooser_is_visible_without_opening_filters(browser, demo_html):
    ph, _ = open_page(browser, demo_html, 390, 844)
    assert ph.locator("#controls").is_hidden() and ph.locator("#sortsel").is_visible()
    ph.select_option("#sortsel", "q")
    assert ph.locator("#sortnote").is_hidden()
    ph.close()
    dk, _ = open_page(browser, demo_html, 1280, 900)
    assert dk.locator("#sortsel").is_hidden()
    dk.close()


def test_neutral_check_threshold_wording_and_title(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    assert page.title() == "Dip Screen" and page.inner_text("h1") == "Dip Screen"
    assert page.locator("[data-testid=tile-quality] .lab").inner_text() == "Dips meeting the check thresholds"
    assert "meet the check thresholds (see Definitions)" in page.inner_text("#brief")
    page.click("#show button[data-v=quality]")
    assert page.inner_text("#tabletitle").startswith("Dips meeting the check thresholds")
    assert "Dips meeting the check thresholds" in page.inner_text("#activebar")
    visible = (page.inner_text("main") + " ".join(page.evaluate("[...document.querySelectorAll('[title]')].map(e => e.title)"))).lower()
    for old in ("quality dip", "quality bar", "pass the quality", "passing the checks", "dip, low quality"):
        assert old not in visible
    page.close()


def test_label_under_non_default_controls_uses_scored_denominator(browser, demo_html):
    page, errors = open_page(browser, demo_html)
    page.select_option("#win", "r5")
    page.evaluate("() => { const d = document.getElementById('drop'); d.value = 1; d.dispatchEvent(new Event('input')); }")
    texts = page.evaluate("[...document.querySelectorAll('#body td[data-k=setup] .badge')].map(b => b.textContent)")
    assert texts and any("scored checks" in t for t in texts)
    assert not any(" checks" in t and "scored" not in t and "passes" in t for t in texts)
    assert errors == []
    page.close()


def test_alert_badge_shows_setup_text_keyed_on_the_enum(browser, demo_html):
    page, errors = open_page(browser, demo_html)
    n = page.evaluate("(DATA.alerts || []).filter(a => a.context && a.context.setup_text).length")
    if n:
        txt = page.inner_text("#alerts")
        first = page.evaluate("DATA.alerts.find(a => a.context && a.context.setup_text).context.setup_text")
        assert first in txt and "Quality dip" not in txt
    assert errors == []
    page.close()


def test_alerts_empty_state_does_not_inherit_the_generic_empty_rule(browser, demo_html, tmp_path):
    """`.empty` (centred "no stocks" box) and the alerts' quiet state are separate components: `.alerts-empty`."""
    for js in ("DATA.alerts = [];", "DATA.alerts = null;"):
        page, errors = open_page(browser, variant_html(tmp_path, demo_html, js), w=390, h=844)
        assert page.locator("#alerts.alerts-empty").count() == 1 and page.locator("#alerts.empty").count() == 0
        align = page.evaluate("""() => { const b = document.getElementById('alerts');
            return [b, ...b.querySelectorAll('h2, .sub')].map(e => getComputedStyle(e).textAlign); }""")
        assert "center" not in align, align
        assert errors == []
        page.close()


def test_alerts_more_hover_does_not_take_the_more_context_button_style(browser, demo_html, tmp_path):
    js = "DATA.alerts = DATA.alerts || []; while (DATA.alerts.length && DATA.alerts.length < 12) DATA.alerts = DATA.alerts.concat(DATA.alerts.map(a => Object.assign({}, a)));"
    page, errors = open_page(browser, variant_html(tmp_path, demo_html, js))
    btn = page.locator("#alerts button.alerts-more")
    assert btn.count() == 1 and page.locator("#alerts button.more").count() == 0
    css = "e => { const c = getComputedStyle(e); return [c.backgroundColor, c.borderTopLeftRadius, c.alignSelf]; }"
    rest = btn.evaluate(css)
    btn.hover()
    hover = btn.evaluate(css)
    assert hover == rest == ["rgba(0, 0, 0, 0)", "0px", "auto"], (rest, hover)
    # the "More context" button in the detail keeps its own hover background
    page.locator("#body tr.row").first.click()
    mc = page.locator("td.detail button.more").first
    mc_rest = mc.evaluate(css)[0]
    mc.hover()
    assert mc.evaluate(css)[0] != mc_rest and mc.evaluate(css)[0] != "rgba(0, 0, 0, 0)"
    # the alerts control still opens and closes (JS finds the renamed class)
    btn.click()
    assert page.locator("#alerts button.alerts-more").get_attribute("aria-expanded") == "true"
    assert errors == []
    page.close()


def test_hide_knives_label_is_a_40px_target(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    assert page.locator("label[for=hideknife]").bounding_box()["height"] >= 40
    page.close()


def test_definitions_toggle_is_closed_and_keeps_sources_and_advice_visible(browser, demo_html):
    for w, h in ((1280, 900), (390, 844)):
        page, errors = open_page(browser, demo_html, w, h)
        tog = page.locator("[data-testid=defs-toggle]")
        assert tog.inner_text() == "Definitions" and tog.bounding_box()["height"] >= 40
        assert page.evaluate("document.getElementById('defs').open") is False       # closed by default on both widths
        assert page.locator("#def-setup").is_hidden() and page.locator("#def-res").is_hidden()
        always = page.locator("[data-testid=foot-always]")
        assert always.is_visible() and "Not investment advice" in always.inner_text() and "Sources" in always.inner_text()
        tog.click()
        assert page.locator("#def-setup").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
        assert errors == []
        page.close()


def test_definition_links_open_the_toggle_and_scroll_to_the_entry(browser, demo_html):
    page, errors = open_page(browser, demo_html, 390, 844)
    page.click("#brief a[href='#def-q']")                                             # the "see Definitions" link in the brief
    assert page.evaluate("document.getElementById('defs').open") is True
    assert page.locator("#def-q").is_visible() and page.evaluate("document.getElementById('def-q').getBoundingClientRect().top < innerHeight")
    page.close()
    page, _ = open_page(browser, demo_html + "#def-setup", 1280, 900)                 # a direct link opens it too
    assert page.evaluate("document.getElementById('defs').open") is True and page.locator("#def-setup").is_visible()
    page.evaluate("document.getElementById('defs').open = false; location.hash = '#def-beta'")
    pw.expect(page.locator("#def-beta")).to_be_visible()
    assert errors == []
    page.close()


def test_residual_label_is_plain_and_beta_is_defined_once(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    page.click("#colbtn")
    heads = [h.lower() for h in page.locator("#head th").all_inner_texts()]     # the header is upper-cased by CSS
    assert any("5d beyond market (beta-adj.)" in h for h in heads) and not any("resid." in h for h in heads)      # short header, full name in the tooltip
    assert "5d beyond market (beta-adjusted)" in page.locator("#head th[data-k=res5]").get_attribute("title")
    assert any(h.strip() == "5d vs index" for h in heads)
    page.click("[data-testid=defs-toggle]")
    names = page.locator("footer dt").all_inner_texts()
    assert "5d beyond market (beta-adjusted)" in names and "5d vs index" in names
    assert names.index("5d vs index") == names.index("5d beyond market (beta-adjusted)") - 1   # plain first, adjusted second
    assert names.count("Beta") == 1 and "5d resid." not in names
    res, beta = page.inner_text("#def-res"), page.inner_text("#def-beta")
    assert "left over after removing the index move" in res and "standard deviation" in res and "does not explain" not in res
    assert "moves with its index" in beta and "±0.2" not in beta and "different year of data" in beta
    page.locator("#body tr.row").first.click()
    page.click("td.detail button.more")
    detail = page.inner_text("td.detail")
    assert "5d beyond market (beta-adjusted)" in detail and "in standard deviations" in detail and "std devs" not in detail
    assert "5d move vs" not in detail and "Resid. in std devs" not in detail and "5d resid." not in detail
    assert "±0.2" not in page.inner_text("body")
    page.close()


def test_5d_vs_index_naming_in_tooltips_and_tile_foot(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    page.click("#colbtn")
    tips = page.evaluate("[...document.querySelectorAll('#head th')].map(t => t.title || '')")
    assert not any("does not explain" in t for t in tips)
    assert any(t.startswith("The part of the 5-day move not explained by how much the stock normally follows the market") and "(beta). Beta is estimated" in t for t in tips)
    market = page.locator("[data-testid=tile-market]").inner_text()
    assert "5d move vs" not in market
    page.close()


def test_definition_link_scrolls_the_heading_into_view_and_moves_focus(browser, demo_html):
    page, errors = open_page(browser, demo_html, 390, 844)
    page.click("#brief a[href='#def-q']")
    info = page.evaluate("""() => { const dd = document.getElementById('def-q'), dt = dd.previousElementSibling;
        return {tag: dt.tagName, dtTop: dt.getBoundingClientRect().top, vh: innerHeight, dtHit: dt.classList.contains('hit'),
                ddHit: dd.classList.contains('hit'), focus: document.activeElement === dd}; }""")
    assert info["tag"] == "DT" and 0 <= info["dtTop"] < info["vh"]                  # the heading itself is on screen
    assert info["dtHit"] and info["ddHit"] and info["focus"]                        # both highlighted, focus on the entry
    page.close()
    page, _ = open_page(browser, demo_html + "#def-res", 1280, 900)
    top = page.evaluate("document.getElementById('def-res').previousElementSibling.getBoundingClientRect().top")
    assert 0 <= top < 900 and page.evaluate("document.activeElement.id") == "def-res"
    assert errors == []
    page.close()


def test_brief_definitions_link_has_a_40px_tap_area_without_changing_the_line(browser, demo_html):
    page, _ = open_page(browser, demo_html, 390, 844)
    link = page.locator("#brief a[href='#def-q']")
    assert link.bounding_box()["height"] >= 40
    h = page.evaluate("document.querySelector('#brief p').getBoundingClientRect().height")
    page.add_style_tag(content="#brief p a{padding:0 !important;margin:0 !important}")
    assert abs(page.evaluate("document.querySelector('#brief p').getBoundingClientRect().height") - h) < 1
    page.close()


def test_quality_tile_reconciles_with_the_all_dips_count(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    dips = page.evaluate("DATA.rows.filter(r => __dipView(r.t).rank > 0).length")
    big = page.locator("[data-testid=tile-quality] .big").inner_text()
    foot = page.locator("[data-testid=tile-quality] .foot").inner_text()
    assert foot.startswith(f"{big} of the {dips} dips below meet the check thresholds (quality score ≥ ") and "net margin above 0) · drop window: default" in foot
    page.click("#show button[data-v=dips]")
    assert page.inner_text("#tabletitle") == f"All dips · {dips}"
    page.close()


def test_phone_filters_summary_says_quality_score(browser, demo_html):
    page, _ = open_page(browser, demo_html, 390, 844)
    assert "Quality score ≥ " in page.text_content("#ctlsum")
    assert "quality ≥" not in page.text_content("#ctlsum").lower()
    page.close()


# ---------- FE-1 / FE-2: table near the top, sticky header, 25 rows then "Show all N stocks", no hidden layout ----------
ROWS_FIRST = 25


def test_desktop_shows_25_rows_then_show_all_and_the_count_stays_right(browser, demo_html):
    page, errors = open_page(browser, demo_html, 1280, 800)
    n = page.evaluate("DATA.rows.filter(r => r.dip).length")
    assert n > ROWS_FIRST
    assert page.locator("#body tr.row").count() == ROWS_FIRST
    more = page.locator("[data-testid=rows-more]")
    assert more.inner_text() == f"Show all {n} stocks" and more.get_attribute("aria-expanded") == "false" and more.bounding_box()["height"] >= 40
    assert page.inner_text("#rowsmore").startswith(f"Showing the first {ROWS_FIRST} of {n} stocks")
    assert page.inner_text("#tabletitle").endswith(f"· {n}")                               # the title counts the list, not the drawn rows
    more.focus()
    page.keyboard.press("Enter")
    assert page.locator("#body tr.row").count() == n
    assert more.inner_text() == f"Show the first {ROWS_FIRST} only" and page.inner_text("#rowsmore").startswith(f"Showing all {n} stocks")
    assert page.evaluate("document.activeElement.dataset.testid") == "rows-more"           # focus stays on the button
    assert page.inner_text("#tabletitle").endswith(f"· {n}")
    page.click("#region button[data-v=US]")                                                  # a filter change folds the list back
    n_us = page.evaluate("DATA.rows.filter(r => r.dip && r.region === 'US').length")
    assert n_us > ROWS_FIRST and page.locator("#body tr.row").count() == ROWS_FIRST
    assert page.inner_text("[data-testid=rows-more]") == f"Show all {n_us} stocks"
    page.click("#region button[data-v=Nordic]")                                              # a short list has no button at all
    assert page.locator("#body tr.row").count() <= ROWS_FIRST and page.is_hidden("#rowsmore") and page.locator("[data-testid=rows-more]").count() == 0
    assert page.locator("#cards .sc").count() == 0                                           # the phone cards are not built on desktop
    assert errors == []
    page.close()


def test_sorting_and_opening_a_row_work_with_the_row_cap(browser, demo_html):
    page, _ = open_page(browser, demo_html, 1280, 800)
    page.click("#head th:has-text('Price')")                                                 # sorts the whole list, then shows its first 25
    prices = [float(t.split()[0]) for t in page.locator("#body tr.row td[data-k=price]").all_inner_texts()]
    all_prices = sorted(page.evaluate("DATA.rows.filter(r => r.dip).map(r => r.price)"), reverse=True)
    assert prices == all_prices[:ROWS_FIRST]
    assert page.locator("[data-testid=rows-more]").count() == 1                              # the sort did not expand the list
    page.locator("#body tr.row").nth(2).click()                                              # opening a detail keeps the cap
    assert page.locator("td.detail").count() == 1 and page.locator("#body tr.row").count() == ROWS_FIRST
    page.close()


def test_a_row_beyond_the_first_25_is_found_by_expanding_or_by_searching(browser, demo_html):
    page, _ = open_page(browser, demo_html, 1280, 800)
    shown = page.evaluate("[...document.querySelectorAll('#body tr.row')].map(tr => tr.dataset.t)")
    hidden = page.evaluate("(shown) => DATA.rows.filter(r => r.dip).map(r => r.t).filter(t => !shown.includes(t))", shown)
    assert len(hidden) > 0
    t = hidden[-1]
    assert page.locator(f"#body tr.row[data-t='{t}']").count() == 0
    page.fill("#q", t)                                                                       # by filtering: no need to expand
    assert page.locator(f"#body tr.row[data-t='{t}']").count() == 1 and page.locator("[data-testid=rows-more]").count() == 0
    page.fill("#q", "")
    assert page.locator(f"#body tr.row[data-t='{t}']").count() == 0
    page.click("[data-testid=rows-more]")                                                    # by expanding
    assert page.locator(f"#body tr.row[data-t='{t}']").count() == 1
    page.close()


def test_phone_search_finds_a_card_beyond_the_first_ten(browser, demo_html):
    page, _ = open_page(browser, demo_html, 390, 844)
    shown = page.evaluate("[...document.querySelectorAll('#cards .sc')].map(c => c.dataset.t)")
    t = page.evaluate("(shown) => DATA.rows.filter(r => r.dip).map(r => r.t).filter(t => !shown.includes(t)).at(-1)", shown)
    assert page.locator(f"#cards .sc[data-t='{t}']").count() == 0
    page.click("#ctltoggle")
    page.fill("#q", t)
    assert page.locator(f"#cards .sc[data-t='{t}']").count() == 1
    page.close()


def test_an_open_row_outside_the_cap_stays_visible(browser, demo_html):
    page, _ = open_page(browser, demo_html, 1280, 800)
    page.click("[data-testid=rows-more]")
    last = page.locator("#body tr.row").last
    t = last.get_attribute("data-t")
    last.click()
    page.click("[data-testid=rows-more]")                                                    # fold back to 25: the open row remains
    assert page.locator(f"#body tr.row.open[data-t='{t}']").count() == 1 and page.locator("td.detail").count() == 1
    page.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_table_header_stays_at_the_top_while_the_page_scrolls(browser, demo_html, scheme):
    page, errors = open_page(browser, demo_html, 1280, 800, scheme)
    top = lambda: page.evaluate("document.querySelector('#head th').getBoundingClientRect().top")
    assert top() > 300                                                                       # at the top of the page the header is in the table
    assert page.evaluate("getComputedStyle(document.querySelector('#head th')).position") == "sticky"
    assert page.evaluate("document.querySelector('.scroll').classList.contains('hs')") is False   # default columns fit: plain CSS sticky
    page.mouse.wheel(0, 900)
    page.wait_for_function("scrollY > 800")
    assert abs(top()) <= 1
    bg = page.evaluate("getComputedStyle(document.querySelector('#head th')).backgroundColor")
    assert bg not in ("rgba(0, 0, 0, 0)", "transparent")                                    # opaque, so rows do not show through (light and dark)
    page.click("[data-testid=rows-more]")                                                    # a long list: still pinned a long way down
    page.evaluate("scrollTo(0, 2200)")
    assert abs(top()) <= 1
    assert errors == []
    page.close()


def test_sticky_header_keeps_the_sideways_scroll_of_more_columns(browser, demo_html):
    page, errors = open_page(browser, demo_html, 1100, 800)   # narrower than 1280: the wrapping badge keeps the wide table inside the card at 1280
    page.click("#colbtn")
    assert page.evaluate("document.querySelector('.scroll').classList.contains('hs')")      # wider than the card: its own sideways scroller
    sw = page.evaluate("(() => { const s = document.querySelector('.scroll'); return [s.scrollWidth, s.clientWidth]; })()")
    assert sw[0] > sw[1]
    page.evaluate("scrollTo(0, 900)")
    page.wait_for_function("scrollY > 800")
    page.wait_for_function("Math.abs(document.querySelector('#head th').getBoundingClientRect().top) <= 2")
    page.evaluate("document.querySelector('.scroll').scrollLeft = 300")
    assert page.evaluate("document.querySelector('.scroll').scrollLeft") > 0               # still scrolls sideways
    th = page.evaluate("document.querySelector('#head th:nth-child(5)').getBoundingClientRect().top")
    assert abs(th) <= 2
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    page.evaluate("scrollTo(0, document.body.scrollHeight)")                                 # at the very bottom the header does not leave the table
    page.wait_for_timeout(100)
    assert page.evaluate("document.querySelector('#head th').getBoundingClientRect().bottom <= document.querySelector('table').getBoundingClientRect().bottom + 1")
    assert errors == []
    page.close()


@pytest.mark.parametrize("w, h, sel, limit", [(1280, 800, "#body tr.row", 900), (390, 844, "#cards .sc", 1000)])
def test_first_row_sits_near_the_top(browser, demo_html, w, h, sel, limit):
    """FE-1: on the demo page (with its Demo banner) the first row or card starts above the fold; the real page has less above it."""
    page, _ = open_page(browser, demo_html, w, h)
    y = page.evaluate("(sel) => document.querySelector(sel).getBoundingClientRect().top + scrollY", sel)
    assert y < limit, y
    page.close()


def test_desktop_filters_fit_in_two_short_rows(browser, demo_html):
    page, _ = open_page(browser, demo_html, 1280, 800)
    assert page.evaluate("document.getElementById('controls').getBoundingClientRect().height") < 130
    tops = sorted(page.evaluate("[...document.querySelectorAll('#controls > *')].filter(e => e.offsetParent).map(e => e.getBoundingClientRect().top)"))
    rows = 1 + sum(1 for a, b in zip(tops, tops[1:]) if b - a > 20)                          # controls in one row differ by a few px at most
    assert rows <= 2
    page.close()


COUNT = "document.getElementsByTagName('*').length"


def test_only_the_layout_in_use_is_built_and_the_page_stays_small(browser, demo_html):
    """FE-2: 'All stocks' (348 here) used to build a 348-row table and, on a phone, 348 hidden cards or rows. Measured nodes on the demo page,
    dips list / All stocks: desktop 1934 / 10433 before, 1053 / 1055 now; phone 2258 / 10757 before, 647 / 649 now."""
    d, _ = open_page(browser, demo_html, 1280, 800)
    d.click("#show button[data-v=all]")
    assert d.locator("#body tr.row").count() == ROWS_FIRST and d.locator("#cards .sc").count() == 0
    assert d.evaluate(COUNT) < 3000
    d.close()
    p, _ = open_page(browser, demo_html, 390, 844)
    p.click("#ctltoggle")
    p.click("#show button[data-v=all]")
    assert p.locator("#cards .sc").count() == 10 and p.locator("#body tr.row").count() == 0
    assert p.evaluate(COUNT) < 1500
    p.close()


def test_switching_between_phone_and_desktop_width_builds_the_other_layout(browser, demo_html):
    page, errors = open_page(browser, demo_html, 1280, 800)
    assert page.locator("#body tr.row").count() == ROWS_FIRST and page.locator("#cards .sc").count() == 0
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.querySelectorAll('#cards .sc').length === 10")
    assert page.locator("#body tr.row").count() == 0 and page.is_hidden("#rowsmore")
    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_function("document.querySelectorAll('#body tr.row').length === 25")
    assert page.locator("#cards .sc").count() == 0 and errors == []
    page.close()


# ---------- layout at 1024 / 1100 px, wrapped headers, detail row width, small wording (this wave) ----------

@pytest.mark.parametrize("w", [1024, 1100])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_default_table_fits_without_sideways_scroll_and_price_is_not_clipped(browser, demo_html, w, scheme):
    page, errors = open_page(browser, demo_html, w, 900, scheme)
    box = page.evaluate("(() => { const s = document.querySelector('.scroll'); return {sw: s.scrollWidth, cw: s.clientWidth, hs: s.classList.contains('hs')}; })()")
    assert box["sw"] <= box["cw"] and not box["hs"]
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    bad = page.evaluate("""() => [...document.querySelectorAll('#body tr.row')].filter(tr => {
        const p = tr.querySelector('td[data-k=price]'), t = tr.querySelector('td[data-k=t]');
        return p.scrollWidth > p.clientWidth || p.getBoundingClientRect().left < t.getBoundingClientRect().right - 0.5;
      }).map(tr => tr.dataset.t)""")
    assert bad == []
    assert errors == []
    page.close()


def test_pinned_stock_column_is_opaque_and_marked_while_scrolling_sideways(browser, demo_html):
    page, _ = open_page(browser, demo_html, 1024, 900)
    page.click("#colbtn")
    assert page.evaluate("document.querySelector('.scroll').classList.contains('hs')")
    info = page.evaluate("""() => { const c = getComputedStyle(document.querySelector('#body td[data-k=t]'));
      return {bg: c.backgroundColor, shadow: c.boxShadow, pos: c.position}; }""")
    assert info["pos"] == "sticky" and info["shadow"] != "none"
    assert info["bg"].startswith("rgb(") or info["bg"].endswith(", 1)")          # no alpha: values scrolled under it cannot show through
    page.close()


@pytest.mark.parametrize("w", [1024, 1280])
def test_header_cells_stay_narrow_and_tap_targets_are_40px(browser, demo_html, w):
    page, _ = open_page(browser, demo_html, w, 900)
    page.click("#colbtn")
    widths = page.evaluate("[...document.querySelectorAll('#head th')].map(t => [t.textContent, Math.round(t.getBoundingClientRect().width)])")
    assert [n for n, x in widths if x > 130 and n not in ("Stock", "Setup")] == []       # Stock and Setup hold names and badges; every other header stays narrow
    assert dict(widths)["5d beyond market (beta-adj.)"] <= 110
    small = page.evaluate("[...document.querySelectorAll('#head th.sortable')].filter(t => t.getBoundingClientRect().width < 40).map(t => t.textContent)")
    assert small == []
    assert page.evaluate("[...document.querySelectorAll('#body .tkbtn')].every(b => b.getBoundingClientRect().width >= 40 && b.getBoundingClientRect().height >= 40)")
    page.close()


@pytest.mark.parametrize("w", [1024, 1280])
def test_detail_row_is_not_wider_than_the_visible_box_with_more_columns(browser, demo_html, w):
    page, errors = open_page(browser, demo_html, w, 900)
    page.click("#colbtn")
    page.locator("#body tr.row").first.click()
    for left in (0, 250):
        r = page.evaluate("""(left) => { const s = document.querySelector('.scroll'); s.scrollLeft = left;
          const b = s.getBoundingClientRect(), d = document.querySelector('td.detail > .dwrap').getBoundingClientRect();
          return {cw: s.clientWidth, w: d.width, l: d.left - b.left, r: d.right - b.left, scrolls: s.scrollWidth > s.clientWidth}; }""", left)
        assert r["w"] <= r["cw"] + 0.5 and r["l"] >= -0.5 and r["r"] <= r["cw"] + 0.5, r
    assert errors == []
    page.close()


def test_phone_market_tile_line_uses_the_briefs_numbers(browser, demo_html):
    page, errors = open_page(browser, demo_html, 390, 844)
    line = page.locator("[data-testid=tile-market-line]")
    assert line.is_visible()
    txt = line.inner_text()
    exp = page.evaluate("""() => { const f = r => r.x5 != null && window.__dipView(r.t).rank > 0;
      const r5 = DATA.rows.map(r => r.r5).filter(v => v != null).sort((a, b) => a - b), d = DATA.rows.filter(f);
      return {med: r5[Math.floor(r5.length / 2)], far: d.filter(r => r.x5 <= -0.05).length, n: d.length}; }""")
    assert f"{exp['far']} of {exp['n']} dips fell 5+ points more than their index" in txt
    assert txt.startswith("Median stock ") and "(5d)" in txt and f"{abs(exp['med']) * 100:.1f}%" in txt
    assert not any(w in txt.lower() for w in ("buy", "sell", "target"))
    assert page.locator("#brief .idxline").is_hidden()
    assert errors == []
    page.close()
    desk, _ = open_page(browser, demo_html, 1280, 900)
    assert desk.locator("[data-testid=tile-market-line]").is_hidden() and desk.locator("#brief .idxline").is_visible()
    desk.close()


def test_small_wording_changes(browser, demo_html):
    page, _ = open_page(browser, demo_html)
    assert "New since the previous close" in page.inner_text("[data-testid=tile-new]") and "yesterday" not in page.inner_text("[data-testid=tile-new]").lower()
    assert "Dips meeting the check thresholds: dips with a quality score at or above the minimum and net margin above 0." in page.evaluate("document.getElementById('def-q').textContent")
    assert page.inner_text("#tablehint") == "Click a row for details. Click a column to sort. Mini chart: last 90 days, each row scaled to its own low and high."
    assert "parkline" not in page.inner_text("body") + page.evaluate("document.getElementById('defs').textContent")
    page.fill("#q", "no such company")
    assert page.inner_text("#empty").startswith("No stocks match the current filters. Try a smaller minimum drop, a lower minimum quality score, or “Show: All dips”.")
    page.close()
    ph, _ = open_page(browser, demo_html, 390, 844)
    assert ph.inner_text("#tablehint") == "Tap a stock for details. Mini chart: last 90 days, each on its own scale."
    ph.close()


def test_not_market_adjusted_label_shows_in_table_and_detail(browser, demo_html, tmp_path):
    js = ("{ const r = DATA.rows.find(x => x.dip); r.res5 = -0.031; r.res5z = -1.2; r.beta = 3; r.beta_raw = 3.6; r.beta_side = 'cap';"
          " r.beta_se = 0.4; r.mkt_adj = false; r.res_why = null; window.__forced = r.t; }")
    page, errors = open_page(browser, variant_html(tmp_path, demo_html, js))
    t = page.evaluate("window.__forced")
    page.click("#colbtn")
    row = page.locator(f"#body tr.row[data-t='{t}']")
    assert "rough: beta capped or uncertain" in row.inner_text()
    row.click()
    page.click("td.detail button.more")
    detail = page.inner_text("td.detail")
    assert "Beta was capped, floored or uncertain, so this number is rough; compare it with the plain 5d vs index." in detail and "±0.40" in detail
    assert "roughly 5d vs index" not in detail
    assert "rough: beta capped or uncertain" in page.text_content("#def-res")
    assert errors == []
    page.close()
