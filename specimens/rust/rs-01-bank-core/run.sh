#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

cargo build --release 2>/dev/null
BIN=target/release/bank-core
STATE=$(mktemp)
trap 'rm -f "$STATE"' EXIT

$BIN --state "$STATE" open alice 10000 1000
$BIN --state "$STATE" open bob 5000 1000
$BIN --state "$STATE" deposit alice 2500
$BIN --state "$STATE" transfer alice bob 800
$BIN --state "$STATE" settle
$BIN --state "$STATE" fee bob 100
$BIN --state "$STATE" interest alice
$BIN --state "$STATE" split 1000 carol dave
$BIN --state "$STATE" statement alice
