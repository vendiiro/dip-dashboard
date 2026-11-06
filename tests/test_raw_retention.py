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


def _old_monday(days_before_today: int = 150) -> date:
    d = _old(days_before_today)
    return d - timedelta(days=d.weekday())


def _registry(path: Path, hashes: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["run_id", "raw_sha256"])
        writer.writeheader()
        for i, h in enumerate(hashes):
            writer.writerow({"run_id": f"r{i}", "raw_sha256": h})
    return path


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
    monday = _old_monday(120)
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


def test_iso_year_boundary_is_one_week(tmp_path):
    raw = tmp_path / "data" / "raw"
    # 2025-12-29 (Monday) and 2026-01-02 (Friday) are both ISO week 2026-W01.
    assert date(2025, 12, 29).isocalendar()[:2] == date(2026, 1, 2).isocalendar()[:2]
    first = _make(raw, "yfinance", "2025-12-29.csv.gz")
    later = _make(raw, "yfinance", "2026-01-02.csv.gz")

    moves = rr.plan_retention(raw, TODAY, keep_days=60)
    moved = {src for src, _ in moves}
    assert first not in moved
    assert later in moved


def test_first_pull_is_per_source(tmp_path):
    raw = tmp_path / "data" / "raw"
    monday = _old_monday(150)
    yf_first = _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    yf_later = _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")
    fund_first = _make(raw, "yfinance_fundamentals", f"{(monday + timedelta(days=1)).isoformat()}.csv.gz")
    fund_later = _make(raw, "yfinance_fundamentals", f"{(monday + timedelta(days=3)).isoformat()}.csv.gz")

    moved = {src for src, _ in rr.plan_retention(raw, TODAY, keep_days=60)}
    # Same ISO week, but each source keeps its own first pull.
    assert moved == {yf_later, fund_later}
    assert yf_first not in moved and fund_first not in moved


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


def test_file_dated_after_today_is_noted_not_moved(tmp_path):
    raw = tmp_path / "data" / "raw"
    monday = _old_monday(150)
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    future = _make(raw, "yfinance", f"{(TODAY + timedelta(days=3)).isoformat()}.csv.gz")

    plan = rr.build_plan(raw, TODAY, keep_days=60)
    assert future in plan.future
    assert all(src != future for src, _ in plan.moves)
    assert future.exists()


