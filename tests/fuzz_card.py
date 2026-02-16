#!/usr/bin/env python3
"""Fuzz/minimal checks for scripts/generate-card.py robustness."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / "scripts" / "generate-card.py"
FONTS = ROOT / "card-template" / "fonts"


def random_value(rng: random.Random):
    choices = [
        None,
        True,
        False,
        rng.randint(-100, 100),
        rng.random() * 100,
        "text",
        "2026-02-16",
        [],
        {},
    ]
    return rng.choice(choices)


def random_analysis(rng: random.Random) -> dict:
    # Intentionally irregular structure to stress normalization and fallback paths.
    data = {
        "meta": {"period": {"start": "2026-02-10", "end": "2026-02-16", "days": rng.randint(0, 10)}, "agent_id": "main"},
        "tasks": {
            "asked": rng.randint(0, 50),
            "completed": rng.randint(0, 50),
            "failed": rng.randint(0, 20),
            "in_progress": rng.randint(0, 10),
            "completion_rate": rng.random(),
            "highlights": [],
        },
        "cost": {
            "total_usd": round(rng.random() * 40, 2),
            "per_completed_task_usd": round(rng.random() * 5, 2),
            "by_source": {
                "user_requests": {"usd": round(rng.random() * 10, 2), "pct": rng.randint(0, 100), "count": rng.randint(0, 200)},
                "heartbeats": {"usd": round(rng.random() * 10, 2), "pct": rng.randint(0, 100), "count": rng.randint(0, 200)},
                "cron_jobs": {"usd": round(rng.random() * 10, 2), "pct": rng.randint(0, 100), "count": rng.randint(0, 200)},
                "self_initiated": {"usd": round(rng.random() * 10, 2), "pct": rng.randint(0, 100), "count": rng.randint(0, 200)},
            },
            "trend": [],
        },
        "autonomous": {
            "total_actions": rng.randint(0, 400),
            "useful_count": rng.randint(0, 120),
            "useful_rate": rng.random(),
            "notable": [],
            "three_am_sessions": rng.randint(0, 10),
            "three_am_useful": rng.randint(0, 5),
        },
        "skills": {
            "installed": rng.randint(0, 20),
            "used": rng.randint(0, 20),
            "top_used": [],
            "unused": ["skill-a", "skill-b"] if rng.random() < 0.5 else [],
        },
        "health": {
            "errors_total": rng.randint(0, 100),
            "errors_self_caused": rng.randint(0, 40),
            "tool_failures": rng.randint(0, 60),
            "context_overflows": rng.randint(0, 8),
            "compactions": rng.randint(0, 20),
            "avg_response_seconds": round(rng.random() * 35, 2),
            "read_write_ratio": rng.randint(0, 500),
            "error_rate": rng.random(),
            "error_rate_trend": [],
        },
        "rating": {
            "title": rng.choice(["Unpaid Intern", "Quiet Quitter", "Ships Code", "Founder Mode", "AGI"]),
            "color": rng.choice(["#dc2626", "#f97316", "#22c55e", "#3b82f6", "#a855f7"]),
            "tier_index": rng.randint(0, 5),
            "task_completion_rate": rng.random(),
            "percentile": rng.randint(1, 99),
            "previous_title": rng.choice(["Unpaid Intern", "Quiet Quitter", "Ships Code"]),
            "improved": rng.choice([True, False]),
        },
    }

    for _ in range(rng.randint(5, 18)):
        section = rng.choice(list(data.keys()))
        if isinstance(data[section], dict) and data[section]:
            key = rng.choice(list(data[section].keys()))
            data[section][key] = random_value(rng)

    return data


def run_one(seed: int) -> None:
    rng = random.Random(seed)
    temp_dir = Path(tempfile.mkdtemp(prefix="apr-fuzz-card-"))
    try:
        analysis_file = temp_dir / "analysis.json"
        out_png = temp_dir / "out.png"
        analysis_file.write_text(json.dumps(random_analysis(rng)), encoding="utf-8")

        proc = subprocess.run(
            [
                "python3",
                str(CARD),
                str(analysis_file),
                str(out_png),
                "--fonts-dir",
                str(FONTS),
                "--seed",
                "7",
            ],
            capture_output=True,
            text=True,
        )

        if proc.returncode == 0:
            assert out_png.exists(), "card output missing after successful run"
        else:
            err = proc.stderr or ""
            assert "Traceback" not in err, f"unexpected traceback in card failure: {err}"
            assert "Error:" in err, f"expected structured error output, got: {err!r}"

        bad_fonts = subprocess.run(
            [
                "python3",
                str(CARD),
                str(analysis_file),
                str(out_png),
                "--fonts-dir",
                str(temp_dir / "missing-fonts"),
                "--seed",
                "7",
            ],
            capture_output=True,
            text=True,
        )
        assert bad_fonts.returncode != 0, "expected missing fonts dir failure"
        assert "fonts directory does not exist" in (bad_fonts.stderr or ""), bad_fonts.stderr
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> None:
    for seed in range(30):
        run_one(20_000 + seed)
    print("fuzz_card: ok")


if __name__ == "__main__":
    main()
