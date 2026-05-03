#!/usr/bin/env bash
set -euo pipefail

# Run every scenario except the template.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
status=0
passed_scenarios=()
failed_scenarios=()

for scenario_dir in "$ROOT_DIR"/scenarios/*; do
  [[ -d "$scenario_dir" ]] || continue
  name="$(basename "$scenario_dir")"
  [[ "$name" == "_template" ]] && continue

  echo "=== Running scenario: $name ==="
  if "$ROOT_DIR/scripts/run_scenario.sh" "$name" "$@"; then
    passed_scenarios+=("$name")
  else
    exit_code=$?
    failed_scenarios+=("$name")
    status=1
    echo "scenario failed: $name (exit $exit_code)" >&2
  fi
done

echo "=== Scenario summary ==="
echo "passed: ${#passed_scenarios[@]}"
for name in "${passed_scenarios[@]}"; do
  echo "  - $name"
done
echo "failed: ${#failed_scenarios[@]}"
for name in "${failed_scenarios[@]}"; do
  echo "  - $name"
done

exit "$status"
