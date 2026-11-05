# Overnight findings, 2026-11-06

## Baseline (before any change, commit f258a31, new .venv with Playwright)

`10 failed, 1014 passed, 1 skipped in 407.79s (0:06:47)`

Failed:
- tests/test_web_build.py::test_template_is_the_assembled_parts (CRLF working file vs LF page; fixed in Task 1)
- tests/test_web_build.py::test_the_placeholder_appears_once_and_the_page_is_one_self_contained_file (CRLF; fixed in Task 1)
- tests/test_guards.py::test_check_fails_early_on_a_stale_template_and_web_fixes_it (CRLF; fixed in Task 1)
- tests/test_browser.py::test_stale_banner_names_the_date_when_prices_are_over_two_weekdays_old
- tests/test_browser.py::test_a_broken_row_is_skipped_and_named_in_a_visible_alert
- tests/test_browser.py::test_a_broken_chart_leaves_the_detail_and_the_table
- tests/test_browser.py::test_a_data_file_that_is_not_valid_javascript_still_shows_a_message
- tests/test_browser.py::test_detail_chart_draws_when_a_stock_has_a_holiday_gap_in_hist
- tests/test_browser.py::test_alerts_empty_state_does_not_inherit_the_generic_empty_rule
- tests/test_browser.py::test_alerts_more_hover_does_not_take_the_more_context_button_style

The 7 test_browser.py failures share one error: `OSError: [Errno 22] Invalid argument: '\\C:\\Users\\K..ytt..j..\\...\\demo.html'`
(a Windows path with non-ASCII characters turned into a bad path inside the tests). Pre-existing, not a line-ending issue, not fixed.

Skipped:
- tests/visual/test_visual.py (whole module, 1 skip): baselines were made on Linux, this is Windows. Baselines not regenerated.
