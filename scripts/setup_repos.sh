#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/setup_repos.sh [--base-dir DIR]
# Clone or update the three demo repositories and write repos.env.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_DIR="$(cd "$ROOT_DIR/.." && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-dir)
      BASE_DIR="$(mkdir -p "$2" && cd "$2" && pwd)"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

ensure_repo() {
  local repo="$1"
  local dir="$2"
  local url="https://github.com/mumei-lang/${repo}.git"
  if [[ -d "$dir/.git" ]]; then
    echo "Updating $repo in $dir"
    git -C "$dir" pull --ff-only
  else
    echo "Cloning $repo into $dir"
    git clone "$url" "$dir"
  fi
}

MUMEI_REPO="$BASE_DIR/mumei"
MUMEI_LEAN_REPO="$BASE_DIR/mumei-lean"
MUMEI_AGENT_REPO="$BASE_DIR/mumei-agent"

ensure_repo mumei "$MUMEI_REPO"
ensure_repo mumei-lean "$MUMEI_LEAN_REPO"
ensure_repo mumei-agent "$MUMEI_AGENT_REPO"

if ! command -v z3 >/dev/null 2>&1; then
  echo "warning: z3 is not on PATH. Install Z3 or run mumei setup." >&2
fi
if [[ -z "${LLVM_SYS_170_PREFIX:-}" ]]; then
  echo "warning: LLVM_SYS_170_PREFIX is unset. Common value: /usr/lib/llvm-17" >&2
fi

echo "Building mumei"
(cd "$MUMEI_REPO" && cargo build --release)

if command -v lake >/dev/null 2>&1; then
  echo "Building mumei-lean"
  (cd "$MUMEI_LEAN_REPO" && mkdir -p generated/Generated && lake build)
else
  echo "warning: lake is not on PATH; L3 Lean steps can be skipped." >&2
fi

echo "Installing mumei-agent dependencies"
MUMEI_AGENT_PYTHON="$MUMEI_AGENT_REPO/.venv/bin/python"
(cd "$MUMEI_AGENT_REPO" && python -m venv .venv && "$MUMEI_AGENT_PYTHON" -m pip install --upgrade pip && "$MUMEI_AGENT_PYTHON" -m pip install -r requirements.txt)

cat > "$ROOT_DIR/repos.env" <<EOF
MUMEI_REPO=$MUMEI_REPO
MUMEI_LEAN_REPO=$MUMEI_LEAN_REPO
MUMEI_AGENT_REPO=$MUMEI_AGENT_REPO
MUMEI_AGENT_PYTHON=$MUMEI_AGENT_PYTHON
MUMEI_BIN=$MUMEI_REPO/target/release/mumei
EOF

echo "Wrote $ROOT_DIR/repos.env"
echo "If needed, export LLVM_SYS_170_PREFIX=/usr/lib/llvm-17 before building mumei."
