#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="$(mktemp "${TMPDIR:-/tmp}/livekit_ice_transport.XXXXXX")"
trap 'rm -f "$output"' EXIT
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  -I components/livekit/core tests/ice_candidate_transport_test.c -o "$output"
"$output"
