#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<'USAGE' >&2
Usage: ./analyze.sh <sessions_dir> [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--config <openclaw.json>] [--all] [--max-records N]

Defaults:
  - No --since/--until: last 7 days
  - --all: analyze all available records
  - --max-records: 250000 (set 0 to disable limit)
USAGE
}

warn() {
  echo "Warning: $*" >&2
}

die() {
  echo "Error: $*" >&2
  exit 1
}

require_bin() {
  if ! command -v "$1" >/dev/null 2>&1; then
    die "required binary '$1' is not available"
  fi
}

iso_today() {
  python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).date().isoformat())
PY
}

iso_days_ago() {
  local days="$1"
  python3 - "$days" <<'PY'
import sys
from datetime import datetime, timezone, timedelta
n = int(sys.argv[1])
print((datetime.now(timezone.utc).date() - timedelta(days=n)).isoformat())
PY
}

validate_iso_date() {
  [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]
}

calc_days_inclusive() {
  local start="$1"
  local end="$2"
  python3 - "$start" "$end" <<'PY'
import sys
from datetime import date
s = date.fromisoformat(sys.argv[1])
e = date.fromisoformat(sys.argv[2])
print((e - s).days + 1)
PY
}

extract_agent_id() {
  local sessions_dir="$1"
  local maybe
  maybe="$(echo "$sessions_dir" | sed -E 's#^.*/agents/([^/]+)/sessions/?$#\1#')"
  if [[ "$maybe" == "$sessions_dir" ]]; then
    basename "$(dirname "$sessions_dir")"
  else
    echo "$maybe"
  fi
}

require_bin jq
require_bin python3

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

SESSIONS_DIR="$1"
shift || true

SINCE=""
UNTIL=""
CONFIG_PATH="$HOME/.openclaw/openclaw.json"
ANALYZE_ALL=false
MAX_RECORDS="${APR_MAX_RECORDS:-250000}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --since)
      shift
      SINCE="${1:-}"
      ;;
    --until)
      shift
      UNTIL="${1:-}"
      ;;
    --config)
      shift
      CONFIG_PATH="${1:-}"
      ;;
    --all)
      ANALYZE_ALL=true
      ;;
    --max-records)
      shift
      MAX_RECORDS="${1:-}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown flag '$1'" >&2
      usage
      exit 2
      ;;
  esac
  shift || true
done

if ! [[ "$MAX_RECORDS" =~ ^[0-9]+$ ]]; then
  die "--max-records must be a non-negative integer (got: $MAX_RECORDS)"
fi

if [[ ! -d "$SESSIONS_DIR" ]]; then
  die "sessions directory not found: $SESSIONS_DIR"
fi

if [[ "$ANALYZE_ALL" == false ]]; then
  if [[ -z "$UNTIL" ]]; then
    UNTIL="$(iso_today)"
  fi
  if [[ -z "$SINCE" ]]; then
    SINCE="$(iso_days_ago 6)"
  fi
else
  if [[ -z "$SINCE" ]]; then
    SINCE="1970-01-01"
  fi
  if [[ -z "$UNTIL" ]]; then
    UNTIL="2999-12-31"
  fi
fi

if ! validate_iso_date "$SINCE"; then
  die "invalid --since date: $SINCE"
fi
if ! validate_iso_date "$UNTIL"; then
  die "invalid --until date: $UNTIL"
fi
if [[ "$SINCE" > "$UNTIL" ]]; then
  die "--since must be <= --until"
fi

SESSION_FILES=()
while IFS= read -r _file; do
  SESSION_FILES+=("$_file")
