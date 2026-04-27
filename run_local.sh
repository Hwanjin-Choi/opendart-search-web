#!/bin/zsh

set -euo pipefail

if [[ -z "${DART_API_KEY:-}" ]]; then
  echo "DART_API_KEY environment variable is required." >&2
  exit 1
fi

export CORPCODE_XML="${CORPCODE_XML:-/Users/hwanjinchoi/Downloads/CORPCODE.xml}"
export PORT="${PORT:-8765}"

exec python3 "/Users/hwanjinchoi/Documents/opendart-search-web/server.py"
