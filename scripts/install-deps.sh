#!/usr/bin/env bash
set -euo pipefail

if ! command -v pip3 >/dev/null 2>&1; then
  echo "pip3 not found; install Python 3 with pip first." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REQ_FILE="$ROOT/requirements.txt"

if [[ ! -f "$REQ_FILE" ]]; then
  echo "requirements.txt not found: $REQ_FILE" >&2
  exit 1
fi

pip3 install -r "$REQ_FILE" --break-system-packages || pip3 install -r "$REQ_FILE" --user