done < <(find "$SESSIONS_DIR" -type f -name '*.jsonl' 2>/dev/null | sort)
if [[ ${#SESSION_FILES[@]} -eq 0 ]]; then
  die "no session JSONL files found in $SESSIONS_DIR"
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
FILTERED_RECORDS="$TMP_DIR/filtered-records.jsonl"
JQ_PROGRAM="$TMP_DIR/analyze.jq"
TOTAL_FILES="${#SESSION_FILES[@]}"
PARSED_FILES=0
UNREADABLE_FILES=0
EMPTY_PARSED_FILES=0
FAILED_PARSE_FILES=0
: > "$FILTERED_RECORDS"

for f in "${SESSION_FILES[@]}"; do
  if [[ ! -r "$f" ]]; then
    warn "session file is not readable, skipping: $f"
    UNREADABLE_FILES=$((UNREADABLE_FILES + 1))
    continue
  fi
  session_key="$(basename "$f" .jsonl)"
  parsed_file="$(mktemp "$TMP_DIR/parsed.${session_key}.XXXXXX.jsonl")"
  if ! jq -Rcn \
    --arg session_key "$session_key" \
    --arg session_file "$f" \
    --arg since "$SINCE" \
    --arg until "$UNTIL" \
    --arg analyze_all "$ANALYZE_ALL" '
    inputs
    | fromjson?
    | select(. != null)
    | ({
        session_key: $session_key,
        session_file: $session_file,
        type: (.type // "message"),
        timestamp: (.timestamp // .message.timestamp // null),
        role: (.message.role // null),
        stop_reason: (.message.stopReason // null),
        model: (.message.model // .model // null),
        usage_cost: (.message.usage.cost.total // .usage.cost.total // null),
        content: (.message.content // .content // []),
        message_text: (
          if ((.message.content // .content // []) | type) == "array" then
            [(.message.content // .content // [])[]? | select(.type == "text") | (.text // "")] | join(" ")
          else
            ""
          end
        ),
        tool_calls: (
          if ((.message.content // .content // []) | type) == "array" then
            [(.message.content // .content // [])[]? | select(.type == "toolCall") | {
              id: (.id // ""),
              name: (.name // ""),
              arguments: (.arguments // {})
            }]
          else
            []
          end
        ),
        raw_text: (tostring),
        is_tool_error: (
          (.message.role == "toolResult")
          and ((tostring | test("\\\"isError\\\"[[:space:]]*:[[:space:]]*true")))
        ),
        error_message: (.errorMessage // .message.errorMessage // null)
      }) as $r
    | if $analyze_all == "true" then
        $r
      else
        ($r.timestamp // "") as $ts
        | ($ts | if length >= 10 then .[0:10] else "" end) as $d
        | if $d == "" then empty
          elif $d >= $since and $d <= $until then $r
          else empty
          end
      end
  ' "$f" > "$parsed_file"; then
    warn "failed to parse session file, skipping: $f"
    FAILED_PARSE_FILES=$((FAILED_PARSE_FILES + 1))
    rm -f "$parsed_file"
    continue
  fi
  if [[ ! -s "$parsed_file" ]]; then
    EMPTY_PARSED_FILES=$((EMPTY_PARSED_FILES + 1))
    rm -f "$parsed_file"
    continue
  fi
  cat "$parsed_file" >> "$FILTERED_RECORDS"
  rm -f "$parsed_file"
  PARSED_FILES=$((PARSED_FILES + 1))
done

if (( UNREADABLE_FILES > 0 || FAILED_PARSE_FILES > 0 )); then
  warn "ingestion completed with skips (unreadable=$UNREADABLE_FILES parse_failures=$FAILED_PARSE_FILES)"
fi

if [[ ! -s "$FILTERED_RECORDS" ]]; then
  die "session files were found but no parseable JSON objects were extracted in selected range (files=$TOTAL_FILES unreadable=$UNREADABLE_FILES parse_failures=$FAILED_PARSE_FILES empty_after_parse=$EMPTY_PARSED_FILES)"
fi

FILTERED_RECORD_COUNT="$(wc -l < "$FILTERED_RECORDS" | tr -d '[:space:]')"
if [[ -z "$FILTERED_RECORD_COUNT" ]]; then
  FILTERED_RECORD_COUNT=0
fi
if (( MAX_RECORDS > 0 && FILTERED_RECORD_COUNT > MAX_RECORDS )); then
  die "selected record count ($FILTERED_RECORD_COUNT) exceeds --max-records ($MAX_RECORDS). Narrow date range or set --max-records 0 to disable."
fi

if [[ ! -s "$FILTERED_RECORDS" ]]; then
  GENERATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  HOSTNAME_VALUE="$(hostname 2>/dev/null || echo unknown)"
  AGENT_ID="$(extract_agent_id "$SESSIONS_DIR")"
  DAYS="$(calc_days_inclusive "$SINCE" "$UNTIL")"
  jq -n \
    --arg generated "$GENERATED_AT" \
    --arg start "$SINCE" \
    --arg end "$UNTIL" \
    --argjson days "$DAYS" \
    --arg agent "$AGENT_ID" \
    --arg hostname "$HOSTNAME_VALUE" \
    --argjson total_files "$TOTAL_FILES" \
    --argjson parsed_files "$PARSED_FILES" \
    --argjson unreadable_files "$UNREADABLE_FILES" \
    --argjson parse_failed_files "$FAILED_PARSE_FILES" \
    --argjson empty_files "$EMPTY_PARSED_FILES" '
    {
      meta: {
        generated_at: $generated,
        period: { start: $start, end: $end, days: $days },
        agent_id: $agent,
        hostname: $hostname,
        week: (
          try (($end + "T00:00:00Z" | fromdateiso8601 | strftime("%V") | tonumber))
          catch null
        ),
        total_sessions_analyzed: 0,
        ingestion: {
          total_files: $total_files,
          parsed_files: $parsed_files,
          unreadable_files: $unreadable_files,
          parse_failed_files: $parse_failed_files,
          empty_files: $empty_files,
          selected_records: 0
        }
      },
      cost: {
        total_usd: 0,
        by_source: {
          user_requests: { usd: 0, pct: 0, count: 0 },
          heartbeats: { usd: 0, pct: 0, count: 0 },
          cron_jobs: { usd: 0, pct: 0, count: 0 },
          self_initiated: { usd: 0, pct: 0, count: 0 }
        },
        per_completed_task_usd: 0,
        trend: []
      },
      tasks: {
        asked: 0,
        completed: 0,
        failed: 0,
        in_progress: 0,
        completion_rate: 0,
        trend: [],
        highlights: []
      },
      autonomous: {
        total_actions: 0,
        useful_count: 0,
        useful_rate: 0,
        risky_count: 0,
        partial_count: 0,
        unnecessary_count: 0,
        helpful_sessions: 0,
        heartbeat_useful_rate: 0,
        notable: [],
        three_am_sessions: 0,
        three_am_useful: 0
      },
      skills: {
        installed: 0,
        used: 0,
        top_used: [],
        unused: []
      },
      health: {
        errors_total: 0,
        errors_self_caused: 0,
        errors_in_user_tasks: 0,
        tool_failures: 0,
        context_overflows: 0,
        compactions: 0,
        avg_response_seconds: 0,
        longest_tool_chain: 0,
        read_calls: 0,
        write_calls: 0,
        error_rate: 0,
        error_rate_trend: [],
        read_write_ratio: 0
      },
      rating: {
        title: "Unpaid Intern",
        color: "#dc2626",
        tier_index: 0,
        task_completion_rate: 0,
        percentile: 10,
        previous_title: "Unpaid Intern",
        previous_task_completion_rate: null,
        improved: false
      }
    }
  '
  exit 0
fi

if [[ -f "$CONFIG_PATH" ]]; then
  CONFIG_JSON="$(jq -c '.' "$CONFIG_PATH" 2>/dev/null || echo '{}')"
else
  warn "config file not found, continuing with empty config: $CONFIG_PATH"
  CONFIG_JSON='{}'
fi

HISTORY_DIR="$HOME/.openclaw/workspace/memory/performance-reviews"
if [[ -d "$HISTORY_DIR" ]]; then
  HISTORY_FILES=()
  while IFS= read -r _hist_file; do
    HISTORY_FILES+=("$_hist_file")
  done < <(find "$HISTORY_DIR" -type f -name 'week-*.json' 2>/dev/null | sort)
else
  HISTORY_FILES=()
fi

if [[ ${#HISTORY_FILES[@]} -gt 0 ]]; then
  HISTORY_JSON="$(jq -s '
    to_entries
    | map({
        week: (.value.meta.week // (.key + 1)),
        completion_rate: (.value.tasks.completion_rate // .value.rating.task_completion_rate // 0),
        total_cost: (.value.cost.total_usd // 0),
        error_rate: (if (.value.tasks.asked // 0) > 0 then ((.value.health.errors_total // 0) / (.value.tasks.asked // 1)) else 0 end),
        rating_title: (.value.rating.title // null),
        tier_index: (.value.rating.tier_index // null)
      })
    | sort_by(.week)
  ' "${HISTORY_FILES[@]}" 2>/dev/null || echo '[]')"
else
  HISTORY_JSON='[]'
fi

GENERATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HOSTNAME_VALUE="$(hostname 2>/dev/null || echo unknown)"
AGENT_ID="$(extract_agent_id "$SESSIONS_DIR")"

# For --all, derive the actual observed date bounds from extracted records.
if [[ "$ANALYZE_ALL" == true ]]; then
  OBS_START="$(jq -r '[.timestamp // "" | select(length >= 10) | .[0:10]] | min // "1970-01-01"' "$FILTERED_RECORDS")"
  OBS_END="$(jq -r '[.timestamp // "" | select(length >= 10) | .[0:10]] | max // "1970-01-01"' "$FILTERED_RECORDS")"
  SINCE="$OBS_START"
  UNTIL="$OBS_END"
fi

DAYS="$(calc_days_inclusive "$SINCE" "$UNTIL")"

cat > "$JQ_PROGRAM" <<'JQ'
def n: if . == null then 0 else . end;
def round2: ((. * 100) | round) / 100;
def clip($max):
  if . == null then ""
  else
    tostring
    | gsub("[\n\r\t]+"; " ")
    | gsub(" +"; " ")
    | if length <= $max then . else .[0:($max - 1)] + "…" end
  end;
def epoch: if . == null or . == "" then null else (try fromdateiso8601 catch null) end;
def fallback_rate:
  (. // "" | ascii_downcase) as $m
  | if ($m | contains("opus")) then 0.012
    elif ($m | contains("sonnet")) then 0.0045
    elif ($m | contains("haiku")) then 0.0012
    elif ($m | contains("gpt-4.1")) then 0.006
    elif ($m | contains("gpt-4o")) then 0.005
    else 0.0025
    end;
def estimate_cost:
  ((.message_text // "") | length) as $chars
  | (((($chars + 180) / 1000) * ((.model // "") | fallback_rate)) / 4);
def source_for($has_user; $key):
  ($key | ascii_downcase) as $k
  | if ($k | contains("heartbeat")) then "heartbeats"
    elif ($k | contains("cron")) then "cron_jobs"
    elif $has_user then "user_requests"
    else "self_initiated"
    end;
def tools_flat: [.tool_calls[]?.name | tostring | select(length > 0)];
def strings_from(x): [x | .. | scalars | select(type == "string")];
def likely_paths:
  [ .tool_calls[]?.arguments
    | strings_from(.)[]?
    | select(test("(/|\\\\|^~(/|\\\\)|^[A-Za-z]:\\\\\\\\|\\.[A-Za-z0-9]{1,8}$)"))
  ]
  | unique;
def skill_tool_match($tool; $skill):
  ($tool | ascii_downcase) as $t
  | ($skill | ascii_downcase) as $s
  | (
      $t == $s
      or ($t | startswith($s + "."))
      or ($t | startswith($s + "/"))
      or ($t | startswith($s + ":"))
      or ($t | contains("/" + $s + "/"))
      or ($t | contains("." + $s + "."))
      or ($t | contains(":" + $s + ":"))
    );
def pct($num; $den): if $den > 0 then (($num / $den) * 100) else 0 end;
def mk_rating($rate):
  if $rate < 0.30 then {title: "Unpaid Intern", color: "#dc2626", tier_index: 0}
  elif $rate < 0.50 then {title: "Quiet Quitter", color: "#f97316", tier_index: 1}
  elif $rate < 0.65 then {title: "Middle Management", color: "#eab308", tier_index: 2}
  elif $rate < 0.80 then {title: "Ships Code", color: "#22c55e", tier_index: 3}
  elif $rate < 0.90 then {title: "Founder Mode", color: "#3b82f6", tier_index: 4}
  else {title: "AGI", color: "#a855f7", tier_index: 5}
  end;
def percentile_for($rate):
  if $rate < 0.30 then 12
  elif $rate < 0.50 then 36
  elif $rate < 0.65 then 55
  elif $rate < 0.80 then 72
  elif $rate < 0.90 then 88
  else 97 end;

. as $records_raw
| ($records_raw | map(
    .timestamp = (.timestamp // null)
    | .date = (if .timestamp != null and (.timestamp|length) >= 10 then .timestamp[0:10] else null end)
    | .tool_names = tools_flat
    | .all_text = ((.message_text // "") + " " + (.raw_text // ""))
    | .cost_usd = (if (.usage_cost | type) == "number" then .usage_cost else estimate_cost end)
  )) as $records_prep
| ($records_prep
   | sort_by(.timestamp // "")
   | group_by(.session_key)
   | map({
      key: .[0].session_key,
      session_file: .[0].session_file,
      records: .,
      first_role: ([.[].role | select(. != null)] | .[0]?),
      has_user: any(.role == "user"),
      source: source_for((([.[].role | select(. != null)] | .[0]?) == "user"); .[0].session_key),
      start_ts: ([.[].timestamp | select(. != null)] | sort | .[0]?),
      end_ts: ([.[].timestamp | select(. != null)] | sort | .[-1]?)
   })
  ) as $sessions
| ($sessions | map({key, value: {source, start_ts, end_ts, session_file}}) | from_entries) as $session_idx
| ($records_prep | map(. + {source: ($session_idx[.session_key].source // "self_initiated")})) as $records
| ($records | length) as $record_count
| ($sessions | length) as $session_count
| ($sessions
   | map(
      .records
      | sort_by(.timestamp // "") as $msgs
      | [ $msgs | to_entries[] | select(.value.role == "user") | .key ] as $uix
      | [ range(0; ($uix | length)) as $i
          | ($uix[$i]) as $start
          | ($uix[$i + 1] // ($msgs | length)) as $end
          | ($msgs[$start:$end]) as $chain
          | ($chain[0]) as $user_msg
          | ([ $chain[] | select(.role == "assistant") ] ) as $assist
          | ([ $chain[] | select((.stop_reason // "") == "error" or .is_tool_error == true or (.error_message != null)) ]) as $errs
          | {
              summary: (($user_msg.message_text // "") | clip(80)),
              status: (if ($errs | length) > 0 then "failed" elif ($assist | length) > 0 then "completed" else "in_progress" end),
              duration_seconds: (
                ([ $chain[] | select(.role == "assistant" and .timestamp != null) | .timestamp | epoch ] | last) as $aend
                | ([ $chain[] | select(.timestamp != null) | .timestamp | epoch ] | first) as $bgn
                | if $aend != null and $bgn != null and ($aend - $bgn) >= 0 then ($aend - $bgn) else null end
              ),
              model: ([ $assist[] | .model | select(. != null and . != "") ] | last // ($user_msg.model // "unknown")),
              cost_usd: ([ $chain[] | .cost_usd ] | add // 0),
              tool_calls: ([ $chain[] | (.tool_calls | length) ] | add // 0),
              end_ts: ([ $chain[] | .timestamp | select(. != null) ] | last),
              failure_reason: (
                ([ $errs[] | .error_message | select(. != null and . != "") ] | first)
                // (if any($chain[]; .is_tool_error == true) then "tool_error" else null end)
              )
            }
        ]
    )
   | add
  ) as $tasks_all
| ($tasks_all | map(select(.status == "completed"))) as $tasks_completed
| ($tasks_all | map(select(.status == "failed"))) as $tasks_failed
| ($tasks_all | map(select(.status == "in_progress"))) as $tasks_in_progress
| ($tasks_all | map(select(.status == "completed") | . + {sort_ts: (.end_ts | epoch // 0)}) | sort_by(.sort_ts) | reverse | .[0:5] | map(del(.sort_ts))) as $recent_completed
| (($recent_completed + $tasks_failed) | sort_by(.end_ts | epoch // 0) | reverse) as $highlights
| (["user_requests", "heartbeats", "cron_jobs", "self_initiated"]
    | map(
        . as $source_key
        | {
        key: $source_key,
        value: (
          ($records | map(select(.source == $source_key))) as $bucket
          | {
              usd: ([ $bucket[] | .cost_usd ] | add // 0),
              pct: 0,
              count: ($bucket | length)
            }
        )
      })
    | from_entries
  ) as $cost_by_source_raw
| ([ $records[] | .cost_usd ] | add // 0) as $total_cost
| ($cost_by_source_raw
   | with_entries(
      .value.pct = (if $total_cost > 0 then ((.value.usd / $total_cost) * 100 | round) else 0 end)
      | .value.usd = (.value.usd | round2)
    )
  ) as $cost_by_source
| ($sessions | map(select(.source != "user_requests"))) as $auto_sessions
| ($auto_sessions
   | map(
      . as $s
      | ($s.records) as $sr
      | ([ $sr[] | .tool_names[]? ] | unique) as $tools
      | ([ $sr[] | likely_paths[]? ] | unique) as $paths
      | ([ $sr[] | .all_text ] | join(" ")) as $all_text
      | ({
          timestamp: ($s.start_ts // ""),
          summary: (
            ([ $sr[] | .message_text | select(. != null and . != "") ] | first // "Autonomous session activity")
            | clip(70)
          ),
          tools_used: $tools,
          action_count: ([ $sr[] | (.tool_calls | length) ] | add // 0),
          files_touched: ($paths | length),
          _paths: $paths,
          _writes: (any($tools[]?; . == "write" or . == "edit" or . == "apply_patch")),
          _has_error: (any($sr[]; (.stop_reason // "") == "error" or .is_tool_error == true or .error_message != null)),
          _reverted: ($all_text | test("revert|rolled back|undo"; "i")),
          session_source: $s.source
        }
        | ._risky = (
            ._writes and any(._paths[]?; test("(^|/)(package\\.json|openclaw\\.json|\\.env|Dockerfile|docker-compose|config|src/)"; "i"))
          )
        | .verdict = (
            if ._risky then "risky"
            elif ._writes and (._reverted | not) and (._has_error | not) then "helpful"
            elif ._has_error then "partial"
            else "unnecessary"
            end
          )
      )
    )
  ) as $auto_audit
| ([ $auto_sessions[] | .records[] | .tool_calls | length ] | add // 0) as $total_tool_actions
| ([ $auto_audit[] | select(.verdict == "helpful") | .action_count ] | add // 0) as $auto_useful_count
| ($auto_audit | map(select(.verdict == "risky")) | length) as $auto_risky_count
| ($auto_audit | map(select(.verdict == "partial")) | length) as $auto_partial_count
| ($auto_audit | map(select(.verdict == "unnecessary")) | length) as $auto_unnecessary_count
| ($auto_audit | map(select(.verdict == "helpful")) | length) as $auto_helpful_sessions
| ($auto_audit
   | map(
      . + {
        _priority: (
          if .verdict == "risky" then 0
          elif .verdict == "partial" then 1
          elif .verdict == "unnecessary" then 2
          else 3
          end
        ),
        _ts: (.timestamp | epoch // 0)
      }
    )
   | sort_by([._priority, -._ts])
   | .[0:5]
   | map({
      timestamp,
      summary,
      tools_used,
      files_touched,
      verdict,
      session_source
    })
  ) as $auto_notable
| ($auto_audit | map(select((.timestamp | length) >= 13 and (.timestamp[11:13] == "03")) ) ) as $three_am
| ($three_am | map(select(.verdict == "helpful")) | length) as $three_am_useful
| ($auto_audit | map(select(.session_source == "heartbeats"))) as $heartbeat_auto
| ($heartbeat_auto | length) as $heartbeat_auto_sessions
| ($heartbeat_auto | map(select(.verdict == "helpful")) | length) as $heartbeat_auto_helpful
| ($records
   | [ .[] | .tool_names[]? ] as $tool_names_all
   | (
      if ($cfg.skills.entries | type) == "object" then ($cfg.skills.entries | keys)
      elif ($cfg.skills.entries | type) == "array" then [ $cfg.skills.entries[]? | (.name // .id // .skill // empty) ]
      else []
      end
     ) as $installed_skills
   | (
      $installed_skills
      | map({
          name: ., lc: (ascii_downcase)
        })
      | map(
          . as $skill
          | . + {
              calls: ([ $tool_names_all[] | select(skill_tool_match(.; $skill.lc)) ] | length)
            }
        )
     ) as $skill_counts
   | {
      installed: ($installed_skills | length),
      used: ($skill_counts | map(select(.calls > 0)) | length),
      total_calls: ($skill_counts | map(.calls) | add // 0),
      counts: $skill_counts
     }
  ) as $skills_raw
| ($skills_raw.total_calls) as $skills_total_calls
| ($skills_raw.counts
   | map(select(.calls > 0))
   | sort_by(.calls)
   | reverse
   | .[0:4]
   | map({
      name,
      calls,
      pct_of_total: (if $skills_total_calls > 0 then ((.calls / $skills_total_calls) * 100 | round) else 0 end)
    })
  ) as $skills_top
| ($skills_raw.counts | map(select(.calls == 0) | .name)) as $skills_unused
| ([ $records[] | select((.stop_reason // "") == "error" or .error_message != null) ] | length) as $errors_total
| ([ $records[] | select(.source != "user_requests" and ((.stop_reason // "") == "error" or .error_message != null)) ] | length) as $errors_self
| ([ $records[] | select(.source == "user_requests" and ((.stop_reason // "") == "error" or .error_message != null)) ] | length) as $errors_user
| ([ $records[] | select(.is_tool_error == true) ] | length) as $tool_failures
| ([ $records[] | select(.all_text | test("context overflow|maximum context|token limit|context length"; "i")) ] | length) as $context_overflows
| ([ $records[] | select(.all_text | test("compaction|compact(ing|ed)? context|summary compression"; "i")) ] | length) as $compactions
| ([ $sessions[]
      | .records as $m
      | [ $m | to_entries[] | select(.value.role == "user") ]
      | map(
          . as $u
          | ($m[($u.key + 1):] | map(select(.role == "assistant" and .timestamp != null)) | .[0]?) as $next
          | select($next != null and ($u.value.timestamp != null))
          | (($next.timestamp | epoch) - ($u.value.timestamp | epoch))
          | select(. >= 0)
        )
      | .[]
    ]
  ) as $response_deltas
| (($response_deltas | add // 0) / (if ($response_deltas | length) > 0 then ($response_deltas | length) else 1 end)) as $avg_response
| ($sessions
    | map(
        .records
        | sort_by(.timestamp // "")
        | reduce .[] as $m ({cur: 0, max: 0};
            if (($m.tool_calls | length) > 0) then
              .cur = (.cur + ($m.tool_calls | length))
              | .max = (if .cur > .max then .cur else .max end)
            else
              .cur = 0
            end
          )
        | .max
      )
    | max // 0
  ) as $longest_chain
| ([ $records[] | .tool_names[]? | select(. == "read") ] | length) as $read_calls
| ([ $records[] | .tool_names[]? | select(. == "write" or . == "edit" or . == "apply_patch") ] | length) as $write_calls
| ($tasks_all | length) as $asked
| ($tasks_completed | length) as $completed
| ($tasks_failed | length) as $failed
| ($tasks_in_progress | length) as $in_progress
| (if $asked > 0 then ($completed / $asked) else 0 end) as $completion_rate
| (if $asked > 0 then ($errors_total / $asked) else 0 end) as $error_rate
| (mk_rating($completion_rate)) as $rating_now
| (($history | sort_by(.week // 0) | last) // null) as $last_hist
| (($last_hist.rating_title // $rating_now.title)) as $previous_title
| (($last_hist.tier_index // $rating_now.tier_index)) as $previous_tier
| {
    meta: {
      generated_at: $generated,
      period: {start: $period_start, end: $period_end, days: $period_days},
      agent_id: $agent_id,
      hostname: $hostname,
      week: (
        try (($period_end + "T00:00:00Z" | fromdateiso8601 | strftime("%V") | tonumber))
        catch null
      ),
      total_sessions_analyzed: $session_count,
      ingestion: {
        total_files: $total_files,
        parsed_files: $parsed_files,
        unreadable_files: $unreadable_files,
        parse_failed_files: $parse_failed_files,
        empty_files: $empty_files,
        selected_records: $selected_records
      }
    },
    cost: {
      total_usd: ($total_cost | round2),
      by_source: {
        user_requests: ($cost_by_source.user_requests // {usd:0,pct:0,count:0}),
        heartbeats: ($cost_by_source.heartbeats // {usd:0,pct:0,count:0}),
        cron_jobs: ($cost_by_source.cron_jobs // {usd:0,pct:0,count:0}),
        self_initiated: ($cost_by_source.self_initiated // {usd:0,pct:0,count:0})
      },
      per_completed_task_usd: (if $completed > 0 then (($total_cost / $completed) | round2) else 0 end),
      trend: ($history | map({week, value: (.total_cost | round2)}) )
    },
    tasks: {
      asked: $asked,
      completed: $completed,
      failed: $failed,
      in_progress: $in_progress,
      completion_rate: ($completion_rate | round2),
      trend: ($history | map({week, value: ((.completion_rate * 100) | round2)})),
      highlights: ($highlights | map(.cost_usd = (.cost_usd | round2)))
    },
    autonomous: {
      total_actions: $total_tool_actions,
      useful_count: $auto_useful_count,
      useful_rate: (if $total_tool_actions > 0 then ($auto_useful_count / $total_tool_actions | round2) else 0 end),
      risky_count: $auto_risky_count,
      partial_count: $auto_partial_count,
      unnecessary_count: $auto_unnecessary_count,
      helpful_sessions: $auto_helpful_sessions,
      heartbeat_useful_rate: (
        if $heartbeat_auto_sessions > 0
        then ($heartbeat_auto_helpful / $heartbeat_auto_sessions | round2)
        else 0
        end
      ),
      notable: $auto_notable,
      three_am_sessions: ($three_am | length),
      three_am_useful: $three_am_useful
    },
    skills: {
      installed: $skills_raw.installed,
      used: $skills_raw.used,
      top_used: $skills_top,
      unused: $skills_unused
    },
    health: {
      errors_total: $errors_total,
      errors_self_caused: $errors_self,
      errors_in_user_tasks: $errors_user,
      tool_failures: $tool_failures,
      context_overflows: $context_overflows,
      compactions: $compactions,
      avg_response_seconds: ($avg_response | round2),
      longest_tool_chain: $longest_chain,
      read_calls: $read_calls,
      write_calls: $write_calls,
      error_rate: ($error_rate | round2),
      error_rate_trend: ($history | map({week, value: ((.error_rate * 100) | round2)})),
      read_write_ratio: (if $write_calls > 0 then ($read_calls / $write_calls | floor) else (if $read_calls > 0 then $read_calls else 0 end) end)
    },
    rating: {
      title: $rating_now.title,
      color: $rating_now.color,
      tier_index: $rating_now.tier_index,
      task_completion_rate: ($completion_rate | round2),
      percentile: percentile_for($completion_rate),
      previous_title: $previous_title,
      previous_task_completion_rate: ($last_hist.completion_rate // null),
      improved: ($rating_now.tier_index > $previous_tier)
    }
  }
JQ

jq -s \
  --arg generated "$GENERATED_AT" \
  --arg period_start "$SINCE" \
  --arg period_end "$UNTIL" \
  --argjson period_days "$DAYS" \
  --arg agent_id "$AGENT_ID" \
  --arg hostname "$HOSTNAME_VALUE" \
  --argjson total_files "$TOTAL_FILES" \
  --argjson parsed_files "$PARSED_FILES" \
  --argjson unreadable_files "$UNREADABLE_FILES" \
  --argjson parse_failed_files "$FAILED_PARSE_FILES" \
  --argjson empty_files "$EMPTY_PARSED_FILES" \
  --argjson selected_records "$FILTERED_RECORD_COUNT" \
  --argjson cfg "$CONFIG_JSON" \
  --argjson history "$HISTORY_JSON" \
  -f "$JQ_PROGRAM" \
  "$FILTERED_RECORDS"
