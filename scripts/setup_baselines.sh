#!/usr/bin/env bash
# Install the pinned baseline analyzers used by scripts/run_baselines.py into
# .cache/baselines (gitignored): a venv with semgrep and bandit, and a
# semgrep-rules checkout at the pinned commit.
set -euo pipefail
cd "$(dirname "$0")/.."
read_pin() { python3 -c "import re,sys; print(re.search(sys.argv[1] + r' = \"([^\"]+)\"', open('scripts/run_baselines.py').read()).group(1))" "$1"; }
SEMGREP_VERSION=$(read_pin SEMGREP_VERSION)
BANDIT_VERSION=$(read_pin BANDIT_VERSION)
RULES_COMMIT=$(read_pin SEMGREP_RULES_COMMIT)
CACHE=.cache/baselines
mkdir -p "$CACHE"
[ -x "$CACHE/venv/bin/python" ] || python3 -m venv "$CACHE/venv"
"$CACHE/venv/bin/pip" install --quiet --disable-pip-version-check \
  "semgrep==$SEMGREP_VERSION" "bandit==$BANDIT_VERSION"
RULES="$CACHE/semgrep-rules"
if [ ! -d "$RULES/.git" ]; then
  git clone --quiet --filter=blob:none https://github.com/semgrep/semgrep-rules "$RULES"
fi
if [ "$(git -C "$RULES" rev-parse HEAD)" != "$RULES_COMMIT" ]; then
  git -C "$RULES" fetch --quiet origin "$RULES_COMMIT"
  git -C "$RULES" checkout --quiet --detach "$RULES_COMMIT"
fi
echo "semgrep $SEMGREP_VERSION, bandit $BANDIT_VERSION, semgrep-rules ${RULES_COMMIT:0:12} ready in $CACHE"
