"""Writes that cannot leave a half-written file behind: write next to the target, then swap it in."""
from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path | str, text: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, p)                      # on one volume this is an atomic swap, also on Windows
    return p
