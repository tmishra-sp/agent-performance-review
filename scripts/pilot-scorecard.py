#!/usr/bin/env python3
"""Generate a pilot impact scorecard from two analysis JSON snapshots."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional


class ScorecardError(Exception):
    """Raised when scorecard generation cannot proceed safely."""


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(int(value))
        parsed = float(value)
        if not math.isfinite(parsed):
            return default
        return parsed
    except (TypeError, ValueError):
        return default


def as_dict(value: object) -> Dict:
    return value if isinstance(value, dict) else {}


def normalize_pct(value: object) -> float:
    parsed = safe_float(value, 0.0)
    if parsed <= 1.0:
        parsed *= 100.0
    return max(0.0, parsed)


def load_json(path: Path) -> Dict:
    if not path.exists():
        raise ScorecardError(f"analysis file does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise ScorecardError(f"analysis file is not valid JSON: {path} ({exc})") from exc
    except OSError as exc:
        raise ScorecardError(f"failed reading analysis file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScorecardError(f"analysis root must be a JSON object: {path}")
    return payload


def period_label(data: Dict) -> str:
    period = as_dict(as_dict(data.get("meta")).get("period"))
    start = str(period.get("start", "")).strip()
    end = str(period.get("end", "")).strip()
    if start and end:
        return f"{start} -> {end}"
    return "unknown"


def extract_metrics(data: Dict) -> Dict[str, float]:
    cost = as_dict(data.get("cost"))
    by_source = as_dict(cost.get("by_source"))
    heartbeats = as_dict(by_source.get("heartbeats"))

    tasks = as_dict(data.get("tasks"))
    health = as_dict(data.get("health"))
    autonomous = as_dict(data.get("autonomous"))

    asked = max(1.0, safe_float(tasks.get("asked"), 0.0))
    error_rate = safe_float(health.get("error_rate"), 0.0)
    if error_rate <= 0:
        error_rate = safe_float(health.get("errors_total"), 0.0) / asked

    return {
        "total_cost_usd": safe_float(cost.get("total_usd"), 0.0),
        "heartbeat_cost_share_pct": normalize_pct(heartbeats.get("pct")),
        "completion_rate_pct": normalize_pct(tasks.get("completion_rate")),
        "error_rate_pct": normalize_pct(error_rate),
        "autonomous_useful_rate_pct": normalize_pct(autonomous.get("useful_rate")),
    }


@dataclass
class MetricRow:
    key: str
    label: str
    unit: str
    direction: str
    baseline: float
    current: float
    delta: float
    delta_pct: Optional[float]
    improved: bool


METRICS = [
    ("total_cost_usd", "Total Cost", "usd", "lower_is_better"),
    ("heartbeat_cost_share_pct", "Heartbeat Cost Share", "pct", "lower_is_better"),
    ("completion_rate_pct", "Task Completion Rate", "pct", "higher_is_better"),
    ("error_rate_pct", "Error Rate", "pct", "lower_is_better"),
    ("autonomous_useful_rate_pct", "Autonomous Useful Rate", "pct", "higher_is_better"),
]


def build_rows(baseline: Dict[str, float], current: Dict[str, float]) -> List[MetricRow]:
    rows: List[MetricRow] = []
    for key, label, unit, direction in METRICS:
        base = safe_float(baseline.get(key), 0.0)
        curr = safe_float(current.get(key), 0.0)
        delta = curr - base
        delta_pct = None if abs(base) < 1e-9 else (delta / base) * 100.0
        improved = curr < base if direction == "lower_is_better" else curr > base
        rows.append(
            MetricRow(
                key=key,
                label=label,
                unit=unit,
                direction=direction,
                baseline=base,
                current=curr,
                delta=delta,
                delta_pct=delta_pct,
                improved=improved,
            )
        )
    return rows


def summarize(rows: List[MetricRow]) -> Dict[str, object]:
    improved = sum(1 for row in rows if row.improved)
    total = max(1, len(rows))
    score = int(round((improved / total) * 100))
    if score >= 80:
        verdict = "strong_improvement"
    elif score >= 60:
        verdict = "improving"
    elif score >= 40:
        verdict = "mixed"
    else:
        verdict = "regressing"
    return {
        "improved_metrics": improved,
        "total_metrics": len(rows),
        "score": score,
        "verdict": verdict,
    }


def fmt_value(value: float, unit: str) -> str:
    if unit == "usd":
        return f"${value:,.2f}"
    return f"{value:.1f}%"


def fmt_delta(value: float, unit: str) -> str:
    sign = "+" if value >= 0 else "-"
    abs_v = abs(value)
    if unit == "usd":
        return f"{sign}${abs_v:,.2f}"
    return f"{sign}{abs_v:.1f}pp"


def fmt_delta_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):.1f}%"


def to_markdown(payload: Dict[str, object]) -> str:
    baseline = as_dict(payload.get("baseline"))
    current = as_dict(payload.get("current"))
    summary = as_dict(payload.get("summary"))
    metrics = payload.get("metrics", [])
    lines = [
        "# Pilot Impact Scorecard",
        "",
        f"- Baseline window: {baseline.get('period', 'unknown')}",
        f"- Current window: {current.get('period', 'unknown')}",
        (
            f"- Score: {summary.get('score', 0)}/100 "
            f"({summary.get('improved_metrics', 0)}/{summary.get('total_metrics', 0)} metrics improved)"
        ),
        f"- Verdict: `{summary.get('verdict', 'mixed')}`",
        "",
        "| Metric | Baseline | Current | Delta | Delta % | Direction | Status |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for metric in metrics:
        row = as_dict(metric)
        unit = str(row.get("unit", "pct"))
        status = "improved" if row.get("improved") else "not improved"
        lines.append(
            "| "
            f"{row.get('label', 'Metric')} | "
            f"{fmt_value(safe_float(row.get('baseline')), unit)} | "
            f"{fmt_value(safe_float(row.get('current')), unit)} | "
            f"{fmt_delta(safe_float(row.get('delta')), unit)} | "
            f"{fmt_delta_pct(row.get('delta_pct'))} | "
            f"{row.get('direction', 'n/a')} | "
            f"{status} |"
        )
    lines.append("")
    return "\n".join(lines)


def build_payload(baseline_path: Path, current_path: Path) -> Dict[str, object]:
    baseline_data = load_json(baseline_path)
    current_data = load_json(current_path)

    baseline_metrics = extract_metrics(baseline_data)
    current_metrics = extract_metrics(current_data)
    rows = build_rows(baseline_metrics, current_metrics)
    summary = summarize(rows)

    return {
        "baseline": {"path": str(baseline_path), "period": period_label(baseline_data)},
        "current": {"path": str(current_path), "period": period_label(current_data)},
        "summary": summary,
        "metrics": [asdict(row) for row in rows],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a pilot before/after impact scorecard.")
    parser.add_argument("baseline_json", type=Path, help="Baseline analysis JSON file")
    parser.add_argument("current_json", type=Path, help="Current analysis JSON file")
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument("--output", type=Path, default=None, help="Write output to file instead of stdout")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_payload(args.baseline_json, args.current_json)
    if args.format == "json":
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    else:
        text = to_markdown(payload)

    if args.output is None:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ScorecardError(f"failed writing output file {args.output}: {exc}") from exc


if __name__ == "__main__":
    try:
        main()
    except ScorecardError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        print("Error: scorecard generation interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:  # pragma: no cover - defensive catch-all for CLI UX
        print(f"Error: unexpected failure while generating scorecard: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
