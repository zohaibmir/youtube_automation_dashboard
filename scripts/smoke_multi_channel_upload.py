#!/usr/bin/env python3
"""End-to-end smoke runner for two YouTube channels.

Generates one long video (guided to 5-8 minutes) and two shorts per channel,
then uploads to YouTube via dashboard API endpoints.

Usage:
  python3 scripts/smoke_multi_channel_upload.py
  python3 scripts/smoke_multi_channel_upload.py --skip-upload
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from urllib import request

BASE_URL = "http://localhost:8080"
POLL_SECONDS = 10
MAX_WAIT_SECONDS = 60 * 45

CASES = [
    {
        "channel_slug": "truth-that-never-shared",
        "topic": "Top 7 AI tools that save creators 10+ hours per week in 2026",
        "guidance": (
            "Create an English YouTube video script and edit flow targeting "
            "5 to 8 minutes runtime, concise pacing, strong hook, practical examples."
        ),
    },
    {
        "channel_slug": "main-channel",
        "topic": "Best side hustles in 2026 for students (Hinglish practical guide)",
        "guidance": (
            "Create a Hinglish YouTube video script and edit flow targeting "
            "5 to 8 minutes runtime, natural Hindi-English mix, clear step-by-step style."
        ),
    },
]


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _auth_headers() -> dict[str, str]:
    env = _load_env_file(Path(".env"))
    user = env.get("DASHBOARD_USERNAME", "")
    password = env.get("DASHBOARD_PASSWORD", "")
    if not user or not password:
        raise RuntimeError("Missing DASHBOARD_USERNAME or DASHBOARD_PASSWORD in .env")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def _call(headers: dict[str, str], path: str, method: str = "GET", body: dict | None = None, timeout: int = 120) -> tuple[int, dict]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(BASE_URL + path, data=payload, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return resp.status, (json.loads(raw) if raw else {})


def _wait_for_ready(headers: dict[str, str], topic: str) -> dict:
    started = time.time()
    while True:
        _, status = _call(headers, "/api/pipeline/status")
        state = status.get("status")
        current_topic = status.get("topic")
        message = status.get("message", "")

        if current_topic == topic and state in ("ready", "failed"):
            return status

        if time.time() - started > MAX_WAIT_SECONDS:
            return {
                "status": "failed",
                "error": "timeout waiting for ready",
                "message": message,
                "topic": current_topic,
            }

        print(f"  poll status={state} topic={current_topic} msg={message[:90]}")
        time.sleep(POLL_SECONDS)


def _run_case(headers: dict[str, str], channel_slug: str, topic: str, guidance: str, skip_upload: bool) -> dict:
    print(f"\n=== START [{channel_slug}] ===")
    _call(headers, "/api/pipeline/cancel", "POST", {})

    run_payload = {
        "topic": topic,
        "channel_slug": channel_slug,
        "guidance": guidance,
        "shortsCount": 2,
    }
    code, run_resp = _call(headers, "/api/pipeline/run", "POST", run_payload)
    if code != 200 or not run_resp.get("ok"):
        return {"ok": False, "stage": "run", "error": str(run_resp)}

    status = _wait_for_ready(headers, topic)
    if status.get("status") != "ready":
        return {
            "ok": False,
            "stage": "generate",
            "error": status.get("error") or status.get("message") or "unknown",
        }

    if skip_upload:
        return {
            "ok": True,
            "stage": "ready",
            "youtube_url": None,
            "shorts_uploaded": 0,
            "title": status.get("title"),
        }

    up_code, up_resp = _call(
        headers,
        "/api/pipeline/upload",
        "POST",
        {"channel": channel_slug},
        timeout=1800,
    )
    if up_code != 200 or not up_resp.get("ok"):
        return {"ok": False, "stage": "upload", "error": str(up_resp)}

    return {
        "ok": True,
        "stage": "done",
        "youtube_url": up_resp.get("youtube_url"),
        "shorts_uploaded": up_resp.get("shorts_uploaded", 0),
        "title": up_resp.get("title"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test multi-channel generation + upload")
    parser.add_argument("--skip-upload", action="store_true", help="Only generate to ready state; skip YouTube upload")
    args = parser.parse_args()

    headers = _auth_headers()
    all_ok = True
    results: list[dict] = []

    for case in CASES:
        result = _run_case(
            headers,
            case["channel_slug"],
            case["topic"],
            case["guidance"],
            args.skip_upload,
        )
        result["channel_slug"] = case["channel_slug"]
        results.append(result)

        if result.get("ok"):
            print(
                f"PASS [{case['channel_slug']}] "
                f"stage={result.get('stage')} "
                f"url={result.get('youtube_url')} "
                f"shorts={result.get('shorts_uploaded')}"
            )
        else:
            print(
                f"FAIL [{case['channel_slug']}] "
                f"stage={result.get('stage')} "
                f"error={result.get('error')}"
            )
            all_ok = False

    print("\n=== SUMMARY ===")
    for result in results:
        print(json.dumps(result, ensure_ascii=False))

    return 0 if all_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
