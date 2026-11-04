"""Shared pytest hooks.

DIP_REQUIRE_BROWSER=1 (set in CI): a skipped browser test is a failure, so a runner
without Playwright or Chromium cannot show a false green.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

_REQUIRE = os.environ.get("DIP_REQUIRE_BROWSER") == "1"


def pytest_configure(config: pytest.Config) -> None:
    if _REQUIRE and importlib.util.find_spec("playwright") is None:
        raise pytest.UsageError("DIP_REQUIRE_BROWSER=1 but the playwright package is not installed")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    rep = outcome.get_result()
    if _REQUIRE and rep.skipped and "test_browser" in item.nodeid:
        reason = rep.longrepr[2] if isinstance(rep.longrepr, tuple) else str(rep.longrepr)
        rep.outcome = "failed"
        rep.longrepr = f"browser test skipped while DIP_REQUIRE_BROWSER=1: {reason}"
