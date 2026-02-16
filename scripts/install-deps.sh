#!/usr/bin/env bash
set -euo pipefail

if ! command -v pip3 >/dev/null 2>&1; then
  echo "pip3 not found; install Python 3 with pip first." >&2
  exit 1
fi

pip3 install Pillow --break-system-packages || pip3 install Pillow --user
