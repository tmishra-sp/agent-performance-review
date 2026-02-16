#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found; install Python 3.10+ first." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REQ_FILE="$ROOT/requirements.txt"

if [[ ! -f "$REQ_FILE" ]]; then
  echo "requirements.txt not found: $REQ_FILE" >&2
  exit 1
fi

if ! python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
then
  echo "python3 must be >= 3.10 (current: $(python3 -V 2>&1))." >&2
  echo "Install and use Python 3.11+ (for example via Homebrew: /opt/homebrew/bin/python3.11)." >&2
  exit 1
fi

python3 -m pip install -r "$REQ_FILE" --break-system-packages || python3 -m pip install -r "$REQ_FILE" --user
