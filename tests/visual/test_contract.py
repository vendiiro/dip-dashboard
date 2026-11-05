"""docs/frontend-contract.md and the page agree (FE-13). No browser needed.

Forward: every hook in the contract exists in src/template.html (or docs/payload.md for DATA fields).
Reverse: every #id, data-testid and data-* attribute used by the browser tests, the visual helpers or screenshots.py is in the contract.
"""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (ROOT / "docs" / "frontend-contract.md").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
PAYLOAD = (ROOT / "docs" / "payload.md").read_text(encoding="utf-8")
USERS = [ROOT / "tests" / "test_browser.py", ROOT / "tests" / "visual" / "vrlib.py", ROOT / "tests" / "visual" / "test_visual.py",
         ROOT / "scripts" / "screenshots.py"]
TEST_ONLY_IDS = {"probe"}                          # element the test itself adds to the page


def listed() -> set[tuple[str, str]]:
    return set(re.findall(r"^\| `(id|testid|attr|class|window|data):([^`]+)`", CONTRACT, flags=re.M))


def exists_in_template(kind: str, name: str) -> bool:
    q = re.escape(name)
    if kind == "id":
        return bool(re.search(rf"""id=["']{q}["']|\.id\s*=\s*["']{q}["']|\$\(["']{q}["']\)""", TEMPLATE))
    if kind == "testid":
        return bool(re.search(rf"""data-testid=["']?{q}(?![\w-])|testid\s*=\s*["']{q}["']|\(["']{q}["']""", TEMPLATE))
    if kind == "attr":
        key = name.removeprefix("data-")
        return f"data-{key}" in TEMPLATE or f"dataset.{key}" in TEMPLATE
    if kind == "class":
        return bool(re.search(rf"""\.{q}(?![\w-])|["'\s]{q}["'\s]""", TEMPLATE))
    if kind == "window":
        return f"window.{name}" in TEMPLATE
    if kind == "data":
        return bool(re.search(rf"(?<![\w-]){q}(?![\w-])", PAYLOAD))
    raise AssertionError(kind)


def used_by_tests() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for f in USERS:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            s = node.value
            for m in re.findall(r"(?<![\w&])#([A-Za-z][\w-]*)", s):
                if not re.fullmatch(r"[0-9a-fA-F]{3,8}", m):             # a colour, not an id
                    found.add(("id", m))
            found |= {("id", m) for m in re.findall(r"getElementById\(['\"]([\w-]+)['\"]\)", s)}
            found |= {("testid", m) for m in re.findall(r"data-testid=['\"]?([\w-]+)", s)}
            found |= {("attr", "data-" + m) for m in re.findall(r"data-([a-z]+)\s*(?:=|\])", s)}
            found |= {("attr", "data-" + m) for m in re.findall(r"\[data-([a-z]+)", s)}
    return {h for h in found if not (h[0] == "id" and h[1] in TEST_ONLY_IDS)}


def test_contract_lists_hooks():
    assert len(listed()) > 50


@pytest.mark.parametrize("kind, name", sorted(listed()))
def test_listed_hook_exists(kind, name):
    assert exists_in_template(kind, name), f"{kind}:{name} is in docs/frontend-contract.md but not in {'docs/payload.md' if kind == 'data' else 'src/template.html'}"


def test_every_hook_the_tests_use_is_listed():
    missing = sorted(used_by_tests() - listed())
    assert not missing, f"used by tests or scripts but not in docs/frontend-contract.md: {missing}"


def test_the_checker_can_fail():
    assert not exists_in_template("id", "no-such-hook-xyz") and not exists_in_template("testid", "no-such-hook-xyz")
    assert ("id", "body") in used_by_tests() and ("testid", "stale") in used_by_tests()
