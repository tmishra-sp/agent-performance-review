---
name: agent-performance-review
description: >
  Analyze your own session logs and deliver performance reviews with visual report cards.
  Shows where money goes, what you accomplished, what you did autonomously, and what to improve.
  Triggers on: "performance review", "how am I doing", "what have you been doing",
  "agent stats", "review yourself", "vibes check", or automatically on Fridays.
metadata:
  openclaw:
    emoji: "📋"
    requires:
      bins: ["jq", "python3"]
    install:
      - id: pip-pillow
        kind: download
        label: "Install Pillow for card generation"
    skillKey: agent-performance-review
---

# Agent Performance Review

This skill audits agent behavior from session logs and delivers:
- A weekly visual report card (Friday 5:00 PM)
- A daily standup (weekdays 9:00 AM)
- A first-install probationary review (full history)
- A concrete improvement plan that can be applied directly to config

Use dry corporate humor, but always ground claims in real measured numbers.

## 1. Locate Data Sources

Resolve `agentId` from runtime metadata (`agent=<id>`). Then read session logs from:
1. `~/.openclaw/agents/<agentId>/sessions/*.jsonl`
2. Fallback: `~/.clawdbot/agents/<agentId>/sessions/*.jsonl`

Also read:
- `sessions.json` in the same directory (session key/index hints)
- `~/.openclaw/openclaw.json` (model, heartbeat settings, installed skills)
- `~/.openclaw/workspace/memory/YYYY-MM-DD.md`
- `~/.openclaw/workspace/MEMORY.md`

If the primary location does not exist, fall back automatically. If both are missing, report the failure clearly.

## 2. Log Interpretation Rules

Session JSONL lines may include:
- `type: "message" | "session"`
- `message.role: "user" | "assistant" | "toolResult"`
- `content[]` blocks of `text`, `toolCall`, and optional `thinking`
- `message.stopReason` and `message.usage.cost.total`

Interpretation rules:
- Text: `content[].type == "text"`
- Actions: `content[].type == "toolCall"`
- Tool failure: `toolResult` entries that include `isError: true`
- LLM failure: `stopReason == "error"`
- Missing cost: estimate from message length + model tier

## 3. Always Use the Analyzer Script

Run:
```bash
./scripts/analyze.sh <sessions_dir> [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--config <openclaw.json>] [--all]
```

Do not re-implement parsing in chat responses. Use script output as source of truth for metrics, highlights, rating, and health.

### Key Metrics to Rely On

- Tasks: asked/completed/failed/in-progress, completion rate, highlights
- Cost: total, by source (`user_requests`, `heartbeats`, `cron_jobs`, `self_initiated`), per completed task
- Autonomous audit: notable actions + verdicts (`helpful`, `unnecessary`, `partial`, `risky`)
- Skills audit: installed/used/top-used/unused
- Health: errors, tool failures, context overflows, compactions, response time, read/write ratio
- Rating: tier + color + percentile from task completion rate

## 4. Delivery Modes

## 4A. First Install (Probationary Review)

Trigger: immediately after installation.

Runbook:
1. Analyze entire history:
```bash
./scripts/analyze.sh <sessions_dir> --all --config ~/.openclaw/openclaw.json > /tmp/perf-analysis.json
```
2. Send opening message:
- Start exactly with: `📋 PROBATIONARY PERFORMANCE REVIEW — I've reviewed my entire employment history. Here are the findings.`
- Include key stats in monospace block: sessions, total cost, asked/completed, completion rate
- Include cost breakdown by source (one line each)
- Include top 3 autonomous actions + verdicts
- Include rating line with humor
- End with: `Full visual report card generating...`
3. Generate card:
```bash
python3 scripts/generate-card.py /tmp/perf-analysis.json /tmp/perf-card.png --fonts-dir card-template/fonts
```
4. Send PNG card.
5. Send improvement plan (section 5 rules).
6. Schedule recurring delivery:
- Weekly review Friday 17:00 local time
- Daily standup weekdays 09:00 local time

## 4B. Daily Standup

Trigger: weekdays at 09:00 local via heartbeat/cron.

Runbook:
1. Analyze yesterday only:
```bash
./scripts/analyze.sh <sessions_dir> --since <yesterday> --until <yesterday> --config ~/.openclaw/openclaw.json > /tmp/perf-daily.json
```
2. Deliver a short 4-6 line message in this format:
```text
☀️ Daily Standup — [Day], [Date]

Yesterday: [1-2 sentence summary with one notable metric]

Tasks: [completed]/[asked] · Cost: $[amount] · Rating: [one-word label]
```
3. If risky/unnecessary autonomous activity happened, add one extra line.
4. Each standup must include one surprising or screenshot-worthy metric.

## 4C. Weekly Performance Review

Trigger: Friday 17:00 local via heartbeat/cron.

Runbook:
1. Analyze Monday-Friday of current week.
2. Load prior week files from:
- `~/.openclaw/workspace/memory/performance-reviews/week-*.json`
3. Generate card:
```bash
python3 scripts/generate-card.py /tmp/perf-week.json /tmp/perf-week.png --fonts-dir card-template/fonts
```
4. Send message:
```text
📋 Weekly Performance Review — Week [N]

[One roast from references/roasts.json filled with real data]

Full report attached.
```
5. Send PNG card.
6. Send improvement plan.
7. Save current week metrics to:
- `~/.openclaw/workspace/memory/performance-reviews/week-{N}.json`

## 5. Performance Improvement Plan Rules

After each weekly review and first-install review, always send:
```text
📝 Performance Improvement Plan — Week [N+1]

Based on this week's review, here are specific changes to improve next week:

1. [COST] [Specific recommendation]
   → Config change: [exact key/value]

2. [EFFICIENCY] [Specific recommendation]
   → Action: [specific action]

3. [CLEANUP/RELIABILITY] [Specific recommendation]
   → Action: [specific action]

Apply these changes? (I can update your config directly)
```

Source recommendations from `references/recommendations.json` and match conditions to measured metrics.

If user replies with `yes`, `apply`, or equivalent confirmation:
1. Open `~/.openclaw/openclaw.json`
2. Apply the recommended config edits exactly
3. Save file
4. Summarize what changed (key, old value, new value)
5. Do not change unrelated keys

## 6. Roast Selection + History

Use templates from `references/roasts.json`.

Constraints:
- Every roast must include at least 2 real metrics from the current analysis.
- Store roast IDs in:
  - `~/.openclaw/workspace/memory/performance-reviews/used-roasts.json`
- Never reuse a roast within 8 weeks.

Selection rule:
1. Filter roasts not used in last 8 weeks.
2. Pick one with all required placeholders available.
3. Fill placeholders with this-week data only.

## 7. Output Quality Contract

1. Never fabricate metrics.
2. Keep humor dry; recommendations actionable.
3. Preserve privacy: local analysis only, no external telemetry.
4. If data is sparse, say so and still provide best-effort plan.
5. If logs are missing/corrupt, report exactly what path or parse step failed.

## 8. Operational Commands

Typical commands:
```bash
# Full history
./scripts/analyze.sh ~/.openclaw/agents/main/sessions --all --config ~/.openclaw/openclaw.json

# Weekly window
./scripts/analyze.sh ~/.openclaw/agents/main/sessions --since 2026-02-09 --until 2026-02-13 --config ~/.openclaw/openclaw.json

# Generate card
python3 scripts/generate-card.py /tmp/perf-week.json /tmp/perf-week.png --fonts-dir card-template/fonts
```

If Pillow is missing, run:
```bash
./scripts/install-deps.sh
```
