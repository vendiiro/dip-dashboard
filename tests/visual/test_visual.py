"""Pixel-diff checks of named dashboard states against committed baselines (FE-13).

Skipped when Playwright, Chromium or Pillow is missing, off Linux (baselines are Linux Chromium + this container's fonts) or with DIP_VISUAL=0.
DIP_VISUAL=1 forces the compare anywhere. A deliberate design change: `python scripts/screenshots.py --states all --update`, then look at the images.
Failures write NAME.actual.png and NAME.diff.png to output/visual/.
"""

import pytest

pw = pytest.importorskip("playwright.sync_api")

import vrlib  # noqa: E402

_why = vrlib.skip_reason()
if _why and not (vrlib.forced() and not vrlib.pillow_missing()):
    pytest.skip(_why, allow_module_level=True)

SHOTS = vrlib.all_shots()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = vrlib.launch(p)
        except Exception as e:
            pytest.skip(f"no Chromium available: {str(e)[:80]}")
        yield b
        b.close()


@pytest.fixture(scope="module")
def page_html(tmp_path_factory):
    return vrlib.build_fixed_demo(tmp_path_factory.mktemp("visual") / "demo.html")


def test_twelve_shots_are_defined():
    assert len(SHOTS) == 12 and len({s.name for s in SHOTS}) == 12


@pytest.mark.parametrize("shot", SHOTS, ids=[s.name for s in SHOTS])
def test_state_matches_its_baseline(browser, page_html, shot, tmp_path):
    png, errors = vrlib.render(browser, page_html, shot, tmp_path)
    assert [e for e in errors if not e.startswith("dashboard: could not draw")] == []
    verdict, frac = vrlib.check(shot, png)
    assert verdict != "missing", f"no baseline for {shot.name}: run scripts/screenshots.py --states all --update"
    assert verdict == "ok", (f"{shot.name}: {frac:.2%} of pixels changed (limit {vrlib.MAX_CHANGED:.1%}); "
                             f"see {vrlib.OUT / (shot.name + '.diff.png')}")


def test_no_baseline_is_left_without_a_state():
    names = {s.name for s in SHOTS}
    on_disk = {p.stem for p in vrlib.BASELINE.glob("*.png")}
    assert on_disk == names, f"baseline files and defined shots differ: {sorted(on_disk ^ names)}"
