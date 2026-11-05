"""Decision log: one file per decision in docs/decisions/, and docs/decisions.md as a generated topic index (OPS-10).

Rebuild the index after adding a decision file:  python tests/test_decisions_index.py --write
The tests check that the index is current, that every decision file is linked exactly once, and that the 54 entries and
6 review bullets of the old single-file log (split on 2026-11-04) are all present, each exactly once, with the text unchanged.
Stdlib only, so the index can be rebuilt without pytest.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "docs" / "decisions"
INDEX = ROOT / "docs" / "decisions.md"

TOPICS = {"data": "Data", "screen": "Screen", "backtest": "Backtest", "dashboard": "Dashboard",
          "alerts": "Alerts", "ops": "Ops", "docs": "Docs"}
NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d{2})-([a-z]+)-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")

# The old single-file log as it stood before the split (203 lines, sha256 of its exact bytes).
OLD_HEADER = "# Decisions log\n\nRecord each decision with date, options considered, choice and reason. Claude: append here.\n\n"
OLD_HEADING = "\n## 2026-11-04: review follow-ups (alerts, forecast, experiment)\n"
OLD_SHA256 = "b27f7efe96165a12abdec18e05fbdbe59e6e7de12217f2836c4cfd34542fccc5"
OLD_ENTRIES, OLD_BULLETS = 54, 6
ENTRY_RE = re.compile(r"^migrated, old entry (\d+) of 54 \(text verbatim\)$")
BULLET_RE = re.compile(r"^migrated, review bullets (\d+)(?:-(\d+))? of 6 \(text verbatim\)$")


def parse(path: Path) -> dict:
    """Split a decision file into title, metadata and body (the text after the first '---' line)."""
    text = path.read_text(encoding="utf-8")
    head, sep, body = text.partition("\n---\n\n")
    assert sep, f"{path.name}: needs a '---' line followed by a blank line before the decision text"
    lines = head.split("\n")
    assert lines[0].startswith("# ") and lines[0][2:].strip(), f"{path.name}: first line must be '# <title>'"
    meta = {}
    for ln in lines[1:]:
        m = re.match(r"^- (Date|Topic|Origin): (.+)$", ln)
        if m:
            meta[m.group(1)] = m.group(2)
    return {"name": path.name, "title": lines[0][2:].strip(), "meta": meta, "body": body}


def decisions() -> list[dict]:
    return [parse(p) for p in sorted(DIR.glob("*.md"))]


def build_index(items: list[dict] | None = None) -> str:
    items = decisions() if items is None else items
    by_topic: dict[str, list[dict]] = {t: [] for t in TOPICS}
    for d in items:
        by_topic.setdefault(d["meta"].get("Topic", "?"), []).append(d)
    out = [
        "# Decisions log",
        "",
        "Generated file, do not edit by hand. Each decision is its own file in `docs/decisions/`; this page is the topic index,",
        f"oldest first in each table ({len(items)} decisions). Source files cite this path, so it must keep existing.",
        "",
        "## How to add a decision",
        "1. Add a new file `docs/decisions/YYYY-MM-DD-NN-<topic>-<slug>.md`: NN is the next free number for that date, topic is one of",
        "   " + ", ".join(TOPICS) + ". Never rewrite an old decision; add a new file and say which one it replaces.",
        "2. Layout: `# <one-line title>`, then the lines `- Date:`, `- Topic:`, `- Origin:` (backlog id or who decided), a `---` line,",
        "   a blank line, then the decision text (date, options considered, choice and reason).",
        "3. Rebuild this index: `python tests/test_decisions_index.py --write`. `pytest tests/test_decisions_index.py` fails while it is out of date.",
        "",
        "Topics: " + " · ".join(f"[{TOPICS.get(t, t)}](#{t}) ({len(v)})" for t, v in by_topic.items() if v),
    ]
    for t, rows in by_topic.items():
        if not rows:
            continue
        out += ["", f"## {TOPICS.get(t, t)}", "", "| Date | Decision |", "|---|---|"]
        for d in rows:
            title = d["title"].replace("|", "\\|")
            out.append(f"| {d['meta'].get('Date', '?')} | [{title}](decisions/{d['name']}) |")
    return "\n".join(out) + "\n"


def migrated(items: list[dict]) -> tuple[dict[int, dict], dict[int, dict]]:
    """Old entries keyed by entry number, and review-bullet groups keyed by their first bullet number."""
    entries, bullets = {}, {}
    for d in items:
        origin = d["meta"].get("Origin", "")
        if m := ENTRY_RE.match(origin):
            assert int(m.group(1)) not in entries, f"old entry {m.group(1)} is migrated twice"
            entries[int(m.group(1))] = d
        elif m := BULLET_RE.match(origin):
            a = int(m.group(1))
            d["bullets"] = range(a, int(m.group(2) or a) + 1)
            bullets[a] = d
    return entries, bullets


# ---------------------------------------------------------------- tests

def test_file_names_and_headers_are_valid():
    items = decisions()
    assert items, "docs/decisions/ is empty"
    for d in items:
        m = NAME_RE.match(d["name"])
        assert m, f"{d['name']}: name must be YYYY-MM-DD-NN-<topic>-<slug>.md (lowercase, hyphens)"
        date, _, topic, _ = m.groups()
        assert topic in TOPICS, f"{d['name']}: topic {topic!r} not in {sorted(TOPICS)}"
        assert d["meta"].get("Date") == date, f"{d['name']}: '- Date:' must equal the date in the file name"
        assert d["meta"].get("Topic") == topic, f"{d['name']}: '- Topic:' must equal the topic in the file name"
        assert d["meta"].get("Origin"), f"{d['name']}: add an '- Origin:' line"
        assert d["body"].strip(), f"{d['name']}: decision text is empty"


def test_index_is_generated_and_current():
    assert INDEX.read_text(encoding="utf-8") == build_index(), \
        "docs/decisions.md is out of date or edited by hand: run python tests/test_decisions_index.py --write"


def test_every_decision_file_is_linked_exactly_once():
    links = re.findall(r"\]\(decisions/([^)]+)\)", INDEX.read_text(encoding="utf-8"))
    names = [d["name"] for d in decisions()]
    assert sorted(links) == sorted(names), "index links and files in docs/decisions/ differ"
    assert len(links) == len(set(links)), "a decision is linked twice"


def test_old_log_is_rebuilt_exactly_from_the_migrated_files():
    entries, bullets = migrated(decisions())
    assert sorted(entries) == list(range(1, OLD_ENTRIES + 1)), "every old entry 1..54 must be migrated exactly once"
    covered = sorted(i for d in bullets.values() for i in d["bullets"])
    assert covered == list(range(1, OLD_BULLETS + 1)), "the 6 review bullets must each be in exactly one file"
    for n, d in entries.items():
        lines = d["body"].splitlines()
        assert lines[0].startswith("- " + d["meta"]["Date"]), f"{d['name']}: old entry {n} must start with its date"
        assert sum(ln.startswith("- 20") for ln in lines) == 1, f"{d['name']}: holds more than one old entry"
    for d in bullets.values():
        lines = d["body"].splitlines()
        assert len(lines) == len(d["bullets"]) and all(ln.startswith("- ") for ln in lines), d["name"]
    old = (OLD_HEADER + "".join(entries[n]["body"] for n in sorted(entries)) + OLD_HEADING
           + "".join(bullets[a]["body"] for a in sorted(bullets)))
    assert hashlib.sha256(old.encode("utf-8")).hexdigest() == OLD_SHA256, \
        "the migrated text no longer joins back into the old log byte for byte: an old entry was edited, dropped or reordered"


def test_each_old_entry_appears_exactly_once_across_all_decisions():
    items = decisions()
    entries, bullets = migrated(items)
    everything = "".join(d["body"] for d in items)
    pieces = [d["body"] for d in entries.values()] + [ln + "\n" for d in bullets.values() for ln in d["body"].splitlines()]
    assert len(pieces) == OLD_ENTRIES + OLD_BULLETS
    twice = [p.splitlines()[0][:70] for p in pieces if everything.count(p) != 1]
    assert not twice, f"old text found more than once: {twice}"


def test_cited_path_still_exists():
    cited = [p for p in (ROOT / "src").rglob("*.py") if "docs/decisions.md" in p.read_text(encoding="utf-8")]
    assert cited, "expected source files to cite docs/decisions.md"
    assert INDEX.is_file()


if __name__ == "__main__":
    if sys.argv[1:] == ["--write"]:
        INDEX.write_text(build_index(), encoding="utf-8", newline="\n")
        print(f"wrote {INDEX.relative_to(ROOT)} ({len(decisions())} decisions)")
    else:
        print("usage: python tests/test_decisions_index.py --write")
