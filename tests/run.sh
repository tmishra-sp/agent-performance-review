#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ANALYZER="$ROOT/scripts/analyze.sh"
CARD="$ROOT/scripts/generate-card.py"
FUZZ_ANALYZE="$ROOT/tests/fuzz_analyze.py"
FUZZ_CARD="$ROOT/tests/fuzz_card.py"
FIXTURE_SESSIONS="$ROOT/tests/fixtures/sessions"
FIXTURE_CONFIG="$ROOT/tests/fixtures/openclaw.json"
MINIMAL_ANALYSIS="$ROOT/tests/fixtures/minimal-analysis.json"
OUT_JSON="$(mktemp)"
OUT_PNG="$(mktemp /tmp/apr-card.XXXXXX).png"
OUT_PNG_MIN="$(mktemp /tmp/apr-card-min.XXXXXX).png"
INVALID_ANALYSIS="$(mktemp)"
ERR_LOG="$(mktemp)"
trap 'rm -f "$OUT_JSON" "$OUT_PNG" "$OUT_PNG_MIN" "$INVALID_ANALYSIS" "$ERR_LOG"' EXIT

bash -n "$ANALYZER"
python3 -m py_compile "$CARD"
python3 -m py_compile "$FUZZ_ANALYZE" "$FUZZ_CARD"
jq empty "$ROOT/references/roasts.json" "$ROOT/references/recommendations.json" "$ROOT/examples/sample-analysis.json"

"$ANALYZER" "$FIXTURE_SESSIONS" --since 2026-02-10 --until 2026-02-11 --config "$FIXTURE_CONFIG" > "$OUT_JSON"

jq -e '.meta.total_sessions_analyzed == 2' "$OUT_JSON" >/dev/null
jq -e '.meta.ingestion.total_files == 2 and .meta.ingestion.parsed_files == 2 and .meta.ingestion.parse_failed_files == 0' "$OUT_JSON" >/dev/null
jq -e '.tasks.asked == 2 and .tasks.completed == 1 and .tasks.failed == 1' "$OUT_JSON" >/dev/null
jq -e '.cost.total_usd > 0.25 and .cost.by_source.heartbeats.usd > 0' "$OUT_JSON" >/dev/null
jq -e '.autonomous.total_actions >= 2 and .autonomous.three_am_sessions >= 1' "$OUT_JSON" >/dev/null
jq -e '.skills.installed == 4 and .skills.used >= 2 and (.skills.unused | index("unused-skill")) != null' "$OUT_JSON" >/dev/null
jq -e '.rating.title != null and .rating.color != null' "$OUT_JSON" >/dev/null
jq -e '.health.read_calls >= 0 and .health.write_calls >= 0 and (.health.error_rate|type) == "number"' "$OUT_JSON" >/dev/null

if "$ANALYZER" "$FIXTURE_SESSIONS" --since 2026-02-10 --until 2026-02-11 --config "$FIXTURE_CONFIG" --max-records 1 > /dev/null 2>"$ERR_LOG"; then
  echo "Expected analyzer max-record guard to fail, but it succeeded." >&2
  exit 1
fi
if ! grep -Eiq "exceeds --max-records" "$ERR_LOG"; then
  echo "Expected max-record guard error message, got:" >&2
  cat "$ERR_LOG" >&2
  exit 1
fi

python3 "$CARD" "$ROOT/examples/sample-analysis.json" "$OUT_PNG" --fonts-dir "$ROOT/card-template/fonts" --seed 7
python3 - "$OUT_PNG" <<'PY'
import sys
from PIL import Image
img = Image.open(sys.argv[1])
assert img.size == (1200, 1800), img.size
PY

python3 "$CARD" "$MINIMAL_ANALYSIS" "$OUT_PNG_MIN" --fonts-dir "$ROOT/card-template/fonts" --seed 7
python3 - "$OUT_PNG_MIN" <<'PY'
import sys
from PIL import Image
img = Image.open(sys.argv[1])
assert img.size == (1200, 1800), img.size
PY

printf '{\"bad_json\": \n' > "$INVALID_ANALYSIS"
if python3 "$CARD" "$INVALID_ANALYSIS" "$OUT_PNG_MIN" --fonts-dir "$ROOT/card-template/fonts" --seed 7 > /dev/null 2>"$ERR_LOG"; then
  echo "Expected invalid JSON card generation to fail, but it succeeded." >&2
  exit 1
fi
if ! grep -Eiq "not valid JSON|analysis file" "$ERR_LOG"; then
  echo "Expected clear JSON parsing error message, got:" >&2
  cat "$ERR_LOG" >&2
  exit 1
fi

python3 "$FUZZ_ANALYZE"
python3 "$FUZZ_CARD"

echo "All tests passed."
