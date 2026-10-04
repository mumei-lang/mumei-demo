#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.foundry/bin:$PATH"
forge build
forge test --match-contract HappyPath -vv
echo "happy path OK"
