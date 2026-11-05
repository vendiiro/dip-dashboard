"""Visual-regression helpers (FE-13): a fixed demo page, named UI states, deterministic rendering and a pixel diff.

Used by tests/visual/test_visual.py and by `python scripts/screenshots.py --states all --compare tests/visual/baseline`.
Baselines are made in the Linux build container (Chromium + its system fonts). Other machines skip the compare (see `skip_reason`).
Pillow is needed to decode PNGs; numpy does the arithmetic.
"""
from __future__ import annotations

import io
import json
import os
import platform
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).resolve().parent / "baseline"
OUT = ROOT / "output" / "visual"

TODAY = date(2026, 11, 5)                          # the day the fixed page pretends to be built on
CLOCK = datetime(2026, 11, 5, 10, 0, 0)            # the browser clock for every state except "stale"
GENERATED = "2026-11-05 07:23"                     # `DATA.generated` is wall-clock time; pin it
TOLERANCE = 8                                      # per channel, out of 255: below this a pixel counts as unchanged
MAX_CHANGED = 0.001                                # fail when more than 0.1% of the pixels changed
SIZES = {"desktop": (1280, 900), "phone": (390, 844)}
CHROMIUM_ARGS = ["--font-render-hinting=none", "--force-color-profile=srgb", "--disable-lcd-text"]

BROKEN_ROW = "{ const r = DATA.rows.find(x => x.dip); r.spark = null; }"       # same fault the FE-4 browser test plants
STALE = "DATA.demo = false;"


@dataclass(frozen=True)
class Shot:
    state: str
    size: str          # key of SIZES
    scheme: str        # light | dark

    @property
    def name(self) -> str:
        return f"{self.state}-{self.size}-{self.scheme}"


@dataclass(frozen=True)
class State:
    js: str = ""                       # appended to the page right after `const DATA = ...;`
    clock: datetime = CLOCK
    actions: str = ""                  # key into ACTIONS
    shots: tuple[tuple[str, str], ...] = ()


ALL4 = tuple((s, c) for s in SIZES for c in ("light", "dark"))
# 12 shots: default and detail in all four combinations, the other four states once each (the plan's option c).
# The "print" state of the plan is left out: the template has no print stylesheet yet, so it would repeat "default".
STATES: dict[str, State] = {
    "default": State(shots=ALL4),
    "detail": State(actions="detail", shots=ALL4),
    "filters": State(actions="filters", shots=(("desktop", "light"),)),       # window 1 day, min drop 3, Nordic
    "empty": State(actions="empty", shots=(("phone", "light"),)),             # search "zzzz" on the phone cards
    "stale": State(js=STALE, clock=datetime(2026, 11, 11, 10, 0, 0), shots=(("desktop", "light"),)),   # FE-3 banner
    "failure": State(js=BROKEN_ROW, shots=(("desktop", "light"),)),           # FE-4 broken row named in the alert
}


def all_shots(only: list[str] | None = None) -> list[Shot]:
    return [Shot(n, sz, sc) for n, s in STATES.items() if not only or n in only for sz, sc in s.shots]


# ---------------------------------------------------------------- the fixed page
def build_fixed_demo(out: Path) -> Path:
    """The demo page for the current template, made as if today were TODAY, so it is the same on any day."""
    import dipdash.cli as cli
    import dipdash.demo as demo
    import pandas as pd

    class FixedDate(date):
        @classmethod
        def today(cls):
            return TODAY

    old = (cli.date, demo._last_close)
    cli.date = FixedDate
    demo._last_close = lambda: pd.Timestamp(TODAY) - pd.offsets.BDay(1)
    try:
        if cli.main(["--demo", "--no-crosscheck", "--out", str(out)]) != 0:
            raise RuntimeError("demo build failed")
    finally:
        cli.date, demo._last_close = old
    return out


def with_js(html_path: Path, js: str, out: Path) -> Path:
    """A copy of the page with `js` run right after the data line (always pins `DATA.generated`)."""
    html = html_path.read_text(encoding="utf-8")
    i = html.index("const DATA = ")
    j = html.index("\n", i)
    out.write_text(html[:j + 1] + f"DATA.generated = '{GENERATED}'; " + js + "\n" + html[j + 1:], encoding="utf-8")
    return out


# ---------------------------------------------------------------- rendering
def _quiet(page) -> None:
    page.mouse.move(0, 0)
    page.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
    page.wait_for_timeout(150)


def _detail(page, size):
    page.click("#body tr.row" if size == "desktop" else "#cards .schead")   # first row, or first card
    page.wait_for_selector("td.detail, #cards .sc.open")


def _filters(page, size):
    page.select_option("#win", "r1")
    page.fill("#drop", "3")
    page.dispatch_event("#drop", "input")
    page.click("#region button[data-v=Nordic]")


