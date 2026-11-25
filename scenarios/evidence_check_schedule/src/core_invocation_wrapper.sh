#!/bin/sh
set -u
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"$dir/real-core" "$@"
rc=$?
printf '%s\n' core-invoked >> "$dir/core_invocations.log"
exit "$rc"
