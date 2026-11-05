#!/usr/bin/env python3
"""Two pre-commit guards, also run by `python tasks.py check` and CI (OPS-6, OPS-7).

    python scripts/check_wording.py                 # wording scan over every in-scope file
    python scripts/check_wording.py FILE ...        # wording scan over these files (out-of-scope ones are ignored)
    python scripts/check_wording.py --paths         # path guard over the files git tracks
    python scripts/check_wording.py --paths FILE ...  # path guard over these names (pre-commit passes the staged files)

Wording scan: advice phrases in source files a reader sees (src/, config/, scripts/*.ps1|bat|cmd, README.md,
START_HERE.md). tests/, docs/, .claude/ and CLAUDE.md quote the phrases as examples on purpose and are not scanned.
Generated text (digest, alerts) is checked by tests/test_alerts.py and tests/test_digest.py instead.
Path guard: data/, output/, .env and .env.* (except .env.example) must never be committed, even with `git add -f`.
Exit code 1 and one `file:line: reason` line per finding. Standard library only.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The phrases are split so this file does not match itself.
_PHRASES = [
    r"\b" + "bu" + r"y\s+now\b",
    r"\b" + "se" + r"lls?\b(?![- ]off)",             # "sell-off" describes a market, it is not advice
    r"(?<!not a )\b" + "price" + r"\s+tar" + r"gets?\b",   # "not a price target" is the disclaimer itself
    r"\bwill\s+" + "reco" + r"ver\b",
    r"\b" + "guaran" + r"tee(s|d)?\b",
    r"\bshould\s+(" + "bu" + "y|se" + "ll|ho" + r"ld)\b",
    r"\b" + "under" + r"valued\b",
    r"\b" + "bar" + r"gains?\b",
    r"\bwill\s+(" + "ri" + "se|re" + "bound|bou" + "nce|go\\s+" + r"up)\b",
    r"\b" + "expected" + r"\s+returns?\b",
    r"\b" + "strong" + r"\s+" + "bu" + r"y\b",
    r"\b" + "top" + r"\s+" + "pi" + r"cks?\b",
]
BANNED = re.compile("|".join(_PHRASES), re.I)

SCOPE_DIRS = ("src/", "config/")
SCOPE_FILES = ("README.md", "START_HERE.md")
SCOPE_SCRIPT_SUFFIXES = (".ps1", ".bat", ".cmd")
SKIP_PARTS = {"__pycache__", ".pytest_cache", "node_modules"}
TEXT_SUFFIXES = {".py", ".html", ".htm", ".js", ".mjs", ".css", ".toml", ".csv", ".md", ".txt", ".json",
                 ".ps1", ".bat", ".cmd", ".yaml", ".yml", ".svg", ".ini"}

FORBIDDEN_DIRS = ("data/", "output/")


def _rel(path: str | Path, root: Path) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.relative_to(root)
        except ValueError:
            pass
    return p.as_posix()                                 # also turns Windows backslashes into '/'


def in_scope(rel: str) -> bool:
    """True for a repo-relative POSIX path that the wording scan reads."""
    if SKIP_PARTS.intersection(rel.split("/")):
        return False
    suffix = Path(rel).suffix.lower()
    if rel in SCOPE_FILES:
        return True
    if rel.startswith(SCOPE_DIRS):
        return suffix in TEXT_SUFFIXES
    return rel.startswith("scripts/") and rel.count("/") == 1 and suffix in SCOPE_SCRIPT_SUFFIXES


def scan_text(text: str) -> list[tuple[int, str]]:
    """(line number, matched phrase) for every banned phrase in the text."""
    return [(n, m.group(0)) for n, line in enumerate(text.splitlines(), 1) for m in BANNED.finditer(line)]


def wording_findings(files: list[str] | None, root: Path = ROOT) -> list[str]:
    if files is None:
        rels = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    else:
        rels = [_rel(f, root) for f in files]
    out = []
    for rel in rels:
        path = root / rel
        if not in_scope(rel) or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        out += [f"{rel}:{n}: advice phrase '{phrase}' (use 'screen results', 'candidates', 'flagged because ...')"
                for n, phrase in scan_text(text)]
    return out


def forbidden(rel: str) -> str | None:
    """Why this repo-relative path must not be committed, or None if it is fine."""
    if rel.startswith(FORBIDDEN_DIRS):
        return f"{rel.split('/')[0]}/ holds local runs and cached pulls; it is never committed"
    name = rel.rsplit("/", 1)[-1]
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return "API keys live in .env, which is never committed (.env.example is fine)"
    return None


def tracked_files(root: Path = ROOT) -> list[str] | None:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return [f for f in out.splitlines() if f]


def path_findings(files: list[str], root: Path = ROOT) -> list[str]:
    return [f"{rel}: {why}" for rel in (_rel(f, root) for f in files) if (why := forbidden(rel))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--paths", action="store_true", help="run the path guard instead of the wording scan")
    ap.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    root = a.root.resolve()
    if a.paths:
        files = a.files or tracked_files(root)
        if files is None:
            print("path guard: not a git checkout, nothing to check")
            return 0
        problems = path_findings(files, root)
        label = "path guard"
    else:
        problems = wording_findings(a.files or None, root)
        label = "wording scan"
    for p in problems:
        print(p)
    print(f"{label}: {len(problems)} problem(s)" if problems else f"{label}: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
