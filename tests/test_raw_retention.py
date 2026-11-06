"""Tests for scripts/raw_retention.py (DATA-9). Synthetic files in tmp_path only."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 6)


def _load():
    path = ROOT / "scripts" / "raw_retention.py"
    spec = importlib.util.spec_from_file_location("raw_retention", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses look the module up by name while it loads
    spec.loader.exec_module(mod)
    return mod


rr = _load()


def _make(raw: Path, source: str, name: str, content: bytes = b"x") -> Path:
    folder = raw / source
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(content)
    return path


def _old(days_before_today: int) -> date:
    return TODAY - timedelta(days=days_before_today)


def test_newest_60_days_are_untouched(tmp_path):
    raw = tmp_path / "data" / "raw"
    # Two files inside the 60-day window, in an ISO week that would otherwise qualify.
    recent_a = _make(raw, "yfinance", f"{_old(10).isoformat()}.csv.gz")
    recent_b = _make(raw, "yfinance", f"{_old(59).isoformat()}_120000.csv.gz")
    moves = rr.plan_retention(raw, TODAY, keep_days=60)
    moved = {src for src, _ in moves}
    assert recent_a not in moved
    assert recent_b not in moved
    assert moves == []


def test_first_pull_of_each_old_week_stays(tmp_path):
    raw = tmp_path / "data" / "raw"
    # Pick a Monday more than 60 days old, then three pulls in that ISO week and one in the next.
    monday = _old(120)
    monday -= timedelta(days=monday.weekday())
    first = _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    second = _make(raw, "yfinance", f"{(monday + timedelta(days=1)).isoformat()}_090000.csv.gz")
    third = _make(raw, "yfinance", f"{(monday + timedelta(days=3)).isoformat()}_101010.csv.gz")
    next_week = _make(raw, "yfinance", f"{(monday + timedelta(days=8)).isoformat()}.csv.gz")

    moves = rr.plan_retention(raw, TODAY, keep_days=60)
    moved = {src for src, _ in moves}
    assert first not in moved
    assert next_week not in moved  # first pull of the following week also stays
    assert second in moved
    assert third in moved


def test_all_three_name_forms_parse(tmp_path):
    raw = tmp_path / "data" / "raw"
    d = _old(200)
    names = [
        f"{d.isoformat()}.csv.gz",
        f"{d.isoformat()}_142529.csv.gz",
        f"{d.isoformat()}T163542.json",
    ]
    for n in names:
        ext = ".json" if n.endswith(".json") else ".csv.gz"
        _make(raw, "yfinance_earnings" if ext == ".json" else "yfinance", n)

    plan = rr.build_plan(raw, TODAY, keep_days=60)
    assert plan.unknown == []
    parsed = {p.name for p in plan.parsed}
    assert parsed == set(names)


def test_unknown_name_is_left_alone(tmp_path):
    raw = tmp_path / "data" / "raw"
    odd = _make(raw, "yfinance", "notes_final.csv.gz")
    odd_json = _make(raw, "yfinance_fundamentals", "2026-11-04.json.bak")

    moves = rr.plan_retention(raw, TODAY, keep_days=60)
    assert moves == []
    assert odd.exists() and odd_json.exists()

    plan = rr.build_plan(raw, TODAY, keep_days=60)
    assert {p.name for p in plan.unknown} == {"notes_final.csv.gz", "2026-11-04.json.bak"}


def test_backtest_raw_is_never_moved(tmp_path):
    raw = tmp_path / "data" / "raw"
    # Old, and not the first pull of its week, so it would move if it were not protected.
    monday = _old(150)
    monday -= timedelta(days=monday.weekday())
    _make(raw, "yfinance_backtest", f"{monday.isoformat()}.csv.gz")
    later = _make(raw, "yfinance_backtest", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")

    moves = rr.plan_retention(raw, TODAY, keep_days=60)
    assert all("yfinance_backtest" not in str(src) for src, _ in moves)
    assert later.exists()


def test_a_file_cited_in_registry_is_protected(tmp_path):
    raw = tmp_path / "data" / "raw"
    monday = _old(150)
    monday -= timedelta(days=monday.weekday())
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    cited_content = b"cited raw pull"
    cited = _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz", cited_content)
    other = _make(raw, "yfinance", f"{(monday + timedelta(days=4)).isoformat()}.csv.gz", b"not cited")

    registry = tmp_path / "output" / "backtests" / "registry.csv"
    registry.parent.mkdir(parents=True)
    with registry.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["run_id", "raw_sha256"])
        writer.writeheader()
        writer.writerow({"run_id": "r1", "raw_sha256": hashlib.sha256(cited_content).hexdigest()})

    hashes, notes = rr.load_registry_hashes(registry)
    assert hashlib.sha256(cited_content).hexdigest() in hashes
    assert notes == []

    moves = rr.plan_retention(raw, TODAY, keep_days=60, protected=hashes)
    moved = {src for src, _ in moves}
    assert cited not in moved
    assert other in moved


def test_dry_run_moves_nothing(tmp_path, capsys):
    raw = tmp_path / "data" / "raw"
    monday = _old(150)
    monday -= timedelta(days=monday.weekday())
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    victim = _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")

    code = rr.main(["--raw-root", str(raw), "--registry", str(tmp_path / "missing.csv")], today=TODAY)
    assert code == 0
    assert victim.exists()
    assert not (tmp_path / "data" / "raw_archive").exists()
    out = capsys.readouterr().out
    assert "dry run" in out.lower()


def test_apply_never_overwrites(tmp_path, capsys):
    raw = tmp_path / "data" / "raw"
    src = _make(raw, "yfinance", "2026-07-01.csv.gz", b"new copy")
    dst = tmp_path / "data" / "raw_archive" / "yfinance" / "2026-07-01.csv.gz"
    dst.parent.mkdir(parents=True)
    dst.write_bytes(b"already archived")

    count = rr.apply_moves([(src, dst)])
    assert count == 0
    assert src.read_bytes() == b"new copy"
    assert dst.read_bytes() == b"already archived"
    assert "skipped" in capsys.readouterr().out.lower()


def test_apply_moves_into_archive(tmp_path):
    raw = tmp_path / "data" / "raw"
    src = _make(raw, "yfinance", "2026-07-01.csv.gz", b"payload")
    dst = tmp_path / "data" / "raw_archive" / "yfinance" / "2026-07-01.csv.gz"

    assert rr.apply_moves([(src, dst)]) == 1
    assert not src.exists()
    assert dst.read_bytes() == b"payload"


def test_archive_path_is_sibling_of_raw(tmp_path):
    raw = tmp_path / "data" / "raw"
    monday = _old(150)
    monday -= timedelta(days=monday.weekday())
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")

    moves = rr.plan_retention(raw, TODAY, keep_days=60)
    assert len(moves) == 1
    _, dst = moves[0]
    assert dst.parent == tmp_path / "data" / "raw_archive" / "yfinance"


def test_missing_registry_is_reported_not_fatal(tmp_path, capsys):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    hashes, notes = rr.load_registry_hashes(tmp_path / "nope" / "registry.csv")
    assert hashes == set()
    assert any("no registry" in n.lower() for n in notes)


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_text_is_plain(flag, capsys):
    with pytest.raises(SystemExit):
        rr.main([flag])
    out = capsys.readouterr().out
    assert "dry run" in out.lower()
    assert "--apply" in out
