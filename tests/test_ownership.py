"""The agent tree stays enforceable: every tracked file has exactly one owner agent, and every owner is a defined agent.

See docs/AGENTS.md. Ownership lives in docs/agents/ownership.csv (fnmatch patterns, '*' crosses '/').
"""
import csv
import fnmatch
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".claude" / "agents"
SKIP_DIRS = {".git", ".venv", "venv", "data", "output", "__pycache__", ".pytest_cache", "node_modules"}


def _rules() -> list[tuple[str, str]]:
    with (ROOT / "docs" / "agents" / "ownership.csv").open(encoding="utf-8") as fh:
        rows = [r for r in csv.reader(fh) if r and not r[0].startswith("#")]
    assert rows[0] == ["pattern", "owner"]
    return [(p.strip(), o.strip()) for p, o in rows[1:]]


def _files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
        files = [f for f in out if f]
        if files:
            return files
    except (OSError, subprocess.CalledProcessError):
        pass
    return [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")                 # no git (for example a zip copy)
            if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(ROOT).parts)]


def _frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---", f"{path.name}: front matter must start on line 1"
    end = lines.index("---", 1)
    return dict(line.split(":", 1) for line in lines[1:end] if ":" in line)


def test_every_tracked_file_has_exactly_one_owner():
    rules = _rules()
    problems = []
    for f in _files():
        owners = sorted({o for p, o in rules if fnmatch.fnmatch(f, p)})
        if len(owners) != 1:
            problems.append(f"{f}: {owners or 'no owner'}")
    assert not problems, "add or fix a pattern in docs/agents/ownership.csv:\n" + "\n".join(problems)


def test_every_owner_is_a_defined_agent_with_valid_front_matter():
    owners = {o for _, o in _rules()}
    defined = {p.stem for p in AGENTS.glob("*.md")}
    assert owners <= defined, f"owners without an agent file: {sorted(owners - defined)}"
    for p in AGENTS.glob("*.md"):
        fm = {k.strip(): v.strip() for k, v in _frontmatter(p).items()}
        assert fm.get("name") == p.stem, f"{p.name}: name must equal the file name"
        assert len(fm.get("description", "")) > 40, f"{p.name}: description must say when to use the agent"
        assert fm.get("tools"), f"{p.name}: list the tools"


def test_read_only_reviewers_cannot_edit():
    for name in ("ui-reviewer", "stats-reviewer", "wording-guard"):
        tools = {t.strip() for t in _frontmatter(AGENTS / f"{name}.md")["tools"].split(",")}
        assert not tools & {"Edit", "Write", "NotebookEdit"}, f"{name} is a reviewer and must not have edit tools"
