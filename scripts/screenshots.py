#!/usr/bin/env python3
"""Render a dashboard HTML file at desktop and phone width, light and dark, and check it (Rule 2 in CLAUDE.md).

    python scripts/screenshots.py output/dashboard.html --out output/screens

Writes four PNGs, prints console errors and horizontal overflow, and exits 1 if either is found.
Setup once on Windows: pip install playwright && playwright install chromium
Set DIP_CHROMIUM=/path/to/chrome to use a browser you already have (the cloud build container does).
"""
import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWPORTS = {"desktop": (1280, 900), "phone": (390, 844)}
SCHEMES = ("light", "dark")
# The web-font stylesheet is optional; a blocked or slow font host is not a page error.
IGNORE = ("fonts.googleapis.com", "fonts.gstatic.com", "ERR_BLOCKED", "ERR_NAME_NOT_RESOLVED", "ERR_CONNECTION", "ERR_TUNNEL")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html")
    ap.add_argument("--out", default="output/screens")
    ap.add_argument("--tag", default="", help="prefix for the PNG names, e.g. demo or live")
    ap.add_argument("--click", default="", help="CSS selector to click before the screenshot")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    url = Path(a.html).resolve().as_uri()
    bad = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("DIP_CHROMIUM") or None)
        for vp, (w, h) in VIEWPORTS.items():
            for scheme in SCHEMES:
                page = browser.new_page(viewport={"width": w, "height": h}, color_scheme=scheme)
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("console", lambda m: m.type == "error" and errors.append(m.text))
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector("#sumrow .stat", timeout=15000)
                try:
                    page.evaluate("document.fonts.ready", )
                except Exception:
                    pass
                page.wait_for_timeout(300)
                if a.click:
                    page.click(a.click)
                    page.wait_for_timeout(200)
                overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                name = out / f"{a.tag + '-' if a.tag else ''}{vp}-{scheme}.png"
                page.screenshot(path=str(name), full_page=True)
                errors = [e for e in errors if not any(i in e for i in IGNORE)]
                status = "ok" if not errors and overflow <= 0 else "PROBLEM"
                bad += status != "ok"
                print(f"{vp:7s} {scheme:5s} overflow={overflow:>4} console_errors={len(errors)} -> {name} [{status}]")
                for e in errors:
                    print("   ", e[:200])
                page.close()
        browser.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
