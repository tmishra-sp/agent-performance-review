#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

./tests/run.sh

python3 scripts/generate-card.py examples/sample-analysis.json examples/sample-card.png --fonts-dir card-template/fonts --seed 7

python3 - <<'PY'
from PIL import Image
from pathlib import Path
p = Path('examples/sample-card.png')
img = Image.open(p)
if img.size != (1200, 1800):
    raise SystemExit(f"Invalid sample card dimensions: {img.size}")
size_kb = p.stat().st_size / 1024
if size_kb > 500:
    raise SystemExit(f"Sample card too large: {size_kb:.1f}KB (target <= 500KB)")
print(f"sample-card.png ok: {img.size}, {size_kb:.1f}KB")
PY

jq empty references/roasts.json references/recommendations.json examples/sample-analysis.json >/dev/null

echo "Release preflight passed."
