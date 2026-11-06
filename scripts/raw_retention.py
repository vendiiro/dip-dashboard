#!/usr/bin/env python3
"""Raw-data retention (DATA-9). Proposes moves of old raw pulls into an archive. Never deletes.

    python scripts/raw_retention.py                 # dry run: prints the plan, moves nothing
    python scripts/raw_retention.py --apply         # copies, verifies, then removes the originals
    python scripts/raw_retention.py --raw-root PATH --registry PATH

Rules:
- A raw file older than --keep-days (default 60) is a candidate for archiving.
- A file dated after today is noted and left alone.
- The first pull of each ISO week (per source folder) always stays in place.
- Everything in the yfinance_backtest folder always stays in place.
- A candidate whose sha256 equals a raw_sha256 value in a registry.csv stays in place.
  --registry may be a file or a folder (every registry.csv under it is read).
- With --apply, if the registry cannot be read (missing, no raw_sha256 column, unreadable),
  the run stops with exit code 2 unless --no-registry is given. A dry run only prints a note.
- Archive target: <raw root's parent>/raw_archive/<source>/<name>.
- Copy, then check the sha256 of the copy, then remove the original. If the copy or the check
  fails, the partial copy is removed and the original is kept. If the original cannot be
  removed, the copy is kept and reported as "copied, original not removed".
- An existing archive file is never overwritten; that move is skipped and printed.
- Names that do not match a known form are left alone and printed.
- Exit codes: 0 ok, 1 at least one move failed or was only half done, 2 apply refused.
Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO

ROOT = Path(__file__).resolve().parents[1]
KEEP_DAYS = 60
ALWAYS_PROTECTED_SOURCES = frozenset({"yfinance_backtest"})
NAME_RE = re.compile(r"^(?P<day>\d{4}-\d{2}-\d{2})(?:[_T](?P<time>\d{6}))?\.(?:csv\.gz|json)$")

MOVED = "moved"
SKIPPED = "skipped"
FAILED = "failed"
COPIED_ONLY = "copied_only"


class ArchiveError(Exception):
    """A copy did not verify (for example a sha256 mismatch)."""


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
    future: list[Path] = field(default_factory=list)
    kept_first: list[Path] = field(default_factory=list)
    protected: list[Path] = field(default_factory=list)
    moves: list[tuple[Path, Path]] = field(default_factory=list)


@dataclass
class ApplyResult:
    moved: int = 0
    skipped: int = 0
    failed: int = 0
    copied_only: int = 0

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.copied_only == 0


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
            if f.day > today:
                plan.future.append(f.path)
                continue
            if (today - f.day).days <= keep_days:
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
    """Collect raw_sha256 values from a registry.csv (or every registry.csv under a folder).

    Returns (hashes, problems). A non-empty problems list means citation protection
    could not be established.
    """
    problems: list[str] = []
    hashes: set[str] = set()
    try:
        if registry.is_dir():
            files = sorted(registry.rglob("registry.csv"))
            if not files:
                problems.append(f"no registry.csv under {registry}")
        elif registry.is_file():
            files = [registry]
        else:
            files = []
            problems.append(f"no registry found at {registry}")
    except OSError as exc:
        return hashes, [f"could not read {registry}: {exc}"]

    for path in files:
        try:
            with path.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None or "raw_sha256" not in reader.fieldnames:
                    problems.append(f"{path} has no raw_sha256 column")
                    continue
                for row in reader:
                    value = (row.get("raw_sha256") or "").strip().lower()
                    if value:
                        hashes.add(value)
        except (OSError, UnicodeError, csv.Error) as exc:
            problems.append(f"could not read {path}: {exc}")
    return hashes, problems


def _copy_stream(src: Path, out: BinaryIO) -> None:
    """Copy the bytes of src into an open output file. Separate so tests can inject failures."""
    with src.open("rb") as r:
        shutil.copyfileobj(r, out, 1 << 20)


def _remove(path: Path) -> None:
    """Remove a file. Separate so tests can inject failures."""
    os.remove(path)


def _size(path: Path) -> str:
    try:
        return f"{path.stat().st_size} bytes"
    except OSError:
        return "size unknown"


def _discard_partial(dst: Path) -> None:
    """Remove a partial target this run created. Never called for a file this run did not create."""
    try:
        os.remove(dst)
    except OSError as exc:
        print(f"warning: could not remove partial copy {dst}: {exc}")


def _archive_one(src: Path, dst: Path) -> str:
    """Copy src to dst, verify, then remove src. Returns MOVED, SKIPPED, FAILED or COPIED_ONLY."""
    if dst.exists():
        print(f"skipped (archive file already exists): {dst}")
        print(f"  hint: compare {src} ({_size(src)}) with {dst} ({_size(dst)}) by hand; nothing was changed.")
        return SKIPPED
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        out = dst.open("xb")  # exclusive create: fails rather than overwrite
    except FileExistsError:
        print(f"skipped (archive file already exists): {dst}")
        print(f"  hint: compare {src} ({_size(src)}) with {dst} ({_size(dst)}) by hand; nothing was changed.")
        return SKIPPED
    except OSError as exc:
        print(f"failed (could not create {dst}; original kept): {exc}")
        return FAILED

    try:
        with out:
            _copy_stream(src, out)
            out.flush()
            os.fsync(out.fileno())
        if sha256_file(dst) != sha256_file(src):
            raise ArchiveError("sha256 of the copy does not match the original")
    except (OSError, ArchiveError) as exc:
        _discard_partial(dst)
        print(f"failed (original kept, partial copy removed): {src}: {exc}")
        return FAILED

    try:
        _remove(src)
    except OSError as exc:
        print(f"copied, original not removed: {src} -> {dst} ({exc})")
        return COPIED_ONLY
    print(f"moved {src} -> {dst}")
    return MOVED


def apply_moves(moves: list[tuple[Path, Path]]) -> ApplyResult:
    """Archive each file in turn. Never overwrites and never deletes; one failure does not stop the rest."""
    result = ApplyResult()
    for src, dst in moves:
        outcome = _archive_one(src, dst)
        if outcome == MOVED:
            result.moved += 1
        elif outcome == SKIPPED:
            result.skipped += 1
        elif outcome == COPIED_ONLY:
            result.copied_only += 1
        else:
            result.failed += 1
    return result


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
    parser.add_argument("--no-registry", action="store_true",
                        help="with --apply: allow moves even if the registry cannot be read. "
                             "Cited raw files are then NOT protected. Use only on purpose.")
    args = parser.parse_args(argv)

    hashes, problems = load_registry_hashes(args.registry)
    for problem in problems:
        print(f"warning: citation protection not established: {problem}")
    if args.apply and problems:
        if not args.no_registry:
            print("refused: --apply needs the registry to protect cited raw files. Fix the problems above, "
                  "or pass --no-registry to override. Nothing was moved.")
            return 2
        print("note: --no-registry given; cited raw files are not protected in this run.")

    plan = build_plan(args.raw_root, today or date.today(), args.keep_days, hashes)
    print(f"raw folder: {args.raw_root}")
    print(f"known files: {len(plan.parsed)}, kept as first pull of an old week: {len(plan.kept_first)}, "
          f"protected: {len(plan.protected)}")
    for path in plan.future:
        print(f"note: dated after today, left alone: {path}")
    for path in plan.unknown:
        print(f"left alone (unknown name): {path}")

    if not args.apply:
        for src, dst in plan.moves:
            print(f"would move {src} -> {dst}")
        print(f"dry run: {len(plan.moves)} move(s) proposed, nothing moved. Add --apply to move them.")
        return 0

    result = apply_moves(plan.moves)
    print(f"result: moved {result.moved}, skipped {result.skipped} (archive file already existed), "
          f"failed {result.failed}, copied but original not removed {result.copied_only}. "
          f"Proposed {len(plan.moves)}.")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
