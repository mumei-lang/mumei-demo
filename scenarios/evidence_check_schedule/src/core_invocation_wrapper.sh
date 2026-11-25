#!/bin/sh
set -eu
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
printf '%s\n' core-invoked >> "$dir/core_invocations.log"
exec "$dir/real-core" "$@"
