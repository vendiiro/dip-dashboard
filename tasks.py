#!/usr/bin/env python3
"""One command per check, the same on Linux and Windows (OPS-6). Standard library only.

    python tasks.py install        pip install -r requirements-dev.txt, then Chromium for Playwright
    python tasks.py demo           build the demo dashboard from synthetic data: output/demo.html
    python tasks.py test           unit tests (everything except the browser tests)
    python tasks.py test-browser   browser tests (needs Playwright and Chromium)
    python tasks.py all            the whole test suite
    python tasks.py shots          demo, then screenshots at desktop and phone width, light and dark: output/screens/
    python tasks.py web            regenerate src/template.html from the parts in src/web/
    python tasks.py check          generated-template check + wording scan + path guard + unit tests (--no-tests: guards only)
    python tasks.py hooks          install the pre-commit hooks (once per clone)

The Makefile targets call these, so `make unit` and `python tasks.py test` run the same thing.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def _env() -> dict[str, str]:
    env = dict(os.environ)
    src = str(ROOT / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(*args: str) -> int:
    """Run python with these arguments from the repo folder; return its exit code."""
    cmd = [PY, *args]
    print("$ python " + " ".join(args), flush=True)
    return subprocess.run(cmd, cwd=ROOT, env=_env()).returncode


def install() -> int:
    return run("-m", "pip", "install", "-r", "requirements-dev.txt") or run("-m", "playwright", "install", "chromium")


def demo() -> int:
    # Own digest name: the default (digest.md next to --out) would overwrite the live output/digest.md on Iiro's PC.
    return run("-m", "dipdash", "--demo", "--out", "output/demo.html", "--digest", "output/digest.demo.md")


def test() -> int:
    return run("-m", "pytest", "-q", "--ignore=tests/test_browser.py")


def test_browser() -> int:
    return run("-m", "pytest", "-q", "-rs", "tests/test_browser.py")


def all_tests() -> int:
    return run("-m", "pytest", "-q", "-rs")


def shots() -> int:
    return demo() or run("scripts/screenshots.py", "output/demo.html", "--out", "output/screens")


def web() -> int:
    return run("src/web/assemble.py", "--write")


def template_fresh() -> int:
    """0 if src/template.html matches the parts in src/web/; otherwise say how to fix it."""
    rc = run("src/web/assemble.py")
    if rc:
        print("src/template.html is out of date: run python tasks.py web")
    return rc


def check(no_tests: bool = False) -> int:
    steps = [("generated template", template_fresh),
             ("wording scan", lambda: run("scripts/check_wording.py")),
             ("path guard", lambda: run("scripts/check_wording.py", "--paths"))]
    if not no_tests:
        steps.append(("unit tests", test))
    results = [(name, step()) for name, step in steps]           # run every step, then report
    print()
    for name, rc in results:
        print(f"{'ok    ' if rc == 0 else 'FAILED'} {name}")
    return 0 if all(rc == 0 for _, rc in results) else 1


def hooks() -> int:
    rc = run("-m", "pre_commit", "install")
    if rc:
        print("pre-commit is missing or this is not a git checkout. Run: python tasks.py install")
    return rc


COMMANDS = {"install": install, "demo": demo, "test": test, "test-browser": test_browser, "all": all_tests,
            "shots": shots, "web": web, "check": check, "hooks": hooks}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=list(COMMANDS))
    ap.add_argument("--no-tests", action="store_true", help="check only: run the two guards, skip the unit tests")
    a = ap.parse_args(argv)
    if a.no_tests and a.command != "check":
        ap.error("--no-tests only applies to 'check'")
    return check(a.no_tests) if a.command == "check" else COMMANDS[a.command]()


if __name__ == "__main__":
    sys.exit(main())
