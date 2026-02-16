# Agent Performance Review v1.0.0

First stable public release.

## Highlights

- Local-first agent accountability skill for OpenClaw.
- Weekly visual report card with cost, task outcomes, autonomous behavior, skills usage, and system health.
- Daily standup mode for concise operational updates.
- Actionable improvement plan suggestions linked to concrete config changes.
- Deterministic sample card generation (`--seed`) and fixture-backed CI tests.

## Technical details

- `scripts/analyze.sh`: JSONL parser and metric aggregation pipeline.
- `scripts/generate-card.py`: 1200x1800 PNG renderer.
- `references/roasts.json`, `references/recommendations.json`: template + recommendation libraries.
- `.github/workflows/ci.yml`: automated test execution.
- `.github/workflows/issue-triage.yml`: security keyword triage support.

## Privacy

Everything runs locally. No telemetry or external analysis API calls.

## Known limitations

- Autonomous usefulness/risk classification is heuristic.
- Cost estimation fallback is approximate when usage-cost fields are missing.
- Trend quality improves only after multiple weekly snapshots exist.
