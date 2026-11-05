"""The pre-commit guards in scripts/check_wording.py (OPS-7) and the task runner tasks.py (OPS-6).

Tested on file lists in tmp_path, without git, so they run in the sandbox and in CI alike.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CW = _load("check_wording", ROOT / "scripts" / "check_wording.py")
TASKS = _load("tasks", ROOT / "tasks.py")

# Split like the script, so this file reads cleanly to a human and to the scan.
BUY_NOW, SELL, PT, RECOVER, GUAR = "bu" + "y now", "se" + "ll", "price tar" + "get", "will reco" + "ver", "guaran" + "teed"

# One planted example per widened phrase (split so the scan does not read this file either).
NEW_PHRASES = ["should " + "bu" + "y", "should " + "se" + "ll", "should " + "ho" + "ld", "under" + "valued", "bar" + "gain",
               "bar" + "gains", "will " + "ri" + "se", "will " + "re" + "bound", "will " + "bou" + "nce", "will go " + "up",
               "expected " + "return", "expected " + "returns", "strong " + "bu" + "y", "top " + "pi" + "ck", "top " + "pi" + "cks"]


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "check_wording.py"), *args],
                          capture_output=True, text=True, encoding="utf-8")


# ---------------------------------------------------------------- wording scan
@pytest.mark.parametrize("phrase", [BUY_NOW, SELL, PT, RECOVER, GUAR, BUY_NOW.upper(), "bu" + "y   now", SELL + "s"])
def test_each_advice_phrase_is_found(phrase):
    assert CW.scan_text(f"ok line\nThe stock: {phrase}.\n") == [(2, phrase)]


@pytest.mark.parametrize("phrase", NEW_PHRASES + [p.upper() for p in NEW_PHRASES[:3]])
def test_each_widened_advice_phrase_is_found(phrase):
    assert CW.scan_text(f"ok line\nSomeone says it is {phrase} today.\n") == [(2, phrase)]


@pytest.mark.parametrize("text", [
    "Target Corp", "tap target 44px", "target_col", "feature target", "a bargaining chip", "returns are not expected",
    "it should be fine", "will riser", "the price will bounded", "top picked", "overvalue", "holdings",
])
def test_bare_target_and_near_misses_are_not_flagged(text):
    assert CW.scan_text(text) == []


@pytest.mark.parametrize("text", [
    "Educational; not a " + PT + ", not a direction call.",     # the disclaimer in forecast.py
    "the market is " + SELL + "ing off broadly",                # describing the market, in template.html
    "a broad " + SELL + "-off",
    "buyback yield", "seller", "target_col = 'fwd'", "entry_date", "you should read the log", "recovered by May",
])
def test_ordinary_words_and_the_disclaimer_are_not_flagged(text):
    assert CW.scan_text(text) == []


def test_scope_covers_user_visible_sources_only():
    yes = ["src/template.html", "src/dipdash/digest.py", "src/web/app.js", "config/alerts.toml", "scripts/notify.ps1",
           "scripts/run_daily.bat", "README.md", "START_HERE.md"]
    no = ["tests/test_digest.py", "docs/decisions.md", ".claude/agents/wording-guard.md", "CLAUDE.md", "TESTING.md",
          "scripts/check_wording.py", "src/dipdash/__pycache__/x.cpython-313.pyc", "src/logo.png", "scripts/sub/x.bat"]
    assert [f for f in yes if not CW.in_scope(f)] == []
    assert [f for f in no if CW.in_scope(f)] == []


def test_a_planted_phrase_is_reported_with_file_and_line(tmp_path):
    root = _tree(tmp_path, {"src/dipdash/digest.py": 'X = 1\nLINE = "' + BUY_NOW + '"\n',
                            "README.md": "Screen results only.\n",
                            "docs/notes.md": BUY_NOW + "\n",                      # out of scope: quoted on purpose
                            "tests/test_x.py": "# " + BUY_NOW + "\n"})
    assert CW.wording_findings(None, root) == [f"src/dipdash/digest.py:2: advice phrase '{BUY_NOW}' "
                                               "(use 'screen results', 'candidates', 'flagged because ...')"]
    r = _cli("--root", str(root))
    assert r.returncode == 1 and "src/dipdash/digest.py:2:" in r.stdout and "docs/notes.md" not in r.stdout


@pytest.mark.parametrize("part", ["footer.js", "layout.css", "body.html"])
def test_a_planted_phrase_in_a_web_part_is_found(tmp_path, part):
    root = _web_copy(tmp_path)
    (root / "src" / "web" / part).open("a", encoding="utf-8").write("\n/* " + BUY_NOW + " */\n")
    found = CW.wording_findings(None, root)
    assert len(found) == 1 and found[0].startswith(f"src/web/{part}:") and BUY_NOW in found[0]
    assert _cli("--root", str(root)).returncode == 1


def test_the_real_web_parts_are_in_scope():
    for rel in sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "src" / "web").iterdir()
                      if p.suffix in {".js", ".html", ".css"}):
        assert CW.in_scope(rel), rel


def test_staged_file_list_mode_ignores_out_of_scope_and_missing_files(tmp_path):
    root = _tree(tmp_path, {"docs/x.md": GUAR, "src/a.py": "fine\n"})
    assert CW.wording_findings(["docs/x.md", "src/a.py", "src/deleted.py"], root) == []
    assert CW.wording_findings([str(root / "src" / "a.py")], root) == []                      # absolute paths work too
    (root / "src" / "a.py").write_text(RECOVER, encoding="utf-8")
    assert len(CW.wording_findings([str(root / "src" / "a.py")], root)) == 1


def test_the_real_tree_is_clean():
    r = _cli()
    assert r.returncode == 0, r.stdout


# ---------------------------------------------------------------- path guard
@pytest.mark.parametrize("rel", ["output/x.html", "output/history/2026-11-03/dashboard.html", "data/raw/prices.parquet",
                                 ".env", ".env.local", "config/.env"])
def test_local_data_output_and_env_files_are_rejected(rel):
    assert CW.forbidden(rel)


@pytest.mark.parametrize("rel", [".env.example", "snapshots/2026-11-03/digest.md", "src/dipdash/data.py",
                                 "docs/sample-output/README.md", "config/settings.toml", "tests/test_output.py"])
def test_ordinary_files_pass_the_path_guard(rel):
    assert CW.forbidden(rel) is None


def test_path_guard_cli_on_staged_names():
    bad = _cli("--paths", "src/a.py", "output/x.html", ".env")
    assert bad.returncode == 1 and "output/x.html" in bad.stdout and ".env:" in bad.stdout and "src/a.py" not in bad.stdout
    assert _cli("--paths", "src/a.py", ".env.example", "snapshots/x.csv").returncode == 0
    assert _cli("--paths", "output\\x.html").returncode == (1 if sys.platform == "win32" else 0)   # backslash only splits on Windows


def test_path_guard_on_tracked_files_is_clean():
    r = _cli("--paths")
    assert r.returncode == 0, r.stdout


# ---------------------------------------------------------------- task runner and wiring
def test_task_runner_commands_and_the_makefile_wraps_them():
    assert {"demo", "test", "test-browser", "shots", "check", "hooks"} <= set(TASKS.COMMANDS)
    make = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipes = [ln.strip() for ln in make.splitlines() if ln.startswith("\t")]
    assert recipes and all(r.startswith("$(PY) tasks.py ") for r in recipes)                  # no logic in the Makefile
    assert {r.split()[2] for r in recipes} <= set(TASKS.COMMANDS)


def test_check_runs_every_step_and_fails_if_one_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(TASKS, "run", lambda *a: calls.append(a) or (1 if "--paths" in a else 0))
    assert TASKS.check(no_tests=False) == 1
    assert len(calls) == 4 and calls[3][:2] == ("-m", "pytest")                                # tests still ran
    assert calls[0] == ("src/web/assemble.py",)                                                # no --write in check
    calls.clear()
    monkeypatch.setattr(TASKS, "run", lambda *a: calls.append(a) or 0)
    assert TASKS.check(no_tests=True) == 0 and len(calls) == 3


def _web_copy(tmp_path: Path) -> Path:
    import shutil
    shutil.copytree(ROOT / "src" / "web", tmp_path / "src" / "web", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "src" / "template.html", tmp_path / "src" / "template.html")
    return tmp_path


def test_web_command_runs_the_assembler_with_write(monkeypatch):
    calls = []
    monkeypatch.setattr(TASKS, "run", lambda *a: calls.append(a) or 0)
    assert TASKS.COMMANDS["web"]() == 0 and calls == [("src/web/assemble.py", "--write")]
    assert "python tasks.py web" in TASKS.__doc__


def test_check_fails_early_on_a_stale_template_and_web_fixes_it(tmp_path, monkeypatch, capsys):
    root = _web_copy(tmp_path)
    monkeypatch.setattr(TASKS, "ROOT", root)
    monkeypatch.setattr(TASKS, "test", lambda: 0)
    monkeypatch.setattr(TASKS, "run", lambda *a: 0 if a[0] != "src/web/assemble.py" else
                        subprocess.run([sys.executable, str(root / a[0]), *a[1:]], cwd=root).returncode)
    assert TASKS.template_fresh() == 0                                           # fresh copy passes
    tpl = root / "src" / "template.html"
    tpl.write_bytes(tpl.read_bytes() + b"<!-- stale -->\n")
    assert TASKS.check(no_tests=True) == 1
    out = capsys.readouterr().out
    assert "src/template.html is out of date: run python tasks.py web" in out and "FAILED generated template" in out
    assert TASKS.web() == 0 and TASKS.check(no_tests=True) == 0                  # `web` regenerates it


def test_task_runner_sets_src_path_and_utf8():
    env = TASKS._env()
    assert env["PYTHONPATH"].split(__import__("os").pathsep)[0] == str(ROOT / "src")
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_ci_and_pre_commit_call_the_same_script():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    hooks = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "python tasks.py check" in ci
    assert "entry: python scripts/check_wording.py\n" in hooks and "entry: python scripts/check_wording.py --paths" in hooks
    pins = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert any(ln.startswith("pre-commit==") for ln in pins.splitlines())


def test_demo_does_not_overwrite_the_live_digest(monkeypatch):
    calls = []
    monkeypatch.setattr(TASKS, "run", lambda *a: calls.append(a) or 0)
    TASKS.demo()
    args = calls[0]
    assert "--demo" in args and args[args.index("--digest") + 1] == "output/digest.demo.md"
