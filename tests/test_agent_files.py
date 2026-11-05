"""The agent files in .claude/agents/ must be valid YAML, or the session silently drops the agent from its list."""
from pathlib import Path

import yaml

AGENTS = Path(__file__).resolve().parent.parent / ".claude" / "agents"


def test_every_agent_file_has_valid_frontmatter():
    files = sorted(AGENTS.glob("*.md"))
    assert files, "no agent files found"
    for p in files:
        meta = yaml.safe_load(p.read_text(encoding="utf-8").split("---")[1])
        assert meta["name"] == p.stem, p.name
        assert isinstance(meta["description"], str) and meta["description"], p.name
