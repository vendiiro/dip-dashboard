"""src/template.html is generated from the parts in src/web/ (python src/web/assemble.py --write). Standard library only."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "web"
TEMPLATE = ROOT / "src" / "template.html"

_spec = importlib.util.spec_from_file_location("web_assemble", WEB / "assemble.py")
assemble = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(assemble)

PARTS = sorted(p.name for p in WEB.iterdir() if p.suffix in {".css", ".js", ".html"})


def test_template_is_the_assembled_parts():
    assert assemble._lf(TEMPLATE.read_bytes().decode("utf-8")) == assemble.assemble(), \
        "src/template.html is out of date: edit the parts in src/web/, then run python src/web/assemble.py --write"


def test_every_part_is_in_the_manifest_exactly_once():
    listed = [name for _, name in assemble.read_manifest()]
    assert sorted(listed) == PARTS, (
        f"in the manifest but missing on disk: {sorted(set(listed) - set(PARTS))}; "
        f"on disk but not in the manifest: {sorted(set(PARTS) - set(listed))}; duplicates: "
        f"{sorted({n for n in listed if listed.count(n) > 1})}")


def test_the_placeholder_appears_once_and_the_page_is_one_self_contained_file():
    page = assemble.assemble()
    assert page.count("__DATA__") == 1
    assert page.count("<style>") == 1 and page.count("</style>") == 1
    assert page.count("<script>") == 2 and page.count("</script>") == 2
    assert not re.search(r"<script[^>]+src=|<link[^>]+href=\"(?!https://fonts\.)|@import", page)
    assert page.startswith("<!doctype html>\n") and page.endswith("</html>\n")


def test_dark_tokens_are_defined_once():
    tokens = (WEB / "tokens.css").read_text(encoding="utf-8")
    assert tokens.count("--bg:") == 2          # light and dark, nothing else


def test_a_bad_manifest_is_reported(tmp_path):
    (tmp_path / "m.txt").write_text("css a.css\nbogus b.css\n", encoding="utf-8")
    with pytest.raises(ValueError, match="m.txt:2"):
        assemble.read_manifest(tmp_path / "m.txt")


def test_a_missing_role_is_reported(tmp_path):
    (tmp_path / "m.txt").write_text("head h.html\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no 'css' part"):
        assemble.assemble(tmp_path, tmp_path / "m.txt")
