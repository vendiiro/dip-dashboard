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
    if _REQUIRE and rep.skipped and _must_not_skip(item.nodeid, _reason(rep)):
        rep.outcome = "failed"
        rep.longrepr = f"browser test skipped while DIP_REQUIRE_BROWSER=1: {_reason(rep)}"


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector: pytest.Collector):
    """A module-level skip (missing Pillow, off-Linux, DIP_VISUAL=0) is a collection report, not a test report."""
    outcome = yield
    rep = outcome.get_result()
    if _REQUIRE and rep.skipped and _must_not_skip(str(getattr(collector, "nodeid", "")), _reason(rep)):
        rep.outcome = "failed"
        rep.longrepr = f"visual tests skipped while DIP_REQUIRE_BROWSER=1: {_reason(rep)}"


# Documented legitimate skips of tests/visual (see its docstring): another OS, or DIP_VISUAL=0.
_ALLOWED_VISUAL = ("DIP_VISUAL=0", "baselines were made on Linux")


def _reason(rep) -> str:
    lr = rep.longrepr
    return lr[2] if isinstance(lr, tuple) else str(lr)


def _must_not_skip(nodeid: str, reason: str) -> bool:
    if "test_browser" in nodeid:
        return True
    if "tests/visual" in nodeid.replace("\\", "/"):
        return not any(a in reason for a in _ALLOWED_VISUAL)
    return False