def _empty(page, size):
    if size == "phone":
        page.click("#ctltoggle")
    page.fill("#q", "zzzz")
    page.wait_for_selector("#empty:not([hidden])")


ACTIONS = {"": lambda p, s: None, "detail": _detail, "filters": _filters, "empty": _empty}


def launch(pw):
    return pw.chromium.launch(executable_path=os.environ.get("DIP_CHROMIUM") or None, args=CHROMIUM_ARGS)


def render(browser, html_path: Path, shot: Shot, workdir: Path) -> tuple[bytes, list[str]]:
    """PNG bytes of one shot plus its console errors. Fonts are stubbed, so the page uses the system fonts of the machine."""
    st = STATES[shot.state]
    url = with_js(html_path, st.js, workdir / f"{shot.state}.html").as_uri()
    w, h = SIZES[shot.size]
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, color_scheme=shot.scheme,
                              reduced_motion="reduce", locale="en-GB", timezone_id="Europe/Helsinki")
    try:
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and "font" not in m.text.lower() and errors.append(m.text))
        page.route("**/fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        page.route("**/fonts.gstatic.com/**", lambda r: r.fulfill(status=200, content_type="font/woff2", body=b""))
        page.clock.set_fixed_time(st.clock)
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("#tiles .tile")
        page.evaluate("document.fonts.ready")
        ACTIONS[st.actions](page, shot.size)
        _quiet(page)
        return page.screenshot(full_page=True, animations="disabled", caret="hide"), errors
    finally:
        ctx.close()


# ---------------------------------------------------------------- the pixel diff
def _pil():
    import PIL.Image as image
    return image


def pillow_missing() -> bool:
    try:
        _pil()
        return False
    except ImportError:
        return True


def skip_reason() -> str | None:
    """Why the compare should not run here, or None. Baselines come from Linux Chromium with this container's fonts."""
    if os.environ.get("DIP_VISUAL") == "0":
        return "DIP_VISUAL=0"
    if platform.system() != "Linux":
        return f"baselines were made on Linux, this is {platform.system()}; use DIP_VISUAL=1 to force or --update to remake them"
    if pillow_missing():
        return "Pillow is not installed (pip install pillow; test-engineer adds it to requirements-dev.txt)"
    return None


def forced() -> bool:
    return os.environ.get("DIP_VISUAL") == "1"


def compare_png(actual: bytes, baseline: bytes) -> tuple[float, "object | None"]:
    """(fraction of pixels changed, boolean mask or None). A different size counts as everything changed."""
    import numpy as np
    img = _pil()
    a = np.asarray(img.open(io.BytesIO(actual)).convert("RGB"), dtype=np.int16)
    b = np.asarray(img.open(io.BytesIO(baseline)).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        return 1.0, None
    mask = np.abs(a - b).max(axis=2) > TOLERANCE
    return float(mask.mean()), mask


def write_diff(actual: bytes, mask, path: Path) -> None:
    """The actual image dimmed, changed pixels in magenta."""
    import numpy as np
    img = _pil()
    a = np.asarray(img.open(io.BytesIO(actual)).convert("RGB")).copy()
    a = (a * 0.35 + 255 * 0.65).astype("uint8") if mask is not None else a
    if mask is not None:
        a[mask] = (255, 0, 200)
    img.fromarray(a).save(path)


def save_png(data: bytes, path: Path) -> None:
    img = _pil()
    img.open(io.BytesIO(data)).convert("RGB").save(path, optimize=True)


def chromium_version(browser) -> str:
    return browser.version


def check(shot: Shot, actual: bytes, baseline_dir: Path = BASELINE, out_dir: Path = OUT) -> tuple[str, float]:
    """('ok' | 'missing' | 'changed', fraction). On 'changed' the actual and diff images go to out_dir."""
    base = baseline_dir / f"{shot.name}.png"
    if not base.exists():
        return "missing", 1.0
    frac, mask = compare_png(actual, base.read_bytes())
    if frac <= MAX_CHANGED:
        return "ok", frac
    out_dir.mkdir(parents=True, exist_ok=True)
    save_png(actual, out_dir / f"{shot.name}.actual.png")
    write_diff(actual, mask, out_dir / f"{shot.name}.diff.png")
    return "changed", frac


def update_baselines(shots: list[Shot], rendered: dict[str, bytes], browser_version: str, baseline_dir: Path = BASELINE) -> None:
    baseline_dir.mkdir(parents=True, exist_ok=True)
    for s in shots:
        save_png(rendered[s.name], baseline_dir / f"{s.name}.png")
    (baseline_dir / "meta.json").write_text(json.dumps({
        "platform": platform.platform(), "chromium": browser_version, "fixed_today": TODAY.isoformat(),
        "tolerance_per_channel": TOLERANCE, "max_changed_fraction": MAX_CHANGED, "fonts": "system fonts, Google Fonts stubbed",
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":                                           # pragma: no cover
    sys.exit("use scripts/screenshots.py --states all")
