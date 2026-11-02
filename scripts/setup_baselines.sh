#!/usr/bin/env bash
# Install the pinned baseline analyzers used by scripts/run_baselines.py into
# .cache/baselines (gitignored): a venv with semgrep, bandit, slither and
# solc (via solc-select), gosec in gobin, the pinned Rust toolchain with clippy
# (via rustup), and a semgrep-rules checkout at the pinned commit.
set -euo pipefail
cd "$(dirname "$0")/.."
read_pin() { python3 -c "import re,sys; print(re.search(sys.argv[1] + r' = \"([^\"]+)\"', open('scripts/run_baselines.py').read()).group(1))" "$1"; }
SEMGREP_VERSION=$(read_pin SEMGREP_VERSION)
BANDIT_VERSION=$(read_pin BANDIT_VERSION)
RULES_COMMIT=$(read_pin SEMGREP_RULES_COMMIT)
GOSEC_VERSION=$(read_pin GOSEC_VERSION)
SLITHER_VERSION=$(read_pin SLITHER_VERSION)
SOLC_VERSION=$(read_pin SOLC_VERSION)
RUST_TOOLCHAIN=$(read_pin RUST_TOOLCHAIN)
CACHE=.cache/baselines
mkdir -p "$CACHE"
[ -x "$CACHE/venv/bin/python" ] || python3 -m venv "$CACHE/venv"
"$CACHE/venv/bin/pip" install --quiet --disable-pip-version-check \
  "semgrep==$SEMGREP_VERSION" "bandit==$BANDIT_VERSION" \
  "slither-analyzer==$SLITHER_VERSION" "solc-select==1.2.0"
VIRTUAL_ENV="$PWD/$CACHE/venv" "$CACHE/venv/bin/solc-select" install "$SOLC_VERSION" >/dev/null
if command -v go >/dev/null; then
  GOBIN="$PWD/$CACHE/gobin" go install "github.com/securego/gosec/v2/cmd/gosec@v$GOSEC_VERSION"
else
  echo "warning: go not on PATH; gosec not installed" >&2
fi
if command -v rustup >/dev/null; then
  rustup toolchain install "$RUST_TOOLCHAIN" --profile minimal --component clippy >/dev/null 2>&1
else
  echo "warning: rustup not on PATH; clippy toolchain $RUST_TOOLCHAIN not installed" >&2
fi
RULES="$CACHE/semgrep-rules"
if [ ! -d "$RULES/.git" ]; then
  git clone --quiet --filter=blob:none https://github.com/semgrep/semgrep-rules "$RULES"
fi
if [ "$(git -C "$RULES" rev-parse HEAD)" != "$RULES_COMMIT" ]; then
  git -C "$RULES" fetch --quiet origin "$RULES_COMMIT"
  git -C "$RULES" checkout --quiet --detach "$RULES_COMMIT"
fi
echo "semgrep $SEMGREP_VERSION, bandit $BANDIT_VERSION, slither $SLITHER_VERSION (solc $SOLC_VERSION), gosec $GOSEC_VERSION, clippy (Rust $RUST_TOOLCHAIN), semgrep-rules ${RULES_COMMIT:0:12} ready in $CACHE"