def test_backtest_raw_is_never_moved(tmp_path):
    raw = tmp_path / "data" / "raw"
    # Old, and not the first pull of its week, so it would move if it were not protected.
    monday = _old_monday(150)
    _make(raw, "yfinance_backtest", f"{monday.isoformat()}.csv.gz")
    later = _make(raw, "yfinance_backtest", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")

    moves = rr.plan_retention(raw, TODAY, keep_days=60)
    assert all("yfinance_backtest" not in str(src) for src, _ in moves)
    assert later.exists()


def test_a_file_cited_in_registry_is_protected(tmp_path):
    raw = tmp_path / "data" / "raw"
    monday = _old_monday(150)
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    cited_content = b"cited raw pull"
    cited = _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz", cited_content)
    other = _make(raw, "yfinance", f"{(monday + timedelta(days=4)).isoformat()}.csv.gz", b"not cited")

    registry = _registry(tmp_path / "output" / "backtests" / "registry.csv",
                         [hashlib.sha256(cited_content).hexdigest()])

    hashes, problems = rr.load_registry_hashes(registry)
    assert hashlib.sha256(cited_content).hexdigest() in hashes
    assert problems == []

    moves = rr.plan_retention(raw, TODAY, keep_days=60, protected=hashes)
    moved = {src for src, _ in moves}
    assert cited not in moved
    assert other in moved


def test_dry_run_moves_nothing(tmp_path, capsys):
    raw = tmp_path / "data" / "raw"
    monday = _old_monday(150)
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    victim = _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")

    code = rr.main(["--raw-root", str(raw), "--registry", str(tmp_path / "missing.csv")], today=TODAY)
    assert code == 0
    assert victim.exists()
    assert not (tmp_path / "data" / "raw_archive").exists()
    out = capsys.readouterr().out
    assert "dry run" in out.lower()
    assert "no registry" in out.lower()  # the missing registry is noted, the dry run continues


def test_apply_never_overwrites(tmp_path, capsys):
    raw = tmp_path / "data" / "raw"
    src = _make(raw, "yfinance", "2026-07-01.csv.gz", b"new copy")
    dst = tmp_path / "data" / "raw_archive" / "yfinance" / "2026-07-01.csv.gz"
    dst.parent.mkdir(parents=True)
    dst.write_bytes(b"already archived")

    result = rr.apply_moves([(src, dst)])
    assert result.moved == 0 and result.skipped == 1 and result.failed == 0
    assert src.read_bytes() == b"new copy"
    assert dst.read_bytes() == b"already archived"
    out = capsys.readouterr().out
    assert "skipped" in out.lower()
    assert "compare" in out.lower()  # hint to compare the two files by hand


def test_apply_moves_into_archive(tmp_path):
    raw = tmp_path / "data" / "raw"
    src = _make(raw, "yfinance", "2026-07-01.csv.gz", b"payload")
    dst = tmp_path / "data" / "raw_archive" / "yfinance" / "2026-07-01.csv.gz"

    result = rr.apply_moves([(src, dst)])
    assert result.moved == 1 and result.ok
    assert not src.exists()
    assert dst.read_bytes() == b"payload"


def test_copy_failure_leaves_source_and_no_partial_and_run_continues(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "data" / "raw"
    bad_src = _make(raw, "yfinance", "2026-07-01.csv.gz", b"first")
    good_src = _make(raw, "yfinance", "2026-07-02.csv.gz", b"second")
    bad_dst = tmp_path / "data" / "raw_archive" / "yfinance" / bad_src.name
    good_dst = tmp_path / "data" / "raw_archive" / "yfinance" / good_src.name

    real_copy = rr._copy_stream

    def flaky_copy(src, out):
        if src.name == bad_src.name:
            out.write(b"part")  # a partial write, then the copy breaks
            raise OSError("simulated copy failure")
        return real_copy(src, out)

    monkeypatch.setattr(rr, "_copy_stream", flaky_copy)
    result = rr.apply_moves([(bad_src, bad_dst), (good_src, good_dst)])

    assert bad_src.read_bytes() == b"first"  # source intact
    assert not bad_dst.exists()              # partial target removed
    assert good_dst.read_bytes() == b"second"  # the next move still ran
    assert not good_src.exists()
    assert result.failed == 1 and result.moved == 1
    assert not result.ok
    assert "failed" in capsys.readouterr().out.lower()


def test_hash_mismatch_removes_partial_and_keeps_source(tmp_path, monkeypatch):
    raw = tmp_path / "data" / "raw"
    src = _make(raw, "yfinance", "2026-07-01.csv.gz", b"correct bytes")
    dst = tmp_path / "data" / "raw_archive" / "yfinance" / src.name

    def wrong_copy(_src, out):
        out.write(b"wrong bytes")

    monkeypatch.setattr(rr, "_copy_stream", wrong_copy)
    result = rr.apply_moves([(src, dst)])

    assert not dst.exists()
    assert src.read_bytes() == b"correct bytes"
    assert result.failed == 1 and result.moved == 0


def test_failing_mkdir_leaves_source_and_later_moves_still_run(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "data" / "raw"
    bad_src = _make(raw, "yfinance", "2026-07-01.csv.gz", b"blocked")
    good_src = _make(raw, "yfinance_fundamentals", "2026-07-02.json", b"fine")
    arch = tmp_path / "data" / "raw_archive"
    bad_dst = arch / "yfinance" / bad_src.name
    good_dst = arch / "yfinance_fundamentals" / good_src.name

    real_mkdir = rr.Path.mkdir

    def blocked_mkdir(self, *args, **kwargs):
        if self == arch / "yfinance":
            raise OSError("simulated: folder cannot be created")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(rr.Path, "mkdir", blocked_mkdir)
    result = rr.apply_moves([(bad_src, bad_dst), (good_src, good_dst)])

    assert bad_src.read_bytes() == b"blocked"  # source intact
    assert not bad_dst.exists()
    assert result.failed == 1 and result.moved == 1
    assert good_dst.read_bytes() == b"fine" and not good_src.exists()
    assert "could not create" in capsys.readouterr().out.lower()


def test_unlink_failure_is_reported_and_run_continues(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "data" / "raw"
    first = _make(raw, "yfinance", "2026-07-01.csv.gz", b"one")
    second = _make(raw, "yfinance", "2026-07-02.csv.gz", b"two")
    arch = tmp_path / "data" / "raw_archive" / "yfinance"

    real_remove = rr._remove

    def stuck_remove(path):
        if path == first:
            raise PermissionError("simulated lock")
        return real_remove(path)

    monkeypatch.setattr(rr, "_remove", stuck_remove)
    result = rr.apply_moves([(first, arch / first.name), (second, arch / second.name)])

    assert (arch / first.name).read_bytes() == b"one"  # copy was verified and kept
    assert first.exists()                             # original not removed, reported
    assert not second.exists() and (arch / second.name).read_bytes() == b"two"
    assert result.copied_only == 1 and result.moved == 1
    assert not result.ok
    assert "copied, original not removed" in capsys.readouterr().out


def test_apply_exit_is_nonzero_when_a_move_failed(tmp_path, monkeypatch):
    raw = tmp_path / "data" / "raw"
    monday = _old_monday(150)
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz", b"x")
    registry = _registry(tmp_path / "reg" / "registry.csv", [])

    def broken_copy(_src, _out):
        raise OSError("simulated")

    monkeypatch.setattr(rr, "_copy_stream", broken_copy)
    code = rr.main(["--apply", "--raw-root", str(raw), "--registry", str(registry)], today=TODAY)
    assert code == 1


def test_apply_refuses_when_registry_is_missing(tmp_path, capsys):
    raw = tmp_path / "data" / "raw"
    monday = _old_monday(150)
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    victim = _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")

    code = rr.main(["--apply", "--raw-root", str(raw), "--registry", str(tmp_path / "nope.csv")], today=TODAY)
    assert code == 2
    assert victim.exists()
    assert not (tmp_path / "data" / "raw_archive").exists()
    assert "refused" in capsys.readouterr().out.lower()


def test_apply_refuses_when_registry_has_no_raw_sha256_column(tmp_path, capsys):
    raw = tmp_path / "data" / "raw"
    monday = _old_monday(150)
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    victim = _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")
    registry = tmp_path / "registry.csv"
    registry.write_text("run_id,score\nr1,0.5\n", encoding="utf-8")

    code = rr.main(["--apply", "--raw-root", str(raw), "--registry", str(registry)], today=TODAY)
    assert code == 2
    assert victim.exists()
    assert "raw_sha256" in capsys.readouterr().out


def test_apply_refuses_when_registry_is_unreadable(tmp_path, capsys):
    raw = tmp_path / "data" / "raw"
    monday = _old_monday(150)
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    victim = _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")
    registry = tmp_path / "registry.csv"
    registry.write_bytes(b"raw_sha256\n\xff\xfe\xfa\n")  # not UTF-8

    code = rr.main(["--apply", "--raw-root", str(raw), "--registry", str(registry)], today=TODAY)
    assert code == 2
    assert victim.exists()
    assert "could not read" in capsys.readouterr().out.lower()


def test_apply_refuses_when_registry_raises_oserror(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "data" / "raw"
    monday = _old_monday(150)
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    victim = _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")
    registry = _registry(tmp_path / "registry.csv", [])

    real_open = rr.Path.open

    def boom(self, *args, **kwargs):
        if self == registry:
            raise OSError("simulated unreadable")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(rr.Path, "open", boom)
    code = rr.main(["--apply", "--raw-root", str(raw), "--registry", str(registry)], today=TODAY)
    assert code == 2
    assert victim.exists()
    assert "could not read" in capsys.readouterr().out.lower()


def test_no_registry_flag_allows_apply(tmp_path, capsys):
    raw = tmp_path / "data" / "raw"
    monday = _old_monday(150)
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    victim = _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")

    code = rr.main(["--apply", "--no-registry", "--raw-root", str(raw),
                    "--registry", str(tmp_path / "nope.csv")], today=TODAY)
    assert code == 0
    assert not victim.exists()
    assert (tmp_path / "data" / "raw_archive" / "yfinance" / victim.name).exists()
    assert "--no-registry" in capsys.readouterr().out


def test_archive_path_is_sibling_of_raw(tmp_path):
    raw = tmp_path / "data" / "raw"
    monday = _old_monday(150)
    _make(raw, "yfinance", f"{monday.isoformat()}.csv.gz")
    _make(raw, "yfinance", f"{(monday + timedelta(days=2)).isoformat()}.csv.gz")

    moves = rr.plan_retention(raw, TODAY, keep_days=60)
    assert len(moves) == 1
    _, dst = moves[0]
    assert dst.parent == tmp_path / "data" / "raw_archive" / "yfinance"


def test_missing_registry_is_reported_not_fatal(tmp_path):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    hashes, problems = rr.load_registry_hashes(tmp_path / "nope" / "registry.csv")
    assert hashes == set()
    assert any("no registry" in p.lower() for p in problems)


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_text_is_plain(flag, capsys):
    with pytest.raises(SystemExit):
        rr.main([flag])
    out = capsys.readouterr().out
    assert "dry run" in out.lower()
    assert "--apply" in out
    assert "--no-registry" in out
