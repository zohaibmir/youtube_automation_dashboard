#!/usr/bin/env python3
"""Lightweight MCP server for repo-specific context and status queries."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


ROOT = Path(__file__).resolve().parent.parent
ROADMAP_PATH = ROOT / "ROADMAP.md"
README_PATH = ROOT / "README.md"
SERVER_PATH = ROOT / "server.py"
PIPELINE_PATH = ROOT / "pipeline.py"
SOCIAL_PATH = ROOT / "social_uploader.py"
DASHBOARD_PATH = ROOT / "youtube_automation_dashboard.html"
SCHEDULER_PATH = ROOT / "scheduler.py"
JOBS_DIR = ROOT / ".jobs"
TOKENS_DIR = ROOT / "tokens"
RUNS_DIR = ROOT / "runs"
OUTPUT_DIR = ROOT / "output"
CHANNELS_REGISTRY_PATH = TOKENS_DIR / "channels.json"

mcp = FastMCP(
    "youtube-automation",
    instructions=(
        "Use this server to answer repo-specific questions about architecture, "
        "pipeline stages, local API endpoints, social upload readiness, job state, "
        "and roadmap status without re-reading large files."
    ),
    json_response=True,
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _extract_endpoints() -> list[dict[str, str]]:
    text = _read_text(SERVER_PATH)
    endpoints: list[dict[str, str]] = []
    pattern = re.compile(r'"""(GET|POST|DELETE)\s+([^\s]+)\s+[-—]\s+([^\"]+)"""')
    for method, path, summary in pattern.findall(text):
        endpoints.append({
            "method": method,
            "path": path,
            "summary": summary.strip(),
            "group": _group_endpoint(path),
        })
    return endpoints


def _group_endpoint(path: str) -> str:
    if path.startswith("/api/pipeline/"):
        return "pipeline"
    if path.startswith("/api/social/"):
        return "social"
    if path.startswith("/api/channels"):
        return "channels"
    if path.startswith("/api/studio/"):
        return "studio"
    if path.startswith("/api/branding/"):
        return "branding"
    if path.startswith("/api/channel/"):
        return "channel-seo"
    if path.startswith("/api/db/") or path.startswith("/api/settings") or path == "/api/env":
        return "dashboard-data"
    if path.startswith("/api/community-post/"):
        return "community"
    return "other"


def _extract_pipeline_stages() -> list[dict[str, str]]:
    text = _read_text(PIPELINE_PATH)
    stage_pattern = re.compile(r"# Step ([0-9]+[a-z]?)\s+—\s+(.+)")
    stages = []
    for step, title in stage_pattern.findall(text):
        stages.append({"step": step, "title": title.strip()})
    return stages


def _extract_dashboard_panels() -> list[str]:
    text = _read_text(DASHBOARD_PATH)
    return sorted(set(re.findall(r'<div id="panel-([a-z0-9-]+)"', text)))


def _extract_dashboard_api_calls() -> list[str]:
    text = _read_text(DASHBOARD_PATH)
    calls = re.findall(r"fetch\(['\"](/api/[^'\"]*)", text)
    return sorted(set(calls))


def _scheduler_policy() -> dict[str, Any]:
    text = _read_text(SCHEDULER_PATH)
    publish_time = "14:00"
    publish_match = re.search(r'_PUBLISH_TIME\s*=\s*"([0-9:]+)"', text)
    if publish_match:
        publish_time = publish_match.group(1)

    refill_threshold = 5
    threshold_match = re.search(r"_REFILL_THRESHOLD\s*=\s*(\d+)", text)
    if threshold_match:
        refill_threshold = int(threshold_match.group(1))

    from config import VIDEOS_PER_WEEK  # local import to avoid slow module init at file import time

    if VIDEOS_PER_WEEK >= 7:
        cadence = "daily"
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    elif VIDEOS_PER_WEEK >= 5:
        cadence = "weekdays"
        days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    else:
        cadence = "mon-wed-fri"
        days = ["monday", "wednesday", "friday"]

    return {
        "videos_per_week": VIDEOS_PER_WEEK,
        "publish_time_utc": publish_time,
        "refill_threshold": refill_threshold,
        "cadence": cadence,
        "days": days,
        "scheduler_channel": os.environ.get("SCHEDULER_CHANNEL") or "default",
    }


def _topic_queue_snapshot() -> dict[str, Any]:
    db_path = _find_database_path()
    if db_path is None:
        return {"database": None, "counts": {}, "recent": []}

    result: dict[str, Any] = {"database": str(db_path.name), "counts": {}, "recent": []}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        if "topic_queue" not in tables:
            result["counts"] = {"pending": 0, "processing": 0, "done": 0, "failed": 0}
            return result

        rows = cur.execute(
            "SELECT status, COUNT(*) AS c FROM topic_queue GROUP BY status"
        ).fetchall()
        counts = {"pending": 0, "processing": 0, "done": 0, "failed": 0}
        for row in rows:
            counts[row["status"]] = row["c"]
        result["counts"] = counts

        recent = cur.execute(
            "SELECT id, topic, status, retry_count, created_at FROM topic_queue ORDER BY id DESC LIMIT 10"
        ).fetchall()
        result["recent"] = [dict(row) for row in recent]
    except sqlite3.Error as exc:
        result["error"] = str(exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return result


def _recent_artifacts(limit: int = 10) -> dict[str, Any]:
    output_files = []
    if OUTPUT_DIR.exists():
        for path in OUTPUT_DIR.glob("*"):
            if path.is_file():
                output_files.append(path)

    output_files = sorted(output_files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    output_items = [
        {
            "name": p.name,
            "path": str(p.relative_to(ROOT)),
            "size_bytes": p.stat().st_size,
            "mtime": int(p.stat().st_mtime),
        }
        for p in output_files
    ]

    run_dirs = []
    if RUNS_DIR.exists():
        for path in RUNS_DIR.glob("*"):
            if path.is_dir():
                run_dirs.append(path)
    run_dirs = sorted(run_dirs, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    run_items = [
        {
            "job_id": p.name,
            "path": str(p.relative_to(ROOT)),
            "mtime": int(p.stat().st_mtime),
        }
        for p in run_dirs
    ]

    return {
        "output_files": output_items,
        "run_dirs": run_items,
        "output_count": len(output_items),
        "run_count": len(run_items),
    }


def _dashboard_panel_endpoint_map() -> dict[str, Any]:
    panels = _extract_dashboard_panels()
    api_calls = _extract_dashboard_api_calls()

    panel_prefix_map = {
        "jobs": ["/api/pipeline/jobs", "/api/pipeline/kill"],
        "queue": ["/api/pipeline/"],
        "tracker": ["/api/db/"],
        "costs": ["/api/db/"],
        "youtube": ["/api/channels"],
        "studio": ["/api/studio/", "/api/channels"],
        "branding": ["/api/branding/"],
        "health": ["/api/channel/"],
        "settings": ["/api/settings", "/api/upload-music", "/api/env"],
        "yt-automation": ["/api/social/", "/api/community-post/", "/api/settings"],
    }

    mapping: dict[str, list[str]] = {}
    for panel in panels:
        prefixes = panel_prefix_map.get(panel, [])
        matched = []
        for endpoint in api_calls:
            for prefix in prefixes:
                if endpoint.startswith(prefix):
                    matched.append(endpoint)
                    break
        mapping[panel] = sorted(set(matched))

    return {
        "panel_count": len(panels),
        "api_call_count": len(api_calls),
        "panels": panels,
        "api_calls": api_calls,
        "map": mapping,
    }


def _read_jobs(limit: int = 10) -> list[dict[str, Any]]:
    if not JOBS_DIR.exists():
        return []
    jobs: list[dict[str, Any]] = []
    for path in sorted(JOBS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            jobs.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
        if len(jobs) >= limit:
            break
    return jobs


def _read_social_platforms() -> dict[str, Any]:
    path = TOKENS_DIR / "social_platforms.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_channels_registry() -> dict[str, Any]:
    if not CHANNELS_REGISTRY_PATH.exists():
        return {}
    try:
        raw = json.loads(CHANNELS_REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    if isinstance(raw, dict):
        return raw
    return {}


def _job_failure_snapshot(limit: int = 10) -> dict[str, Any]:
    jobs = _read_jobs(limit=200)
    failures = []
    for job in jobs:
        status = str(job.get("status", "")).lower()
        if status in {"error", "failed", "stale"}:
            failures.append(job)
    failures = failures[:limit]

    buckets: dict[str, int] = {}
    for item in failures:
        message = str(item.get("error") or "unknown")
        key = message[:80]
        buckets[key] = buckets.get(key, 0) + 1

    return {
        "failure_count": len(failures),
        "failures": failures,
        "top_error_buckets": sorted(
            [{"error": k, "count": v} for k, v in buckets.items()],
            key=lambda row: row["count"],
            reverse=True,
        )[:5],
    }


def _detect_social_wiring_status() -> dict[str, Any]:
    pipeline_text = _read_text(PIPELINE_PATH)
    social_text = _read_text(SOCIAL_PATH)
    roadmap_text = _read_text(ROADMAP_PATH)
    auto_social_in_pipeline = "upload_to_platforms(" in pipeline_text
    has_provider_entrypoint = "def upload_to_platforms(" in social_text
    roadmap_mentions_partial = "NOT wired" in roadmap_text and "social_uploader.py" in roadmap_text
    return {
        "provider_entrypoint_exists": has_provider_entrypoint,
        "pipeline_calls_social_uploader": auto_social_in_pipeline,
        "roadmap_marks_partial": roadmap_mentions_partial,
        "status": "wired" if auto_social_in_pipeline else "partial",
    }


def _find_database_path() -> Path | None:
    candidates = [ROOT / "yt_automation.db", ROOT / "automation.db", ROOT / "data" / "yt_automation.db"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _db_summary() -> dict[str, Any]:
    db_path = _find_database_path()
    if db_path is None:
        return {"database": None, "tables": [], "recent_videos": []}

    summary: dict[str, Any] = {"database": str(db_path.name), "tables": [], "recent_videos": []}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        summary["tables"] = tables
        if "videos" in tables:
            rows = cur.execute(
                "SELECT id, title, youtube_id, created_at FROM videos ORDER BY id DESC LIMIT 5"
            ).fetchall()
            summary["recent_videos"] = [dict(row) for row in rows]
    except sqlite3.Error as exc:
        summary["error"] = str(exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return summary


@mcp.tool()
def get_repo_overview() -> dict[str, Any]:
    """Return a compact overview of the repo architecture, commands, and primary files."""
    return {
        "root": str(ROOT),
        "primary_files": {
            "cli": "main.py",
            "pipeline": "pipeline.py",
            "server": "server.py",
            "dashboard": "youtube_automation_dashboard.html",
            "roadmap": "ROADMAP.md",
            "settings": "SETTINGS.md",
        },
        "run_commands": {
            "server": "source .venv/bin/activate && python3 server.py",
            "pipeline": "source .venv/bin/activate && python3 main.py \"topic\"",
            "test_pipeline": "source .venv/bin/activate && python3 _run_test_pipeline.py",
        },
        "architecture": [
            "pipeline.py orchestrates end-to-end video creation and upload",
            "server.py serves the dashboard and local HTTP API",
            "youtube_automation_dashboard.html is a single-file SPA",
            "social_uploader.py owns Instagram, Facebook, and TikTok upload providers",
            "SQLite stores analytics and video history",
        ],
    }


@mcp.tool()
def get_pipeline_stage_map() -> dict[str, Any]:
    """Return the numbered pipeline stages and current social-upload wiring status."""
    return {
        "stages": _extract_pipeline_stages(),
        "social_upload": _detect_social_wiring_status(),
    }


@mcp.tool()
def get_server_api_surface(group: str = "") -> dict[str, Any]:
    """Return server.py endpoints, optionally filtered by group such as pipeline, social, studio, or channels."""
    endpoints = _extract_endpoints()
    if group:
        endpoints = [item for item in endpoints if item["group"] == group]
    return {
        "count": len(endpoints),
        "group": group or "all",
        "endpoints": endpoints,
    }


@mcp.tool()
def get_social_platform_status() -> dict[str, Any]:
    """Return configured social platform status and whether automatic pipeline wiring exists."""
    platforms = _read_social_platforms()
    normalized = {}
    for name in ("instagram", "facebook", "tiktok"):
        info = platforms.get(name, {})
        normalized[name] = {
            "enabled": bool(info.get("enabled")),
            "connected": bool(info.get("access_token")),
            "stories_enabled": bool(info.get("stories_enabled")),
            "account_name": info.get("account_name", ""),
        }
    return {
        "platforms": normalized,
        "wiring": _detect_social_wiring_status(),
    }


@mcp.tool()
def get_channel_registry_summary() -> dict[str, Any]:
    """Return a compact summary of configured YouTube channels and default channel state."""
    registry = _read_channels_registry()
    channels = registry.get("channels", []) if isinstance(registry, dict) else []
    if not isinstance(channels, list):
        channels = []

    normalized = []
    for item in channels:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "slug": item.get("slug", ""),
            "name": item.get("name", ""),
            "channel_id": item.get("channel_id", ""),
            "is_default": bool(item.get("is_default", False)),
        })

    default_slugs = [c["slug"] for c in normalized if c.get("is_default")]
    return {
        "has_registry": bool(registry),
        "count": len(normalized),
        "default": default_slugs[0] if default_slugs else None,
        "channels": normalized,
    }


@mcp.tool()
def get_recent_job_state(limit: int = 10) -> dict[str, Any]:
    """Return recent pipeline jobs from .jobs for quick operational context."""
    jobs = _read_jobs(limit=limit)
    running = [job for job in jobs if job.get("status") == "running"]
    return {
        "count": len(jobs),
        "running_count": len(running),
        "jobs": jobs,
    }


@mcp.tool()
def get_recent_job_failures(limit: int = 10) -> dict[str, Any]:
    """Return recent failed/stale jobs and grouped error buckets."""
    return _job_failure_snapshot(limit=limit)


@mcp.tool()
def get_database_snapshot() -> dict[str, Any]:
    """Return a light SQLite snapshot with table names and recent videos if available."""
    return _db_summary()


@mcp.tool()
def get_scheduler_state() -> dict[str, Any]:
    """Return scheduler cadence, publish timing, and queue refill policy."""
    return _scheduler_policy()


@mcp.tool()
def get_topic_queue_state() -> dict[str, Any]:
    """Return topic queue status counts and recent queue records."""
    return _topic_queue_snapshot()


@mcp.tool()
def get_recent_artifacts(limit: int = 10) -> dict[str, Any]:
    """Return recent files from output/ and recent run directories from runs/."""
    return _recent_artifacts(limit=limit)


@mcp.tool()
def get_dashboard_panel_map() -> dict[str, Any]:
    """Return dashboard panel IDs, API calls, and a best-effort panel-to-endpoint map."""
    return _dashboard_panel_endpoint_map()


@mcp.tool()
def get_runtime_summary() -> dict[str, Any]:
    """Return a compact all-in-one summary of jobs, queue, scheduler, social status, and artifacts."""
    return {
        "scheduler": _scheduler_policy(),
        "jobs": get_recent_job_state(limit=8),
        "job_failures": _job_failure_snapshot(limit=8),
        "topic_queue": _topic_queue_snapshot(),
        "social": get_social_platform_status(),
        "channels": get_channel_registry_summary(),
        "artifacts": _recent_artifacts(limit=8),
    }


@mcp.resource("repo://overview")
def repo_overview_resource() -> str:
    """Compact repo overview resource."""
    return json.dumps(get_repo_overview(), indent=2)


@mcp.resource("repo://roadmap")
def roadmap_resource() -> str:
    """Expose the roadmap for selective attachment as MCP context."""
    return _read_text(ROADMAP_PATH)


@mcp.resource("repo://api-surface")
def api_surface_resource() -> str:
    """Expose the grouped API surface from server.py."""
    return json.dumps(get_server_api_surface(), indent=2)


@mcp.resource("repo://runtime-summary")
def runtime_summary_resource() -> str:
    """Expose one compact runtime status snapshot for quick context attachment."""
    return json.dumps(get_runtime_summary(), indent=2)


@mcp.resource("repo://dashboard-map")
def dashboard_map_resource() -> str:
    """Expose dashboard panel-to-endpoint mapping and API call inventory."""
    return json.dumps(get_dashboard_panel_map(), indent=2)


@mcp.resource("repo://job-failures")
def job_failures_resource() -> str:
    """Expose recent failure-focused job summary for debugging context."""
    return json.dumps(get_recent_job_failures(), indent=2)


@mcp.prompt(title="Implementation Brief")
def implementation_brief(feature: str) -> str:
    """Create a compact repo-aware implementation brief for a requested feature."""
    return (
        f"Prepare an implementation brief for the feature: {feature}. "
        "Use the MCP tools to identify the owning files, missing integration point, "
        "runtime side effects, and the minimum safe change."
    )


@mcp.prompt(title="Roadmap Audit")
def roadmap_audit(feature: str) -> str:
    """Create a compact roadmap audit prompt for a requested feature."""
    return (
        f"Audit the roadmap status of: {feature}. "
        "State what is implemented, what is partial, what is missing, and cite the actual owning files."
    )


def main() -> None:
    os.chdir(ROOT)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()