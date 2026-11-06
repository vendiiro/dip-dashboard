#!/usr/bin/env python3
"""Raw-data retention (DATA-9). Proposes moves of old raw pulls into an archive. Never deletes.

    python scripts/raw_retention.py                 # dry run: prints the plan, moves nothing
    python scripts/raw_retention.py --apply         # performs the moves listed by the dry run
    python scripts/raw_retention.py --raw-root PATH --registry PATH

Rules:
- A raw file older than --keep-days (default 60) is a candidate for archiving.
- The first pull of each ISO week (per source folder) always stays in place.
- Everything in the yfinance_backtest folder always stays in place.
- A candidate whose sha256 equals a raw_sha256 value in a registry.csv stays in place.
  --registry may be a file or a folder (every registry.csv under it is read).
- Archive target: <raw root's parent>/raw_archive/<source>/<name>.
- An existing archive file is never overwritten; that move is skipped and printed.
- Names that do not match a known form are left alone and printed.
Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEEP_DAYS = 60
ALWAYS_PROTECTED_SOURCES = frozenset({"yfinance_backtest"})
NAME_RE = re.compile(r"^(?P<day>\d{4}-\d{2}-\d{2})(?:[_T](?P<time>\d{6}))?\.(?:csv\.gz|json)$")


@dataclass(frozen=True)
class RawFile:
    path: Path
    source: str
    name: str
    day: date
    stamp: datetime


@dataclass
class RetentionPlan:
    parsed: list[RawFile] = field(default_factory=list)
    unknown: list[Path] = field(default_factory=list)
    kept_first: list[Path] = field(default_factory=list)
    protected: list[Path] = field(default_factory=list)
    moves: list[tuple[Path, Path]] = field(default_factory=list)


def parse_name(name: str) -> tuple[date, datetime] | None:
    """Return (day, timestamp) for the three known name forms, or None."""
    m = NAME_RE.match(name)
    if m is None:
        return None
    try:
        day = date.fromisoformat(m["day"])
        t = m["time"]
        if t:
            stamp = datetime(day.year, day.month, day.day, int(t[:2]), int(t[2:4]), int(t[4:]))
        else:
            stamp = datetime(day.year, day.month, day.day)
    except ValueError:
        return None
    return day, stamp


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_raw(raw_root: Path) -> tuple[list[RawFile], list[Path]]:
    """Split the files under raw_root/<source>/ into parseable and unknown."""
    parsed: list[RawFile] = []
    unknown: list[Path] = []
    if not raw_root.is_dir():
        return parsed, unknown
    for source_dir in sorted(p for p in raw_root.iterdir() if p.is_dir()):
        for path in sorted(p for p in source_dir.iterdir() if p.is_file()):
            info = parse_name(path.name)
            if info is None:
                unknown.append(path)
            else:
                parsed.append(RawFile(path, source_dir.name, path.name, info[0], info[1]))
    unknown.extend(sorted(p for p in raw_root.iterdir() if p.is_file()))
    return parsed, unknown


def _iso_week(day: date) -> tuple[int, int]:
    iso = day.isocalendar()
    return iso[0], iso[1]


def build_plan(
    raw_root: Path,
    today: date,
    keep_days: int = KEEP_DAYS,
    protected: set[str] | None = None,
) -> RetentionPlan:
    """Work out what would move. Hashes are computed only for files that would otherwise move."""
    protected_hashes = protected or set()
    plan = RetentionPlan()
    plan.parsed, plan.unknown = scan_raw(raw_root)
    archive_root = raw_root.parent / "raw_archive"

    by_source: dict[str, list[RawFile]] = {}
    for f in plan.parsed:
        by_source.setdefault(f.source, []).append(f)

    for source, files in sorted(by_source.items()):
        firsts = _first_pull_per_week(files)
        for f in sorted(files, key=lambda x: x.stamp):
            too_new = (today - f.day).days <= keep_days
            if too_new:
                continue
            if f.path in firsts:
                plan.kept_first.append(f.path)
                continue
            if source in ALWAYS_PROTECTED_SOURCES:
                plan.protected.append(f.path)
                continue
            if sha256_file(f.path) in protected_hashes:
                plan.protected.append(f.path)
                continue
            plan.moves.append((f.path, archive_root / source / f.name))
    return plan


def _first_pull_per_week(files: list[RawFile]) -> set[Path]:
    first: dict[tuple[int, int], RawFile] = {}
    for f in sorted(files, key=lambda x: x.stamp):
        first.setdefault(_iso_week(f.day), f)
    return {f.path for f in first.values()}


def plan_retention(
    raw_root: Path,
    today: date,
    keep_days: int = KEEP_DAYS,
    protected: set[str] | None = None,
) -> list[tuple[Path, Path]]:
    """Return the (source, archive target) moves that would be made. Nothing is moved here."""
    return build_plan(raw_root, today, keep_days, protected).moves


def load_registry_hashes(registry: Path) -> tuple[set[str], list[str]]:
    """Collect raw_sha256 values from a registry.csv (or every registry.csv under a folder)."""
    notes: list[str] = []
    if registry.is_dir():
        files = sorted(registry.rglob("registry.csv"))
        if not files:
            notes.append(f"no registry.csv under {registry}; no raw file is protected by citation")
    elif registry.is_file():
        files = [registry]
    else:
        files = []
        notes.append(f"no registry found at {registry}; no raw file is protected by citation")

    hashes: set[str] = set()
    for path in files:
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None or "raw_sha256" not in reader.fieldnames:
                notes.append(f"{path} has no raw_sha256 column; skipped")
                continue
            for row in reader:
                value = (row.get("raw_sha256") or "").strip().lower()
                if value:
                    hashes.add(value)
    return hashes, notes


def apply_moves(moves: list[tuple[Path, Path]]) -> int:
    """Move each file to its archive target. Never overwrites; returns the number moved."""
    moved = 0
    for src, dst in moves:
        if dst.exists():
            print(f"skipped (archive file already exists): {dst}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src, dst)  # fails if dst exists, on every platform
        except FileExistsError:
            print(f"skipped (archive file already exists): {dst}")
            continue
        except OSError as exc:
            print(f"skipped (could not archive {src}): {exc}")
            continue
        os.unlink(src)
        moved += 1
        print(f"moved {src} -> {dst}")
    return moved


def main(argv: list[str] | None = None, today: date | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan (dry run by default) the archiving of old raw data pulls. Nothing is deleted.",
    )
    parser.add_argument("--raw-root", type=Path, default=ROOT / "data" / "raw",
                        help="folder of raw pulls, one subfolder per source (default: data/raw)")
    parser.add_argument("--registry", type=Path, default=ROOT / "output" / "backtests" / "registry.csv",
                        help="registry.csv file, or a folder to search (default: output/backtests/registry.csv)")
    parser.add_argument("--keep-days", type=int, default=KEEP_DAYS,
                        help=f"files newer than this many days stay in place (default: {KEEP_DAYS})")
    parser.add_argument("--apply", action="store_true",
                        help="actually move the files. Without it, this is a dry run and nothing is moved.")
    args = parser.parse_args(argv)

    hashes, notes = load_registry_hashes(args.registry)
    for note in notes:
        print(f"note: {note}")

    plan = build_plan(args.raw_root, today or date.today(), args.keep_days, hashes)
    print(f"raw folder: {args.raw_root}")
    print(f"known files: {len(plan.parsed)}, kept as first pull of an old week: {len(plan.kept_first)}, "
          f"protected: {len(plan.protected)}")
    for path in plan.unknown:
        print(f"left alone (unknown name): {path}")

    if not args.apply:
        for src, dst in plan.moves:
            print(f"would move {src} -> {dst}")
        print(f"dry run: {len(plan.moves)} move(s) proposed, nothing moved. Add --apply to move them.")
        return 0

    count = apply_moves(plan.moves)
    print(f"moved {count} of {len(plan.moves)} proposed file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
