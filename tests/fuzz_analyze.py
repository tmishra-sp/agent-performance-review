#!/usr/bin/env python3
"""Lightweight property/fuzz checks for scripts/analyze.sh."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYZER = ROOT / "scripts" / "analyze.sh"


def rand_ts(rng: random.Random) -> str:
    base = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
    dt = base + timedelta(seconds=rng.randint(0, 20 * 24 * 3600))
    return dt.isoformat().replace("+00:00", "Z")


def random_tool(rng: random.Random) -> str:
    return rng.choice(["read", "write", "edit", "apply_patch", "browser", "unknown_tool"])


def random_model(rng: random.Random) -> str:
    return rng.choice(
        [
            "anthropic/claude-opus-4-6",
            "anthropic/claude-sonnet-4-5",
            "anthropic/claude-haiku-4-5",
            "openai/gpt-4.1",
            "",
        ]
    )


def maybe_cost(rng: random.Random):
    if rng.random() < 0.35:
        return None
    return round(rng.uniform(0.001, 0.08), 4)


def make_record(rng: random.Random) -> str:
    # Intentionally produce a blend of valid and invalid lines.
    if rng.random() < 0.16:
        return "{ this is malformed json"
    if rng.random() < 0.1:
        return ""

    role = rng.choice(["user", "assistant", "toolResult"])
    content = []

    if rng.random() < 0.8:
        content.append({"type": "text", "text": rng.choice(["fix bug", "heartbeat", "review", "status", "done"])})

    if role != "user" and rng.random() < 0.7:
        content.append(
            {
                "type": "toolCall",
                "id": f"tc-{rng.randint(1, 9999)}",
                "name": random_tool(rng),
                "arguments": {"path": rng.choice(["src/a.ts", "package.json", "/tmp/test.txt", "README.md"])},
            }
        )

    msg = {
        "role": role,
        "content": content,
    }

    if role == "assistant" and rng.random() < 0.2:
        msg["stopReason"] = "error"

    model = random_model(rng)
    if model and role == "assistant":
        msg["model"] = model

    cost = maybe_cost(rng)
    if cost is not None:
        msg["usage"] = {"cost": {"total": cost}}

    # Randomly place timestamp/message fields in old/new style.
    if rng.random() < 0.15:
        record = {"type": "message", "message": msg}
        if rng.random() < 0.4:
            record["timestamp"] = rand_ts(rng)
    else:
        record = {"type": "message", "timestamp": rand_ts(rng), "message": msg}

    if role == "toolResult" and rng.random() < 0.25:
        record["message"]["content"].append({"type": "text", "text": '{"isError":true}'})

    return json.dumps(record)


def run_once(seed: int) -> None:
    rng = random.Random(seed)
    temp_dir = Path(tempfile.mkdtemp(prefix="apr-fuzz-analyze-"))
    try:
        sessions_dir = temp_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        session_files = rng.randint(1, 5)
        for idx in range(session_files):
            name = rng.choice([f"session-{idx}", f"heartbeat-{idx}", f"cron-{idx}"])
            path = sessions_dir / f"{name}.jsonl"
            line_count = rng.randint(1, 60)
            lines = [make_record(rng) for _ in range(line_count)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        cmd = [
            str(ANALYZER),
            str(sessions_dir),
            "--since",
            "2026-02-01",
            "--until",
            "2026-02-28",
            "--max-records",
            "10000",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            for key in ["meta", "cost", "tasks", "autonomous", "skills", "health", "rating"]:
                assert key in data, f"missing key '{key}'"
            ingest = data.get("meta", {}).get("ingestion", {})
            assert isinstance(ingest, dict), "meta.ingestion must be object"
            selected = ingest.get("selected_records", 0)
            assert isinstance(selected, int), "meta.ingestion.selected_records must be integer"
            assert selected <= 10000, "selected_records exceeded max-records"
        else:
            err = (proc.stderr or "").strip()
            assert err.startswith("Error:"), f"non-structured analyzer error: {err!r}"

        # Explicit max-record guard check with deterministic heavy input.
        heavy = sessions_dir / "heavy-heartbeat.jsonl"
        heavy_lines = []
        for i in range(40):
            heavy_lines.append(
                json.dumps(
                    {
                        "type": "message",
                        "timestamp": f"2026-02-14T03:{i%60:02d}:00Z",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "heartbeat"},
                                {"type": "toolCall", "name": "read", "arguments": {"path": "/tmp/x"}},
                            ],
                        },
                    }
                )
            )
        heavy.write_text("\n".join(heavy_lines) + "\n", encoding="utf-8")

        guard = subprocess.run(
            [
                str(ANALYZER),
                str(sessions_dir),
                "--since",
                "2026-02-01",
                "--until",
                "2026-02-28",
                "--max-records",
                "1",
            ],
            capture_output=True,
            text=True,
        )
        assert guard.returncode != 0, "expected max-record guard failure"
        assert "exceeds --max-records" in (guard.stderr or ""), f"unexpected max-record error: {guard.stderr!r}"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> None:
    for seed in range(40):
        run_once(10_000 + seed)
    print("fuzz_analyze: ok")


if __name__ == "__main__":
    main()
