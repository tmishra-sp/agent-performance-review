#!/usr/bin/env python3
"""Render an Agent Performance Review card from analysis JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1200
HEIGHT = 1800

BG = "#0b0d12"
TEXT_BRIGHT = "#e8eaf0"
TEXT_MED = "#8a8fa0"
TEXT_DIM = "#555a68"
TEXT_VERY_DIM = "#3d4250"
DIVIDER = "#1a1d26"
WELL_BG = "#10131a"

CATEGORY_COLORS = {
    "COST": "#22c55e",
    "EFFICIENCY": "#3b82f6",
    "CLEANUP": "#f97316",
    "RELIABILITY": "#dc2626",
}

SOURCE_COLORS = {
    "user_requests": "#22c55e",
    "heartbeats": "#f97316",
    "cron_jobs": "#3b82f6",
    "self_initiated": "#a855f7",
}

RATING_SCALE = [
    ("Unpaid Intern", "#dc2626"),
    ("Quiet Quitter", "#f97316"),
    ("Middle Management", "#eab308"),
    ("Ships Code", "#22c55e"),
    ("Founder Mode", "#3b82f6"),
    ("AGI", "#a855f7"),
]


class CardGenerationError(Exception):
    """Raised when card generation cannot proceed safely."""


def warn(msg: str) -> None:
    print(f"Warning: {msg}", file=sys.stderr)


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(int(value))
        v = float(value)
        if not math.isfinite(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_text(value: object, default: str = "", max_len: int = 240) -> str:
    if value is None:
        text = default
    elif isinstance(value, str):
        text = value
    elif isinstance(value, (dict, list, tuple, set)):
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            text = str(value)
    else:
        text = str(value)
    text = text.replace("\x00", " ").strip()
    if not text:
        text = default
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def safe_color(value: object, default: str) -> str:
    text = safe_text(value, default=default, max_len=16)
    if re.fullmatch(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})", text):
        return text
    return default


def as_dict(value: object, label: str) -> Dict:
    if isinstance(value, dict):
        return value
    if value is not None:
        warn(f"Expected object for '{label}', got {type(value).__name__}; using empty object.")
    return {}


def as_list(value: object, label: str) -> List:
    if isinstance(value, list):
        return value
    if value is not None:
        warn(f"Expected list for '{label}', got {type(value).__name__}; using empty list.")
    return []


def load_json(path: Path) -> Dict:
    if not path.exists():
        raise CardGenerationError(f"analysis file does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise CardGenerationError(f"analysis file is not valid JSON: {path} ({exc})") from exc
    except OSError as exc:
        raise CardGenerationError(f"failed reading analysis file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CardGenerationError(f"analysis root must be a JSON object: {path}")
    return data


def normalize_analysis(data: Dict) -> Dict:
    out = dict(data)
    out["meta"] = as_dict(out.get("meta"), "meta")
    out["cost"] = as_dict(out.get("cost"), "cost")
    out["tasks"] = as_dict(out.get("tasks"), "tasks")
    out["autonomous"] = as_dict(out.get("autonomous"), "autonomous")
    out["skills"] = as_dict(out.get("skills"), "skills")
    out["health"] = as_dict(out.get("health"), "health")
    out["rating"] = as_dict(out.get("rating"), "rating")

    out["cost"]["by_source"] = as_dict(out["cost"].get("by_source"), "cost.by_source")
    out["cost"]["trend"] = as_list(out["cost"].get("trend"), "cost.trend")
    out["tasks"]["highlights"] = as_list(out["tasks"].get("highlights"), "tasks.highlights")
    out["tasks"]["trend"] = as_list(out["tasks"].get("trend"), "tasks.trend")
    out["autonomous"]["notable"] = as_list(out["autonomous"].get("notable"), "autonomous.notable")
    out["skills"]["top_used"] = as_list(out["skills"].get("top_used"), "skills.top_used")
    out["skills"]["unused"] = as_list(out["skills"].get("unused"), "skills.unused")
    out["health"]["error_rate_trend"] = as_list(out["health"].get("error_rate_trend"), "health.error_rate_trend")
    return out


def fmt_money(value: float) -> str:
    return f"{value:,.2f}"


def fmt_pct(rate: float) -> str:
    return f"{round(rate * 100)}%"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def draw_rounded_box(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int, int, int],
    fill: str,
    outline: Optional[str] = None,
    width: int = 1,
    radius: int = 14,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def wrap_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: Optional[int] = None,
) -> List[str]:
    words = text.split()
    if not words:
        return [""]

    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if max_lines and len(lines) >= max_lines:
                break

    if not max_lines or len(lines) < max_lines:
        lines.append(current)

    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]

    if max_lines and len(lines) == max_lines:
        while text_width(draw, lines[-1], font) > max_width and len(lines[-1]) > 2:
            lines[-1] = lines[-1][:-2] + "…"

    return lines


def safe_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        warn(f"font missing/unreadable: {path}; using PIL default font fallback.")
        return ImageFont.load_default()


def load_fonts(fonts_dir: Path) -> Dict[str, ImageFont.FreeTypeFont]:
    return {
        "mono": safe_font(fonts_dir / "JetBrainsMono-Regular.ttf", 20),
        "mono_sm": safe_font(fonts_dir / "JetBrainsMono-Regular.ttf", 16),
        "mono_xs": safe_font(fonts_dir / "JetBrainsMono-Regular.ttf", 14),
        "heading": safe_font(fonts_dir / "SpaceGrotesk-Bold.ttf", 28),
        "heading_lg": safe_font(fonts_dir / "SpaceGrotesk-Bold.ttf", 44),
        "title": safe_font(fonts_dir / "SpaceGrotesk-Bold.ttf", 58),
        "body": safe_font(fonts_dir / "SpaceGrotesk-Regular.ttf", 22),
        "body_sm": safe_font(fonts_dir / "SpaceGrotesk-Regular.ttf", 18),
        "body_xs": safe_font(fonts_dir / "SpaceGrotesk-Regular.ttf", 16),
        "bold": safe_font(fonts_dir / "SpaceGrotesk-Bold.ttf", 20),
    }


def draw_grid(img: Image.Image) -> None:
    grid = ImageDraw.Draw(img)
    color = (99, 102, 241, 10)
    for x in range(0, WIDTH, 40):
        grid.line([(x, 0), (x, HEIGHT)], fill=color, width=1)
    for y in range(0, HEIGHT, 40):
        grid.line([(0, y), (WIDTH, y)], fill=color, width=1)


def section_well(draw: ImageDraw.ImageDraw, y1: int, y2: int) -> None:
    draw_rounded_box(draw, (28, y1, WIDTH - 28, y2), fill=WELL_BG, outline=DIVIDER, width=1, radius=14)


def get_week_label(meta: Dict) -> str:
    period_end = (meta.get("period") or {}).get("end")
    if period_end:
        try:
            dt = date.fromisoformat(period_end)
            return f"Week {dt.isocalendar().week}"
        except ValueError:
            pass
    return "Week N"


def choose_tip(analysis: Dict) -> Tuple[str, float]:
    recs = generate_recommendations(analysis)
    cost_rec = next((r for r in recs if r.get("category") == "COST"), None)
    if not cost_rec:
        return ("No large leak detected this week; keep current config and monitor trends", 0.0)
    impact = cost_rec.get("impact", "")
    savings_match = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", impact)
    savings = float(savings_match.group(1)) if savings_match else 0.0
    return (cost_rec.get("text", "Tune cost settings"), savings)


def build_metrics(analysis: Dict) -> Dict[str, float]:
    tasks = as_dict(analysis.get("tasks"), "tasks")
    cost = as_dict(analysis.get("cost"), "cost")
    by_source = as_dict(cost.get("by_source"), "cost.by_source")
    health = as_dict(analysis.get("health"), "health")
    auto = as_dict(analysis.get("autonomous"), "autonomous")
    skills = as_dict(analysis.get("skills"), "skills")
    top_skill = (as_list(skills.get("top_used"), "skills.top_used") or [{}])[0]

    asked = max(safe_int(tasks.get("asked"), 0), 1)
    heartbeat_usd = safe_float(as_dict(by_source.get("heartbeats"), "cost.by_source.heartbeats").get("usd"))
    self_usd = safe_float(as_dict(by_source.get("self_initiated"), "cost.by_source.self_initiated").get("usd"))
    total_usd = max(safe_float(cost.get("total_usd")), 0.0001)
    auto_total = max(safe_int(auto.get("total_actions"), 0), 1)
    three_am_total = max(safe_int(auto.get("three_am_sessions"), 0), 1)

    return {
        "heartbeat_cost_pct": safe_float(as_dict(by_source.get("heartbeats"), "cost.by_source.heartbeats").get("pct")),
        "unused_skills_count": float(len(as_list(skills.get("unused"), "skills.unused"))),
        "three_am_sessions": float(safe_int(auto.get("three_am_sessions"), 0)),
        "three_am_useful_rate": safe_float(auto.get("three_am_useful")) / float(three_am_total),
        "error_rate": safe_float(health.get("error_rate")) or (safe_float(health.get("errors_total")) / float(asked)),
        "cost_per_task": safe_float(cost.get("per_completed_task_usd")),
        "read_write_ratio": safe_float(health.get("read_write_ratio")),
        "context_overflows": safe_float(health.get("context_overflows")),
        "top_skill_pct": safe_float(as_dict(top_skill, "skills.top_used[0]").get("pct_of_total")),
        "self_initiated_cost_pct": (self_usd / total_usd) * 100.0,
        "autonomous_useful_rate": safe_float(auto.get("useful_count")) / float(auto_total),
        "tool_failures": safe_float(health.get("tool_failures")),
        "heartbeat_cost_usd": heartbeat_usd,
        "total_cost_usd": total_usd,
    }


def evaluate_condition(condition: str, metrics: Dict[str, float]) -> bool:
    condition = (condition or "").strip()
    if not condition:
        return False

    or_parts = [part.strip() for part in re.split(r"\s+OR\s+", condition, flags=re.IGNORECASE)]

    def eval_clause(clause: str) -> bool:
        and_parts = [part.strip() for part in re.split(r"\s+AND\s+", clause, flags=re.IGNORECASE)]
        for expr in and_parts:
            m = re.match(r"^([a-zA-Z0-9_]+)\s*(>=|<=|>|<|==|!=)\s*(-?[0-9]+(?:\.[0-9]+)?)$", expr)
            if not m:
                return False
            key, op, value_s = m.groups()
            left = float(metrics.get(key, 0.0))
            right = float(value_s)
            if op == ">" and not (left > right):
                return False
            if op == "<" and not (left < right):
                return False
            if op == ">=" and not (left >= right):
                return False
            if op == "<=" and not (left <= right):
                return False
            if op == "==" and not (left == right):
                return False
            if op == "!=" and not (left != right):
                return False
        return True

    return any(eval_clause(clause) for clause in or_parts)


def placeholder_values(analysis: Dict) -> Dict[str, str]:
    tasks = as_dict(analysis.get("tasks"), "tasks")
    cost = as_dict(analysis.get("cost"), "cost")
    by_source = as_dict(cost.get("by_source"), "cost.by_source")
    health = as_dict(analysis.get("health"), "health")
    auto = as_dict(analysis.get("autonomous"), "autonomous")
    skills = as_dict(analysis.get("skills"), "skills")
    top_skill = (as_list(skills.get("top_used"), "skills.top_used") or [{"name": "github", "calls": 0, "pct_of_total": 0}])[0]

    three_am_sessions = safe_int(auto.get("three_am_sessions"), 0)
    three_am_useful = safe_int(auto.get("three_am_useful"), 0)
    completion = safe_float(tasks.get("completion_rate"), 0.0)
    completed = safe_int(tasks.get("completed"), 0)
    asked = max(safe_int(tasks.get("asked"), 0), 1)
    total_cost = safe_float(cost.get("total_usd"), 0.0)
    heartbeat = safe_float(as_dict(by_source.get("heartbeats"), "cost.by_source.heartbeats").get("usd"), 0.0)
    self_usd = safe_float(as_dict(by_source.get("self_initiated"), "cost.by_source.self_initiated").get("usd"), 0.0)
    error_rate = safe_float(health.get("error_rate"), 0.0)
    if error_rate <= 0:
        error_rate = safe_float(health.get("errors_total"), 0.0) / float(asked)
    unused = as_list(skills.get("unused"), "skills.unused")
    reduction_pct = 0
    if total_cost > 0:
        reduction_pct = int(round((heartbeat / total_cost) * 35))

    estimated_savings = max(2.0, heartbeat * 0.35)
    overnight_cost = heartbeat * 0.22
    token_savings = max(80, len(unused) * 42)
    cost_per_task = safe_float(cost.get("per_completed_task_usd"), 0.0)
    prev_completion_rate = (analysis.get("rating") or {}).get("previous_task_completion_rate")
    if prev_completion_rate is None:
        completion_hist = as_list(tasks.get("trend"), "tasks.trend")
        if completion_hist:
            prev_completion_rate = safe_float(as_dict(completion_hist[-1], "tasks.trend[-1]").get("value"), 0.0) / 100.0
    completion_delta = ""
    prev_completion_pct = ""
    if isinstance(prev_completion_rate, (int, float)):
        prev_completion_pct = f"{int(round(float(prev_completion_rate) * 100))}"
        completion_delta = f"{round((completion - float(prev_completion_rate)) * 100, 1)}"
    read_calls = health.get("read_calls")
    write_calls = health.get("write_calls")
    if not isinstance(read_calls, (int, float)):
        read_calls = None
    if not isinstance(write_calls, (int, float)):
        write_calls = None
    heartbeat_useful_rate = auto.get("heartbeat_useful_rate")
    heartbeat_useful_pct = ""
    if isinstance(heartbeat_useful_rate, (int, float)):
        heartbeat_useful_pct = str(int(round(safe_float(heartbeat_useful_rate) * 100)))
    risky_count = auto.get("risky_count")
    if not isinstance(risky_count, int):
        risky_count = len([x for x in as_list(auto.get("notable"), "autonomous.notable") if as_dict(x, "autonomous.notable[]").get("verdict") == "risky"])

    return {
        "completed_tasks": str(completed),
        "asked_tasks": str(asked),
        "failed_tasks": str(safe_int(tasks.get("failed"), 0)),
        "in_progress_tasks": str(safe_int(tasks.get("in_progress"), 0)),
        "total_cost": f"{total_cost:.2f}",
        "cost_per_task": f"{cost_per_task:.2f}",
        "completion_rate": f"{int(round(completion * 100))}",
        "prev_completion": prev_completion_pct,
        "heartbeat_pct": str(safe_int(as_dict(by_source.get("heartbeats"), "cost.by_source.heartbeats").get("pct"), 0)),
        "heartbeat_cost": f"{heartbeat:.2f}",
        "heartbeat_useful_pct": heartbeat_useful_pct,
        "errors_total": str(safe_int(health.get("errors_total"), 0)),
        "errors_fixed": "",
        "autonomous_notable_desc": as_dict((as_list(auto.get("notable"), "autonomous.notable") or [{"summary": "status checks"}])[0], "autonomous.notable[0]").get("summary", "status checks"),
        "autonomous_actions": str(safe_int(auto.get("total_actions"), 0)),
        "autonomous_useful_pct": str(int(round(safe_float(auto.get("useful_rate")) * 100))),
        "errors_self_caused": str(safe_int(health.get("errors_self_caused"), 0)),
        "read_write_ratio": str(safe_int(health.get("read_write_ratio"), 0)),
        "reads_total": str(int(read_calls)) if read_calls is not None else "",
        "writes_total": str(int(write_calls)) if write_calls is not None else "",
        "context_overflows": str(safe_int(health.get("context_overflows"), 0)),
        "tool_calls_total": str(safe_int(auto.get("total_actions"), 0)),
        "risky_actions": str(risky_count),
        "rating_title": str(as_dict(analysis.get("rating"), "rating").get("title", "Unpaid Intern")),
        "percentile": str(safe_int(as_dict(analysis.get("rating"), "rating").get("percentile"), 50)),
        "previous_rating": str(
            (analysis.get("rating") or {}).get(
                "previous_title", (analysis.get("rating") or {}).get("title", "Unpaid Intern")
            )
        ),
        "self_initiated_cost": f"{self_usd:.2f}",
        "self_initiated_count": str(safe_int(as_dict(by_source.get("self_initiated"), "cost.by_source.self_initiated").get("count"), 0)),
        "avg_response_seconds": f"{safe_float(health.get('avg_response_seconds'), 0.0):.1f}",
        "completion_delta": completion_delta,
        "three_am_sessions": str(three_am_sessions),
        "three_am_useful": str(three_am_useful),
        "skills_used": str(safe_int(skills.get("used"), 0)),
        "skills_installed": str(safe_int(skills.get("installed"), 0)),
        "tool_failures": str(safe_int(health.get("tool_failures"), 0)),
        "compactions": str(safe_int(health.get("compactions"), 0)),
        "recommendation_summary": "tighten cost controls and reduce low-yield autonomous cycles",
        "cheapest_model": "anthropic/claude-haiku-4-5",
        "cheaper_model": "anthropic/claude-haiku-4-5",
        "estimated_savings": f"{estimated_savings:.2f}",
        "reduction_pct": str(max(10, reduction_pct)),
        "unused_count": str(len(unused)),
        "unused_names_short": ", ".join(unused[:4]) if unused else "none",
        "skill_name": unused[0] if unused else "example-skill",
        "token_savings": str(token_savings),
        "error_rate_pct": f"{error_rate * 100:.1f}",
        "overnight_cost": f"{overnight_cost:.2f}",
        "suggested_threshold": "120000",
        "suggested_confidence": "0.75",
        "top_skill_name": str(as_dict(top_skill, "skills.top_used[0]").get("name", "github")),
        "top_skill_pct": str(safe_int(as_dict(top_skill, "skills.top_used[0]").get("pct_of_total"), 0)),
    }


def generate_recommendations(analysis: Dict) -> List[Dict[str, str]]:
    tasks = as_dict(analysis.get("tasks"), "tasks")
    cost = as_dict(analysis.get("cost"), "cost")
    by_source = as_dict(cost.get("by_source"), "cost.by_source")
    health = as_dict(analysis.get("health"), "health")
    auto = as_dict(analysis.get("autonomous"), "autonomous")
    skills = as_dict(analysis.get("skills"), "skills")

    repo_root = Path(__file__).resolve().parent.parent
    rec_path = repo_root / "references" / "recommendations.json"
    values = placeholder_values(analysis)
    metrics = build_metrics(analysis)
    recs: List[Dict[str, str]] = []

    if rec_path.exists():
        try:
            pattern_data = load_json(rec_path).get("patterns", [])
            for pattern in sorted(pattern_data, key=lambda p: safe_int(as_dict(p, "recommendation.pattern").get("priority"), 99)):
                if not evaluate_condition(str(pattern.get("condition", "")), metrics):
                    continue
                text = fill_template(str(pattern.get("template", "")), values)
                impact = fill_template(str(pattern.get("impact", "")), values)
                recs.append(
                    {
                        "category": str(pattern.get("category", "EFFICIENCY")),
                        "text": text,
                        "impact": impact,
                        "config_change": str(pattern.get("config_change") or ""),
                    }
                )
        except Exception as exc:
            warn(f"failed evaluating recommendations from {rec_path}: {exc}")
            recs = []

    if recs:
        return recs[:3]

    heartbeat_pct = safe_float(values.get("heartbeat_pct"), 0.0)
    heartbeat_usd = safe_float(as_dict(by_source.get("heartbeats"), "cost.by_source.heartbeats").get("usd"))
    if heartbeat_pct > 30:
        recs.append(
            {
                "category": "COST",
                "text": "Switch heartbeat model to a cheaper default and limit overnight windows",
                "impact": f"Expected savings: ${heartbeat_usd * 0.35:,.2f}/week",
            }
        )

    if len(as_list(skills.get("unused"), "skills.unused")) > 3:
        names = ", ".join(as_list(skills.get("unused"), "skills.unused")[:4])
        recs.append(
            {
                "category": "CLEANUP",
                "text": f"Disable unused skills ({names}) to reduce prompt overhead",
                "impact": "Reduces token load per session and lowers latency",
            }
        )

    asked = max(safe_int(tasks.get("asked"), 0), 1)
    error_rate = safe_float(health.get("error_rate")) or (safe_float(health.get("errors_total")) / asked)
    if error_rate > 0.1:
        recs.append(
            {
                "category": "RELIABILITY",
                "text": "Add guardrails for recurring failing task types and increase validation before writes",
                "impact": f"Current error rate: {error_rate * 100:.1f}%",
            }
        )

    ratio = safe_int(health.get("read_write_ratio"), 0)
    if ratio > 50:
        recs.append(
            {
                "category": "EFFICIENCY",
                "text": "Restructure MEMORY.md to reduce repetitive read-heavy tool chains",
                "impact": f"Read/write ratio currently {ratio}:1",
            }
        )

    if safe_int(health.get("context_overflows"), 0) > 0:
        recs.append(
            {
                "category": "RELIABILITY",
                "text": "Increase compaction threshold and trim oversized memory sections",
                "impact": f"Observed overflows: {health.get('context_overflows', 0)}",
            }
        )

    if safe_float(auto.get("three_am_sessions"), 0.0) > 2:
        recs.append(
            {
                "category": "EFFICIENCY",
                "text": "Restrict autonomous runtime hours to 08:00-24:00",
                "impact": "Cuts low-value overnight activity",
            }
        )

    if not recs:
        recs.append(
            {
                "category": "EFFICIENCY",
                "text": "Keep current configuration and monitor weekly trend movement",
                "impact": "No major regressions detected",
                "config_change": "",
            }
        )

    return recs[:3]


def fill_template(template: str, data: Dict[str, str]) -> str:
    out = template
    for k, v in data.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def choose_manager_note(analysis: Dict, roasts_path: Path, seed: Optional[int] = None) -> str:
    template = (
        "Completion rate is {completion_rate}% on ${total_cost} weekly spend. "
        "Autonomous work logged {autonomous_actions} actions with {autonomous_useful_pct}% usefulness. "
        "Current rating: {rating_title}. Recommendation: {recommendation_summary}."
    )

    values = placeholder_values(analysis)
    recommendations = generate_recommendations(analysis)
    if recommendations:
        values["recommendation_summary"] = recommendations[0].get("text", values["recommendation_summary"])

    candidates: List[Dict] = []
    try:
        roast_data = load_json(roasts_path)
        for item in roast_data.get("manager_notes", []):
            required = item.get("requires", [])
            if all(str(values.get(key, "")).strip() != "" for key in required):
                candidates.append(item)
    except Exception as exc:
        warn(f"failed loading roast templates from {roasts_path}: {exc}")
        candidates = []

    if candidates:
        if seed is None:
            period = (analysis.get("meta", {}).get("period", {}) or {}).get("end", "week")
            agent = analysis.get("meta", {}).get("agent_id", "agent")
            digest = hashlib.sha256(f"{agent}:{period}".encode("utf-8")).hexdigest()[:8]
            seed = int(digest, 16)
        # Deterministic template choice only; not used for cryptography.
        rng = random.Random(seed)  # nosec B311
        template = rng.choice(candidates).get("template", template)

    rendered = fill_template(template, values)
    return re.sub(r"\{[a-zA-Z0-9_]+\}", "n/a", rendered)


def draw_stacked_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    values: Sequence[Tuple[str, float]],
    fonts: Dict[str, ImageFont.FreeTypeFont],
) -> None:
    total = sum(v for _, v in values)
    cursor = x
    if total <= 0:
        draw_rounded_box(draw, (x, y, x + w, y + h), fill="#0f1320", outline=DIVIDER, radius=8)
        return

    for idx, (key, amount) in enumerate(values):
        seg = int(round((amount / total) * w))
        if idx == len(values) - 1:
            seg = x + w - cursor
        if seg <= 0:
            continue
        color = SOURCE_COLORS.get(key, "#3d4250")
        draw.rectangle((cursor, y, cursor + seg, y + h), fill=color)
        label = f"${amount:.2f}"
        if seg > text_width(draw, label, fonts["mono_sm"]) + 14:
            draw.text((cursor + 7, y + 4), label, fill="#0b0d12", font=fonts["mono_sm"])
        cursor += seg

    draw.rounded_rectangle((x, y, x + w, y + h), radius=8, outline=DIVIDER, width=1)


def draw_sparkline(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    values: List[float],
    color: str,
) -> None:
    sanitized: List[float] = []
    for raw in values:
        val = safe_float(raw, 0.0)
        if math.isfinite(val):
            sanitized.append(val)
    values = sanitized
    if not values:
        draw.rectangle((x, y, x + w, y + h), outline=DIVIDER, width=1)
        return

    lo = min(values)
    hi = max(values)
    span = (hi - lo) or 1.0
    points = []
    for i, v in enumerate(values):
        px = x + int(i * (w / max(1, len(values) - 1)))
        py = y + h - int(((v - lo) / span) * h)
        points.append((px, py))

    draw.rectangle((x, y, x + w, y + h), outline=DIVIDER, width=1)
    if len(points) > 1:
        draw.line(points, fill=color, width=3, joint="curve")
    else:
        draw.ellipse((points[0][0] - 2, points[0][1] - 2, points[0][0] + 2, points[0][1] + 2), fill=color)

    lx, ly = points[-1]
    draw.ellipse((lx - 5, ly - 5, lx + 5, ly + 5), fill=color)


def render_card(
    analysis: Dict,
    out_path: Path,
    fonts_dir: Path,
    assets_dir: Path,
    refs_dir: Path,
    seed: Optional[int] = None,
) -> None:
    if not fonts_dir.exists():
        raise CardGenerationError(f"fonts directory does not exist: {fonts_dir}")
    fonts = load_fonts(fonts_dir)

    img = Image.new("RGBA", (WIDTH, HEIGHT), BG)
    draw_grid(img)
    draw = ImageDraw.Draw(img)

    meta = as_dict(analysis.get("meta"), "meta")
    period = as_dict(meta.get("period"), "meta.period")
    tasks = as_dict(analysis.get("tasks"), "tasks")
    cost = as_dict(analysis.get("cost"), "cost")
    auto = as_dict(analysis.get("autonomous"), "autonomous")
    skills = as_dict(analysis.get("skills"), "skills")
    health = as_dict(analysis.get("health"), "health")
    rating = as_dict(analysis.get("rating"), "rating")

    week_label = get_week_label(meta)

    # Header row
    draw.text((36, 22), "CONFIDENTIAL", fill="#dc2626", font=fonts["bold"])
    draw.text(
        (36, 52),
        f"WEEKLY PERFORMANCE REVIEW · {period.get('start', '?')} to {period.get('end', '?')}",
        fill=TEXT_DIM,
        font=fonts["mono_sm"],
    )
    draw.text((WIDTH - 36, 20), week_label, fill=TEXT_BRIGHT, font=fonts["heading"], anchor="ra")
    uptime = f"Uptime: {safe_int(period.get('days'), 0)}d window"
    draw.text((WIDTH - 36, 52), uptime, fill=TEXT_MED, font=fonts["mono_sm"], anchor="ra")

    # Agent + rating
    section_well(draw, 80, 168)
    agent_name = safe_text(meta.get("agent_id", "main"), default="main", max_len=60)
    host = safe_text(meta.get("hostname", "unknown"), default="unknown", max_len=80)
    draw.text((48, 98), agent_name, fill=TEXT_BRIGHT, font=fonts["title"])
    draw.text(
        (48, 146),
        f"Dept: {host} · Role: Unclear · Status: 'Working'",
        fill=TEXT_MED,
        font=fonts["body_sm"],
    )

    rating_title = safe_text(rating.get("title", "Unpaid Intern"), default="Unpaid Intern", max_len=32)
    rating_color = safe_color(rating.get("color", "#dc2626"), "#dc2626")
    badge_w, badge_h = 320, 56
    bx2 = WIDTH - 46
    bx1 = bx2 - badge_w
    by1 = 95
    by2 = by1 + badge_h
    draw_rounded_box(draw, (bx1, by1, bx2, by2), fill="#0d1220", outline=rating_color, width=2, radius=12)
    draw.text((bx1 + 14, by1 + 14), rating_title, fill=rating_color, font=fonts["heading"])

    prev = safe_text(rating.get("previous_title", rating_title), default=rating_title, max_len=32)
    if prev == rating_title:
        delta_line = "→ Unchanged"
    else:
        sign = "↑" if rating.get("improved") else "↓"
        delta_line = f"{sign} from {prev} · Top {safe_int(rating.get('percentile'), 50)}%"
    draw.text((bx2, by2 + 12), delta_line, fill=TEXT_MED, font=fonts["mono_sm"], anchor="ra")

    # Money section
    section_well(draw, 176, 325)
    total_cost = safe_float(cost.get("total_usd"), 0.0)
    draw.text(
        (48, 192),
        f"WHERE YOUR MONEY GOES · ${fmt_money(total_cost)} THIS WEEK",
        fill=TEXT_BRIGHT,
        font=fonts["heading"],
    )

    sources = as_dict(cost.get("by_source"), "cost.by_source")
    bar_values = [
        ("user_requests", safe_float(as_dict(sources.get("user_requests"), "cost.by_source.user_requests").get("usd"), 0.0)),
        ("heartbeats", safe_float(as_dict(sources.get("heartbeats"), "cost.by_source.heartbeats").get("usd"), 0.0)),
        ("cron_jobs", safe_float(as_dict(sources.get("cron_jobs"), "cost.by_source.cron_jobs").get("usd"), 0.0)),
        ("self_initiated", safe_float(as_dict(sources.get("self_initiated"), "cost.by_source.self_initiated").get("usd"), 0.0)),
    ]
    draw_stacked_bar(draw, 48, 232, WIDTH - 96, 36, bar_values, fonts)

    lx = 48
    ly = 275
    for key, _ in bar_values:
        pct = safe_int(as_dict(sources.get(key), f"cost.by_source.{key}").get("pct"), 0)
        label = key.replace("_", " ")
        color = SOURCE_COLORS[key]
        draw.ellipse((lx, ly + 4, lx + 10, ly + 14), fill=color)
        draw.text((lx + 16, ly), f"{label} {pct}%", fill=TEXT_MED, font=fonts["mono_sm"])
        lx += 270

    tip, savings = choose_tip(analysis)
    tip_fill = "#112016" if savings >= 2 else "#171c28"
    draw_rounded_box(draw, (48, 294, WIDTH - 48, 319), fill=tip_fill, outline=DIVIDER, radius=8)
    tip_text = f"TIP: {tip}"
    if savings >= 2:
        tip_text += f" → -${savings:.2f}/wk"
    draw.text((56, 298), tip_text, fill=TEXT_MED, font=fonts["body_xs"])

    # Tasks section
    section_well(draw, 334, 516)
    asked = safe_int(tasks.get("asked"), 0)
    completed = safe_int(tasks.get("completed"), 0)
    draw.text(
        (48, 350),
        f"WHAT YOU ASKED FOR · {completed}/{asked} COMPLETED ({fmt_pct(safe_float(tasks.get('completion_rate'), 0.0))})",
        fill=TEXT_BRIGHT,
        font=fonts["heading"],
    )

    highlights = as_list(tasks.get("highlights"), "tasks.highlights")[:5]
    y = 390
    for item in highlights:
        item_d = as_dict(item, "tasks.highlights[]")
        status = item_d.get("status", "in_progress")
        icon = "✓" if status == "completed" else ("✗" if status == "failed" else "◌")
        color = "#22c55e" if status == "completed" else ("#dc2626" if status == "failed" else TEXT_DIM)
        summary = safe_text(item_d.get("summary"), default="(untitled task)", max_len=52)
        dur = item_d.get("duration_seconds")
        dur_str = "--"
        if isinstance(dur, (int, float)) and dur >= 0:
            if dur >= 60:
                dur_str = f"{int(round(dur / 60.0))}m"
            else:
                dur_str = f"{int(dur)}s"

        draw.text((56, y), icon, fill=color, font=fonts["bold"])
        draw.text((80, y), summary, fill=TEXT_MED, font=fonts["body_sm"])
        draw.text((860, y), dur_str, fill=TEXT_DIM, font=fonts["mono_sm"])

        model = safe_text(item_d.get("model"), default="unknown", max_len=26)
        pw = text_width(draw, model, fonts["mono_xs"]) + 16
        px1 = WIDTH - 56 - pw
        draw_rounded_box(draw, (px1, y - 1, WIDTH - 56, y + 20), fill="#121826", outline=DIVIDER, radius=10)
        draw.text((px1 + 8, y + 2), model, fill=TEXT_DIM, font=fonts["mono_xs"])

        if status == "failed" and item_d.get("failure_reason"):
            draw.text((82, y + 19), safe_text(item_d.get("failure_reason"), default="failure", max_len=56), fill="#dc2626", font=fonts["body_xs"])
            y += 36
        else:
            y += 29

    completed_in_rows = 0
    for h in highlights:
        if as_dict(h, "tasks.highlights[]").get("status") == "completed":
            completed_in_rows += 1
    extra_completed = max(0, safe_int(tasks.get("completed"), 0) - completed_in_rows)
    draw.text(
        (48, 495),
        f"+ {extra_completed} more completed · {safe_int(tasks.get('in_progress'), 0)} in progress",
        fill=TEXT_DIM,
        font=fonts["mono_sm"],
    )

    # Autonomous section
    section_well(draw, 524, 695)
    useful = safe_int(auto.get("useful_count"), 0)
    total_actions = safe_int(auto.get("total_actions"), 0)
    useful_rate = safe_float(auto.get("useful_rate"), 0.0)
    draw.text(
        (48, 540),
        f"AUTONOMOUS ACTIVITY · {total_actions} ACTIONS, {useful} USEFUL ({fmt_pct(useful_rate)})",
        fill=TEXT_BRIGHT,
        font=fonts["heading"],
    )

    verdict_colors = {
        "helpful": "#22c55e",
        "unnecessary": "#f97316",
        "partial": "#3b82f6",
        "risky": "#dc2626",
    }
    verdict_icons = {"helpful": "▲", "unnecessary": "■", "partial": "◆", "risky": "⚠"}

    y = 576
    notable = as_list(auto.get("notable"), "autonomous.notable")[:5]
    for act in notable:
        act_d = as_dict(act, "autonomous.notable[]")
        verdict = (str(act_d.get("verdict") or "unnecessary")).lower()
        color = verdict_colors.get(verdict, TEXT_DIM)
        icon = verdict_icons.get(verdict, "■")
        ts = safe_text(act_d.get("timestamp"), default="", max_len=40)
        ts_short = ts[5:16].replace("T", " ") if len(ts) >= 16 else ts

        draw.text((56, y), icon, fill=color, font=fonts["bold"])
        draw.text((84, y), ts_short, fill=TEXT_DIM, font=fonts["mono_sm"])
        draw.text((238, y), safe_text(act_d.get("summary"), default="Autonomous action", max_len=56), fill=TEXT_MED, font=fonts["body_sm"])

        pill = verdict.capitalize()
        pw = text_width(draw, pill, fonts["mono_xs"]) + 16
        px1 = WIDTH - 56 - pw
        draw_rounded_box(draw, (px1, y - 1, WIDTH - 56, y + 20), fill="#141722", outline=color, radius=10)
        draw.text((px1 + 8, y + 2), pill, fill=color, font=fonts["mono_xs"])
        y += 24

    status_checks = max(0, total_actions - useful)
    status_pct = int(round((status_checks / max(total_actions, 1)) * 100))
    draw.text(
        (48, 673),
        f"+ {max(0, total_actions - len(notable))} other actions ({status_pct}% were status checks)",
        fill=TEXT_DIM,
        font=fonts["body_xs"],
    )

    # Skills + health
    section_well(draw, 703, 900)
    draw.line((WIDTH // 2, 720, WIDTH // 2, 884), fill=DIVIDER, width=1)

    draw.text((48, 720), f"SKILLS · {safe_int(skills.get('used'), 0)} OF {safe_int(skills.get('installed'), 0)} USED", fill=TEXT_BRIGHT, font=fonts["heading"])
    sy = 754
    top_skills = as_list(skills.get("top_used"), "skills.top_used")[:4]
    max_calls = max([safe_int(as_dict(s, "skills.top_used[]").get("calls"), 0) for s in top_skills] + [1])
    for s in top_skills:
        s_d = as_dict(s, "skills.top_used[]")
        name = safe_text(s_d.get("name"), default="skill", max_len=18)
        calls = safe_int(s_d.get("calls"), 0)
        bw = int((calls / max_calls) * 180)
        draw.text((56, sy), name[:18], fill=TEXT_MED, font=fonts["mono_sm"])
        draw.rectangle((204, sy + 4, 204 + bw, sy + 16), fill="#3b82f6")
        draw.text((392, sy), str(calls), fill=TEXT_DIM, font=fonts["mono_sm"])
        sy += 26

    unused = as_list(skills.get("unused"), "skills.unused")
    if unused:
        draw_rounded_box(draw, (48, 854, WIDTH // 2 - 24, 892), fill="#271417", outline="#4a1d24", radius=8)
        unused_text = ", ".join([safe_text(u, default="skill", max_len=20) for u in unused[:5]])
        draw.text((56, 865), f"IDLE {len(unused)}: {unused_text}", fill="#fca5a5", font=fonts["mono_xs"])

    draw.text((WIDTH // 2 + 24, 720), "SYSTEM HEALTH", fill=TEXT_BRIGHT, font=fonts["heading"])
    health_rows = [
        ("Errors caused / fixed", f"{safe_int(health.get('errors_self_caused'), 0)} / {max(0, safe_int(tasks.get('completed'), 0) - safe_int(tasks.get('failed'), 0))}"),
        ("Self-caused errors", str(safe_int(health.get("errors_self_caused"), 0))),
        ("Context overflows", str(safe_int(health.get("context_overflows"), 0))),
        ("Avg response", f"{safe_float(health.get('avg_response_seconds'), 0.0)}s"),
        ("Read/write ratio", f"{safe_int(health.get('read_write_ratio'), 0)}:1"),
        ("Compactions", str(safe_int(health.get("compactions"), 0))),
    ]
    hy = 756
    for label, val in health_rows:
        first_num = safe_int(str(val).split(" ")[0].split("/")[0], 0)
        val_color = "#dc2626" if ("error" in label.lower() and first_num > 10) else TEXT_MED
        if "Context overflows" in label and safe_int(val, 0) > 0:
            val_color = "#dc2626"
        draw.text((WIDTH // 2 + 28, hy), label, fill=TEXT_DIM, font=fonts["mono_sm"])
        draw.text((WIDTH - 56, hy), val, fill=val_color, font=fonts["mono_sm"], anchor="ra")
        hy += 24

    # Trends
    section_well(draw, 908, 1052)
    draw.text((48, 924), "TRENDS · 7-WEEK HISTORY", fill=TEXT_BRIGHT, font=fonts["heading"])

    cost_trend = [safe_float(as_dict(x, "cost.trend[]").get("value"), 0.0) for x in as_list(cost.get("trend"), "cost.trend")][-6:]
    completion_trend_hist = [safe_float(as_dict(x, "tasks.trend[]").get("value"), 0.0) for x in as_list(tasks.get("trend"), "tasks.trend")][-6:]
    error_trend_hist = [safe_float(as_dict(x, "health.error_rate_trend[]").get("value"), 0.0) for x in as_list(health.get("error_rate_trend"), "health.error_rate_trend")][-6:]

    completion_current = safe_float(tasks.get("completion_rate"), 0.0) * 100
    error_current = safe_float(health.get("error_rate"), 0.0) * 100
    if error_current <= 0:
        error_current = (safe_float(health.get("errors_total"), 0.0) / max(1, asked)) * 100

    if cost_trend:
        cost_trend.append(total_cost)
    if completion_trend_hist:
        comp_trend = completion_trend_hist + [completion_current]
    else:
        comp_trend = []
    if error_trend_hist:
        err_trend = error_trend_hist + [error_current]
    else:
        err_trend = []

    chart_w = 340
    chart_h = 72
    draw.text((56, 956), f"Completion {completion_current:.0f}%", fill="#22c55e", font=fonts["mono_sm"])
    draw_sparkline(draw, 56, 977, chart_w, chart_h, comp_trend, "#22c55e")

    draw.text((430, 956), f"Weekly Cost ${total_cost:.2f}", fill="#3b82f6", font=fonts["mono_sm"])
    draw_sparkline(draw, 430, 977, chart_w, chart_h, cost_trend, "#3b82f6")

    draw.text((804, 956), f"Error Rate {error_current:.1f}%", fill="#dc2626", font=fonts["mono_sm"])
    draw_sparkline(draw, 804, 977, chart_w, chart_h, err_trend, "#dc2626")

    if not cost_trend and not comp_trend and not err_trend:
        draw.text((48, 1028), "Tracking starts next week", fill=TEXT_DIM, font=fonts["mono_sm"])
    elif len(cost_trend) > 1:
        delta = cost_trend[-1] - cost_trend[-2] if len(cost_trend) > 1 else 0
        arrow = "↑" if delta > 0 else "↓"
        draw.text((48, 1028), f"{arrow} from ${abs(delta):.2f} week-over-week", fill=TEXT_DIM, font=fonts["mono_sm"])
    elif len(comp_trend) > 1:
        delta = comp_trend[-1] - comp_trend[-2]
        arrow = "↑" if delta > 0 else "↓"
        draw.text((48, 1028), f"{arrow} {abs(delta):.1f}pts completion week-over-week", fill=TEXT_DIM, font=fonts["mono_sm"])

    # Manager's note
    section_well(draw, 1060, 1254)
    draw.text((48, 1076), "MANAGER'S NOTE", fill=TEXT_BRIGHT, font=fonts["heading"])
    note = choose_manager_note(analysis, refs_dir / "roasts.json", seed=seed)
    lines = wrap_lines(draw, note, fonts["body_sm"], WIDTH - 96, max_lines=6)
    yy = 1114
    for line in lines:
        draw.text((56, yy), line, fill=TEXT_MED, font=fonts["body_sm"])
        yy += 28

    # Improvement plan
    section_well(draw, 1262, 1462)
    next_week = week_label.replace("Week", "")
    try:
        next_week_n = int(next_week.strip()) + 1
    except ValueError:
        next_week_n = 0
    header = f"PERFORMANCE IMPROVEMENT PLAN — WEEK {next_week_n if next_week_n else 'N+1'}"
    draw.text((48, 1278), header, fill=TEXT_BRIGHT, font=fonts["heading"])

    recs = generate_recommendations(analysis)
    ry = 1316
    for idx, rec in enumerate(recs, start=1):
        category = rec.get("category", "EFFICIENCY")
        cat_color = CATEGORY_COLORS.get(category, "#3b82f6")
        tag = f"[{category}]"
        draw.text((56, ry), f"{idx}.", fill=TEXT_MED, font=fonts["mono_sm"])
        draw.text((84, ry), tag, fill=cat_color, font=fonts["mono_sm"])
        draw.text((174, ry), safe_text(rec.get("text", ""), default="", max_len=120), fill=TEXT_MED, font=fonts["body_xs"])
        draw.text((174, ry + 19), f"→ {safe_text(rec.get('impact', ''), default='', max_len=120)}", fill=TEXT_DIM, font=fonts["mono_xs"])
        ry += 52

    # Rating scale
    section_well(draw, 1470, 1522)
    sx = 56
    segment_w = (WIDTH - 112) // len(RATING_SCALE)
    current_tier = safe_int(rating.get("tier_index"), 0)
    for idx, (name, color) in enumerate(RATING_SCALE):
        x1 = sx + idx * segment_w
        x2 = x1 + segment_w - 4
        y1 = 1486
        y2 = 1506
        draw.rectangle((x1, y1, x2, y2), fill=color)
        if idx == current_tier:
            draw.rectangle((x1 - 2, y1 - 2, x2 + 2, y2 + 2), outline=TEXT_BRIGHT, width=2)
    draw.text((56, 1509), "Unpaid Intern", fill=TEXT_DIM, font=fonts["mono_xs"])
    draw.text((WIDTH - 56, 1509), "AGI", fill=TEXT_DIM, font=fonts["mono_xs"], anchor="ra")

    # Footer
    section_well(draw, 1530, 1582)
    draw.text((48, 1548), "IS MY AGENT WORKING OR JUST VIBING?", fill=TEXT_MED, font=fonts["heading"])
    draw.text(
        (WIDTH - 48, 1548),
        "github.com/tmishra-sp/agent-performance-review",
        fill=TEXT_DIM,
        font=fonts["mono_sm"],
        anchor="ra",
    )

    crab = assets_dir / "crab.png"
    if crab.exists():
        try:
            crab_img = Image.open(crab).convert("RGBA")
            crab_img.thumbnail((34, 34))
            img.alpha_composite(crab_img, (WIDTH - 44, 1538))
        except OSError:
            pass

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rgb = img.convert("RGB")
    rgb.save(out_path, format="PNG", optimize=True, compress_level=9)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the Agent Performance Review card PNG")
    parser.add_argument("analysis_json", type=Path)
    parser.add_argument("output_png", type=Path)
    parser.add_argument("--fonts-dir", type=Path, default=Path("card-template/fonts"))
    parser.add_argument("--seed", type=int, default=None, help="Deterministic seed for roast/template choices")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    analysis = normalize_analysis(load_json(args.analysis_json))

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    assets_dir = repo_root / "card-template" / "assets"
    refs_dir = repo_root / "references"
    fonts_dir = args.fonts_dir
    if not fonts_dir.is_absolute():
        cwd_candidate = Path.cwd() / fonts_dir
        repo_candidate = repo_root / fonts_dir
        if cwd_candidate.exists():
            fonts_dir = cwd_candidate
        elif repo_candidate.exists():
            fonts_dir = repo_candidate

    render_card(
        analysis=analysis,
        out_path=args.output_png,
        fonts_dir=fonts_dir,
        assets_dir=assets_dir,
        refs_dir=refs_dir,
        seed=args.seed,
    )


if __name__ == "__main__":
    try:
        main()
    except CardGenerationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        print("Error: card generation interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:  # pragma: no cover - defensive catch-all for CLI UX
        print(f"Error: unexpected failure while generating card: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
