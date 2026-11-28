"""Tests for scripts/setup_repos.sh dependency installation behavior."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = REPO_ROOT / "scripts" / "setup_repos.sh"


def test_setup_repos_shell_syntax_is_valid() -> None:
    subprocess.run(["bash", "-n", str(SETUP_SCRIPT)], check=True)


def test_setup_repos_agent_install_matches_ci_dependency_fallback() -> None:
    script = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "if [[ -f requirements.txt ]]; then" in script
    assert '"$MUMEI_AGENT_PYTHON" -m pip install -r requirements.txt' in script
    assert '"$MUMEI_AGENT_PYTHON" -m pip install -e ".[test]"' in script

    for workflow_name in ("demo.yml", "integration.yml", "audit-evidence-pack.yml"):
        workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
        assert "if [ -f requirements.txt ]; then" in workflow
        assert "-m pip install -r requirements.txt" in workflow
        assert '-m pip install -e ".[test]"' in workflow
