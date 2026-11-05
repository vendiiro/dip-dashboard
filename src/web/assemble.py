#!/usr/bin/env python3
"""Assemble the dashboard page from the parts in src/web/ into the one self-contained src/template.html.

    python src/web/assemble.py            print nothing, exit 1 if src/template.html is out of date
    python src/web/assemble.py --write    regenerate src/template.html from the parts

The order of the parts is src/web/manifest.txt. The page stays one file: CSS and JavaScript are inlined, and the single
`__DATA__` placeholder (in data.js) is filled in later by dipdash.dashboard.render_html. Standard library only.
"""
from __future__ import annotations

import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent
TEMPLATE = WEB.parent / "template.html"
MANIFEST = WEB / "manifest.txt"
ROLES = ("head", "css", "body", "data", "js", "fallback")


def read_manifest(manifest: Path = MANIFEST) -> list[tuple[str, str]]:
    """The (role, file name) pairs in build order."""
    entries: list[tuple[str, str]] = []
    for n, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        role, _, name = line.partition(" ")
        if role not in ROLES or not name.strip():
            raise ValueError(f"{manifest.name}:{n}: expected '<{'|'.join(ROLES)}> <file>', got {line!r}")
        entries.append((role, name.strip()))
    return entries


def _lf(text: str) -> str:
    """Line endings as LF: a Windows checkout (core.autocrlf) stores CRLF, the page is always LF."""
    return text.replace("\r\n", "\n")


def _text(web: Path, name: str) -> str:
    # bytes, not text mode (no newline translation on Windows), then CRLF -> LF so the page is the same on every OS
    return _lf((web / name).read_bytes().decode("utf-8"))


def assemble(web: Path = WEB, manifest: Path | None = None) -> str:
    """The full page text, parts joined in manifest order inside fixed wrapper tags."""
    entries = read_manifest(manifest or web / "manifest.txt")
    by_role = {r: [n for rr, n in entries if rr == r] for r in ROLES}
    for role in ROLES:
        if not by_role[role]:
            raise ValueError(f"manifest has no '{role}' part")
    for role in ("head", "body", "data", "fallback"):
        if len(by_role[role]) != 1:
            raise ValueError(f"manifest needs exactly one '{role}' part, has {len(by_role[role])}")
    t = lambda role: "".join(_text(web, n) for n in by_role[role])  # noqa: E731
    return (t("head") + "<style>\n" + t("css") + "</style>\n</head>\n" + t("body")
            + "<script>\n" + t("data") + t("js") + "</script>\n"
            + "<script>\n" + t("fallback") + "</script>\n</body>\n</html>\n")


def main(argv: list[str]) -> int:
    page = assemble()
    if "--write" in argv:
        TEMPLATE.write_bytes(page.encode("utf-8"))
        print(f"wrote {TEMPLATE} ({len(page.splitlines())} lines)")
        return 0
    if _lf(TEMPLATE.read_bytes().decode("utf-8")) != page:
        print("src/template.html is out of date: run python src/web/assemble.py --write")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
