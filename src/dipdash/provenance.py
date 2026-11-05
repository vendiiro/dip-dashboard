"""Provenance recorded in every research spec: which code, which package versions, which settings sections.

It is written into the spec but never hashed (`registry.ALWAYS_EXCLUDED`), so a new commit or an edit to an unused settings
section does not give an analysis a new identity. Every setting a test uses is already in the spec by value.
`registry.register` never overwrites `spec_<hash>.json`, so a rerun of the same hash keeps the FIRST run's provenance in the archive;
the latest run's provenance is in the run folder's own spec file (spec.json / spec_<kind>.json).
stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import asdict, fields, is_dataclass
from importlib import metadata
from pathlib import Path

PACKAGES = ("pandas", "numpy", "scipy", "yfinance", "arch", "statsmodels")


def code_hash(src_dir: Path) -> str:
    """sha256 over the sorted relative paths and contents of every .py file under `src_dir`. CRLF and LF hash the same."""
    src_dir = Path(src_dir)
    h = hashlib.sha256()
    for p in sorted(src_dir.rglob("*.py"), key=lambda q: q.relative_to(src_dir).as_posix()):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(src_dir).as_posix().encode() + b"\0")
        h.update(p.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def package_versions(names: tuple[str, ...] = PACKAGES) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for n in names:
        try:
            out[n] = metadata.version(n)
        except metadata.PackageNotFoundError:
            out[n] = None
    return out


def _canonical(value):
    """JSON-ready copy: dataclasses as dicts, tuples as lists; dict keys are sorted when dumped."""
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def settings_section_hashes(s) -> dict[str, str]:
    """One 16-hex hash per top-level settings section, so an edit to [news] shows up as a change in 'news' only."""
    out = {}
    for f in fields(s):
        body = json.dumps(_canonical(getattr(s, f.name)), sort_keys=True, default=str)
        out[f.name] = hashlib.sha256(body.encode()).hexdigest()[:16]
    return out


def build_provenance(s, src_dir: Path) -> dict:
    return {"code_sha256": code_hash(src_dir), "python": platform.python_version(), "packages": package_versions(), "settings_sections": settings_section_hashes(s)}
