"""scripts/run_daily.bat (DATA-10): one retry after exit code 2, run.log rotation, test hooks.

The static checks read the batch text, because cmd.exe cannot run in the Linux sandbox or in CI.
The Windows test runs a copy of the batch file with tests/stubs/exit2_then_0.cmd in place of python; it runs on Iiro's PC only.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "run_daily.bat"
STUB = ROOT / "tests" / "stubs" / "exit2_then_0.cmd"


def _code() -> list[str]:
    """Batch lines without comments and blank lines, stripped."""
    lines = [ln.strip() for ln in BAT.read_text(encoding="ascii").splitlines()]
    return [ln for ln in lines if ln and not re.match(r"(?i)^(rem\b|::)", ln)]


def _first(code: list[str], pattern: str) -> int:
    hits = [i for i, ln in enumerate(code) if re.search(pattern, ln, re.I)]
    assert hits, f"no line matches {pattern!r}"
    return hits[0]


def test_exactly_one_retry_only_after_exit_code_2():
    code = _code()
    assert len([ln for ln in code if re.match(r"(?i):run\b", ln)]) == 1                  # one :run label
    after = code[_first(code, r"^:run\b"):]
    assert len([ln for ln in after if re.search(r"(?i)\bgoto\s+:?run\b", ln)]) == 1       # one jump back to the run
    assert len([ln for ln in code if re.search(r"(?i)\bset\s+\"?RETRIED=1", ln)]) == 1
    compared = set(re.findall(r'"%RC%"\s*==\s*"(\d+)"', "\n".join(code)))
    assert "2" in compared and compared <= {"0", "2"}                                    # exit 3 and crashes never retry
    i_rc2 = _first(code, r'"%RC%"\s*==\s*"2"')
    i_guard = _first(code, r"\bif\s+(not\s+)?defined\s+RETRIED\b")
    i_set = _first(code, r"\bset\s+\"?RETRIED=1")
    i_goto = len(code) - 1 - _first(code[::-1], r"\bgoto\s+:?run\b")                     # the last jump to :run
    assert _first(code, r"^:run\b") < i_rc2 <= i_guard <= i_set <= i_goto                 # the retry is guarded by both checks
    assert re.search(r"(?im)^set\s+\"?RETRIED=\"?$", "\n".join(code[:_first(code, r"^:run\b")]))  # cleared before the first run


def test_the_wait_does_not_use_timeout_and_defaults_to_20_minutes():
    code = _code()
    assert not any(re.search(r"(?i)(^|[&(|]\s*)timeout\b", ln) for ln in code)            # timeout fails without a console
    wait = [ln for ln in code if re.search(r"(?i)start-sleep|\bping\s+-n\b", ln)]
    assert wait and all("%DIPDASH_RETRY_WAIT%" in ln for ln in wait)
    assert any(re.search(r"(?i)\bset\s+\"?DIPDASH_RETRY_WAIT=1200\b", ln) for ln in code)
    assert any("retrying in %DIPDASH_RETRY_WAIT% s" in ln and "run.log" in ln for ln in code)


def test_run_log_rotates_to_one_older_copy_before_the_first_start():
    code = _code()
    assert any(re.search(r"(?i)\bset\s+\"?DIPDASH_LOG_MAX=5242880\b", ln) for ln in code)
    i_move = _first(code, r"\bmove\s+/y\s+\"?output\\run\.log\"?\s+\"?output\\run\.log\.1\"?")
    assert i_move < _first(code, r"^:run\b") < _first(code, r"==== start")             # rotation runs once, before the run
    assert any("%%~z" in ln for ln in code[:i_move]) and any("%DIPDASH_LOG_MAX%" in ln for ln in code[:i_move])
    assert not any(re.search(r"(?i)\bdel\b.*run\.log", ln) for ln in code)              # the previous log is moved, never deleted here


def test_python_can_be_replaced_by_a_stub_and_is_started_with_call():
    code = _code()
    assert any(re.search(r'(?i)set\s+"?PY=\.venv\\Scripts\\python\.exe', ln) for ln in code)
    assert any(re.search(r"(?i)if\s+defined\s+DIPDASH_PYTHON\b.*%DIPDASH_PYTHON%", ln) for ln in code)
    run = [ln for ln in code if "src\\dip_screener.py" in ln]
    assert len(run) == 1 and re.match(r'(?i)call\s+"%PY%"', run[0])                     # without call a .cmd stub never returns
    assert _first(code, r"notify\.ps1") > _first(code, r"exit\s+/b\s+%RC%")              # notify only after a final exit 0


def test_the_stub_exits_2_then_0_and_has_crlf_line_ends():
    raw = STUB.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("ascii")
    assert "exit /b 2" in text and "exit /b 0" in text and "output\\exit2_then_0.state" in text


@pytest.mark.skipif(sys.platform != "win32", reason="runs cmd.exe; checked on Iiro's Windows PC")
def test_on_windows_exit_2_is_retried_once_and_the_big_log_is_rotated(tmp_path):
    root = tmp_path / "repo"                                       # a copy, so the real output\run.log is untouched
    (root / "scripts").mkdir(parents=True)
    (root / "output").mkdir()
    shutil.copy2(BAT, root / "scripts" / "run_daily.bat")
    (root / "output" / "run.log").write_text("old line\r\n" * 300, encoding="ascii")   # 3000 bytes, over the 2000 limit
    env = {**os.environ, "DIPDASH_PYTHON": str(STUB), "DIPDASH_RETRY_WAIT": "1", "DIPDASH_LOG_MAX": "2000"}
    r = subprocess.run(["cmd", "/c", str(root / "scripts" / "run_daily.bat")], cwd=root, env=env,
                       capture_output=True, timeout=180)
    log = (root / "output" / "run.log").read_text(encoding="utf-8", errors="replace")
    assert r.returncode == 0, log
    assert log.count("==== start") == 2 and "retrying in 1 s" in log
    assert log.index("==== exit code 2") < log.index("retrying in 1 s") < log.index("==== exit code 0")
    assert "log rotated" in log and "old line" not in log
    assert (root / "output" / "run.log.1").read_text(encoding="ascii").count("old line") == 300
    assert not (root / "output" / "exit2_then_0.state").exists()   # the stub cleaned up after its second call
