#!/usr/bin/env bash
set -euo pipefail

# Run every scenario except the template.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for scenario_dir in "$ROOT_DIR"/scenarios/*; do
  [[ -d "$scenario_dir" ]] || continue
  name="$(basename "$scenario_dir")"
  [[ "$name" == "_template" ]] && continue
  "$ROOT_DIR/scripts/run_scenario.sh" "$name" "$@"
done
