#!/usr/bin/env python3
"""Read-only regression suite for the dashboard UI contract.

This script validates the single-file dashboard surface without mutating server
state or starting pipeline jobs. It is intended as a safe smoke/regression
check for local or Railway deployments.

Coverage:
  - Dashboard HTML loads and includes critical panel/element ids.
  - Primary read-only API endpoints used by the dashboard return JSON.
  - Selected panel-specific probes work when backing data exists.

Usage:
  python3 scripts/dashboard_ui_regression.py
  python3 scripts/dashboard_ui_regression.py --base-url http://localhost:8080
  python3 scripts/dashboard_ui_regression.py --base-url https://your-app.up.railway.app
  python3 scripts/dashboard_ui_regression.py --include-optional
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from urllib import error, parse, request


DEFAULT_BASE_URL = os.getenv(
    "DASHBOARD_BASE_URL",
    "http://localhost:8080",
)

HTML_MARKERS = [
    'id="panel-trending"',
    'id="panel-script"',
    'id="panel-seo"',
    'id="panel-thumbnail"',
    'id="panel-queue"',
    'id="cfg-auto-upload-youtube"',
    'id="queue-list"',
    'id="yt-channels-list"',
    'id="social-platforms-list"',
    'id="brand-assets-container"',
    'id="stu-video-select"',
    'id="health-audit-btn"',
    'id="pl-payload-summary"',
    'id="pl-warn-box"',
    'function runPipelineForTopic(',
    'function uploadQueueItem(',
    'function _persistDraftContext(',
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


def _resolve_headers(username: str | None, password: str | None) -> dict[str, str]:
    env = _load_env_file(Path(".env"))
    user = username or os.getenv("DASHBOARD_USERNAME") or env.get("DASHBOARD_USERNAME", "")
    secret = password or os.getenv("DASHBOARD_PASSWORD") or env.get("DASHBOARD_PASSWORD", "")
    headers = {"Content-Type": "application/json"}
    if user and secret:
        token = base64.b64encode(f"{user}:{secret}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    return headers


def _call(base_url: str, headers: dict[str, str], path: str, timeout: int = 60) -> tuple[int, str]:
    req = request.Request(base_url.rstrip("/") + path, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


def _call_json(base_url: str, headers: dict[str, str], path: str, timeout: int = 60) -> tuple[int, object]:
    status, raw = _call(base_url, headers, path, timeout=timeout)
    try:
        data: object = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {"_raw": raw}
    return status, data


def _assert(label: str, condition: bool, detail: str, failures: list[str]) -> None:
    if condition:
        print(f"  PASS  {label}")
        return
    print(f"  FAIL  {label}: {detail}")
    failures.append(f"{label}: {detail}")


def _check_html(base_url: str, headers: dict[str, str], failures: list[str]) -> None:
    print("\n[HTML]")
    status, html = _call(base_url, headers, "/youtube_automation_dashboard.html")
    _assert("dashboard HTML fetch", status == 200, f"HTTP {status}", failures)
    if status != 200:
        return
    for marker in HTML_MARKERS:
        _assert(f"marker {marker}", marker in html, "missing from dashboard HTML", failures)


def _check_json_endpoint(base_url: str, headers: dict[str, str], path: str,
                         validator, failures: list[str]) -> object | None:
    status, data = _call_json(base_url, headers, path)
    label = f"GET {path}"
    if status != 200:
        _assert(label, False, f"HTTP {status} payload={data}", failures)
        return None
    ok, detail = validator(data)
    _assert(label, ok, detail, failures)
    return data if ok else None


def _is_dict(data: object) -> tuple[bool, str]:
    return isinstance(data, dict), f"expected object, got {type(data).__name__}"


def _is_list(data: object) -> tuple[bool, str]:
    return isinstance(data, list), f"expected array, got {type(data).__name__}"


def _has_keys(*keys: str):
    def _validator(data: object) -> tuple[bool, str]:
        if not isinstance(data, dict):
            return False, f"expected object, got {type(data).__name__}"
        missing = [key for key in keys if key not in data]
        return not missing, f"missing keys: {', '.join(missing)}"
    return _validator


def _channels_validator(data: object) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, f"expected object, got {type(data).__name__}"
    if "channels" not in data:
        return False, "missing channels"
    if not isinstance(data["channels"], list):
        return False, "channels is not an array"
    return True, ""


def _run_optional_probes(base_url: str, headers: dict[str, str], channels: list[dict],
                         studio_videos: dict | None, include_optional: bool,
                         failures: list[str]) -> None:
    print("\n[OPTIONAL]")
    if channels:
        slug = channels[0].get("slug")
        if slug:
            _check_json_endpoint(
                base_url,
                headers,
                f"/api/channels/{parse.quote(slug)}/voice",
                _is_dict,
                failures,
            )
    else:
        print("  SKIP  channel voice probe: no channels available")

    videos = []
    if isinstance(studio_videos, dict):
        raw_videos = studio_videos.get("videos", [])
        if isinstance(raw_videos, list):
            videos = raw_videos
    if videos:
        path = videos[0].get("path")
        if path:
            _check_json_endpoint(
                base_url,
                headers,
                f"/api/studio/info/{parse.quote(path)}",
                _is_dict,
                failures,
            )
    else:
        print("  SKIP  studio info probe: no studio videos available")

    if include_optional:
        _check_json_endpoint(base_url, headers, "/api/youtube/oauth-diagnostics", _is_dict, failures)
        status, data = _call_json(base_url, headers, "/api/channel/audit")
        label = "GET /api/channel/audit"
        if status != 200:
            _assert(label, False, f"HTTP {status} payload={data}", failures)
        elif isinstance(data, dict) and data.get("ok") is False and data.get("error_code") == "token_revoked":
            print("  PASS  GET /api/channel/audit (handled token_revoked state)")
        else:
            ok = isinstance(data, dict)
            _assert(label, ok, f"unexpected payload type {type(data).__name__}", failures)
    else:
        print("  SKIP  deep probes: run with --include-optional")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only regression suite for dashboard UI/API contract")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Dashboard base URL")
    parser.add_argument("--username", default=None, help="Optional Basic Auth username")
    parser.add_argument("--password", default=None, help="Optional Basic Auth password")
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Also probe optional/deeper read-only endpoints like OAuth diagnostics and channel audit",
    )
    args = parser.parse_args()

    headers = _resolve_headers(args.username, args.password)
    failures: list[str] = []

    print(f"Base URL: {args.base_url}")
    print("Mode: read-only UI contract regression")

    _check_html(args.base_url, headers, failures)

    print("\n[API]")
    _check_json_endpoint(args.base_url, headers, "/api/settings", _is_dict, failures)
    _check_json_endpoint(args.base_url, headers, "/api/pipeline/status", _has_keys("status"), failures)
    _check_json_endpoint(args.base_url, headers, "/api/pipeline/lock-status", _has_keys("running"), failures)
    _check_json_endpoint(args.base_url, headers, "/api/pipeline/jobs", _is_dict, failures)
    _check_json_endpoint(args.base_url, headers, "/api/db/stats", _is_dict, failures)
    _check_json_endpoint(args.base_url, headers, "/api/db/costs", _is_list, failures)
    _check_json_endpoint(args.base_url, headers, "/api/db/videos", _is_list, failures)
    _check_json_endpoint(args.base_url, headers, "/api/db/ypp", _is_dict, failures)
    _check_json_endpoint(args.base_url, headers, "/api/db/queue", _is_list, failures)
    channels = _check_json_endpoint(args.base_url, headers, "/api/channels", _channels_validator, failures)
    _check_json_endpoint(args.base_url, headers, "/api/social/platforms", _is_list, failures)
    _check_json_endpoint(args.base_url, headers, "/api/branding/assets", _is_dict, failures)
    _check_json_endpoint(args.base_url, headers, "/api/voices/samples", _is_dict, failures)
    studio_videos = _check_json_endpoint(args.base_url, headers, "/api/studio/videos", _is_dict, failures)

    channel_list = channels.get("channels", []) if isinstance(channels, dict) else []
    _run_optional_probes(args.base_url, headers, channel_list, studio_videos, args.include_optional, failures)

    print("\n[SUMMARY]")
    if failures:
        print(f"FAILED: {len(failures)} checks")
        for failure in failures:
            print(f"  - {failure}")
        return 2
    print("ALL UI CONTRACT CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())