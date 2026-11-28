"""Tests for scripts/setup_repos.sh dependency installation behavior."""

from __future__ import annotations

import os
import shlex
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


def test_integration_demo_pins_linked_z3_before_building_mumei() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "integration.yml").read_text(encoding="utf-8")

    setup_step = workflow.index("uses: ./mumei/.github/actions/setup-z3")
    llvm_step = workflow.index("name: Install LLVM 17")
    build_step = workflow.index("name: Build mumei")

    assert setup_step < llvm_step < build_step
    assert "name: Use pinned Z3 for native linking" in workflow
    assert 'LIBRARY_PATH=$Z3_SYS_Z3_LIB_DIR' in workflow
    assert "shared-key: release-z3-4.14.1" in workflow
    assert "libz3-dev" not in workflow
    assert not any(line.strip().endswith(" z3") or line.strip().endswith(" z3 \\")
                   for line in workflow.splitlines() if "apt-get install" in line)


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _run_stubbed_setup(tmp_path: Path, *, with_requirements: bool) -> str:
    base = tmp_path / ("with-requirements" if with_requirements else "without-requirements")
    bin_dir = tmp_path / "bin"
    log = tmp_path / f"agent-install-{with_requirements}.log"
    script_copy = tmp_path / "repo" / "scripts" / "setup_repos.sh"
    script_copy.parent.mkdir(parents=True, exist_ok=True)
    script_copy.write_text(SETUP_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    for repo in ("mumei", "mumei-lean", "mumei-agent"):
        (base / repo / ".git").mkdir(parents=True)
    if with_requirements:
        (base / "mumei-agent" / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    bin_dir.mkdir(exist_ok=True)
    _write_executable(bin_dir / "git", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(bin_dir / "cargo", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(bin_dir / "lake", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(bin_dir / "python", f'''#!/usr/bin/env bash
if [[ "${{1:-}}" == "-m" && "${{2:-}}" == "venv" ]]; then
  target="$3"
  mkdir -p "$target/bin"
  cat > "$target/bin/python" <<'PYEOF'
#!/usr/bin/env bash
echo "agent-python $*" >> {shlex.quote(str(log))}
exit 0
PYEOF
  chmod +x "$target/bin/python"
  exit 0
fi
exit 3
''')
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    result = subprocess.run(
        ["bash", str(script_copy), "--base-dir", str(base)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return log.read_text(encoding="utf-8")


def test_setup_repos_selects_editable_install_without_requirements(tmp_path: Path) -> None:
    output = _run_stubbed_setup(tmp_path, with_requirements=False)
    assert "agent-python -m pip install -e .[test]" in output
    assert "agent-python -m pip install -r requirements.txt" not in output


def test_setup_repos_selects_requirements_install_when_present(tmp_path: Path) -> None:
    output = _run_stubbed_setup(tmp_path, with_requirements=True)
    assert "agent-python -m pip install -r requirements.txt" in output
    assert "agent-python -m pip install -e .[test]" not in output
