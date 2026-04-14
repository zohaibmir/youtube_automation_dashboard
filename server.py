#!/usr/bin/env python3
"""server.py — Local development server for the YouTube Automation dashboard.

Serves all static files on port 8080 AND exposes API endpoints:

    GET /api/env          →  Returns keys from .env as JSON (localhost only)
    GET /api/db/stats     →  Channel stats from SQLite (views, revenue, subs, watch hours)
    GET /api/db/costs     →  Monthly API costs from api_costs table
    GET /api/db/videos    →  Video history from videos table
    GET /api/db/ypp       →  YPP progress (subs + watch hours)
    GET /api/db/queue     →  Pending topics from topic_queue table

Usage:
    python server.py          # default port 8080
    PORT=9000 python server.py

Docker:
    command: python server.py
"""

import base64
import json
import os
import sys
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ── .env reader ───────────────────────────────────────────────────────────────
try:
    from dotenv import dotenv_values as _dotenv_values

    def _read_env(path: str) -> dict:
        return dict(_dotenv_values(path))

except ImportError:
    def _read_env(path: str) -> dict:
        vals: dict = {}
        try:
            for raw in Path(path).read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                vals[key.strip()] = val
        except Exception:
            pass
        return vals

# ── Database helpers (optional — skipped if db/config not available) ──────────

def _update_env_key(key: str, value: str) -> None:
    """Update or add a single key in the .env file."""
    env_path = Path(__file__).parent / ".env"
    lines = []
    found = False
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            if raw.strip().startswith(key + "="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(raw)
    if not found:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_DB_AVAILABLE = False
try:
    # Add project directory to path so we can import our modules
    _PROJECT_DIR = str(Path(__file__).parent)
    if _PROJECT_DIR not in sys.path:
        sys.path.insert(0, _PROJECT_DIR)

    from database import (
        get_channel_stats, get_monthly_costs, get_video_history,
        get_ypp_progress, init_db, get_conn,
        get_settings, save_setting,
    )
    init_db()
    _DB_AVAILABLE = True
except Exception as _db_err:
    print(f"[server.py] DB not available ({_db_err}) — /api/db/* will return empty data")

# Ensure all storage directories exist on the persistent disk.
# This runs unconditionally at startup — critical on Render where /data is a
# fresh volume that starts empty after the first deploy or disk re-attach.
try:
    from config import AUDIO_DIR, IMAGES_DIR, OUTPUT_DIR
    for _d in [AUDIO_DIR, IMAGES_DIR, OUTPUT_DIR,
               os.path.join(OUTPUT_DIR, "shorts"),
               os.path.join(OUTPUT_DIR, "clips")]:
        os.makedirs(_d, exist_ok=True)
    print(f"[server.py] Storage dirs ready: audio={AUDIO_DIR} images={IMAGES_DIR} output={OUTPUT_DIR}")
except Exception as _dir_err:
    print(f"[server.py] WARNING: could not create storage dirs: {_dir_err}")


def _db_stats() -> dict:
    if not _DB_AVAILABLE:
        return {}
    try:
        return get_channel_stats()
    except Exception:
        return {}


def _db_costs() -> list:
    if not _DB_AVAILABLE:
        return []
    try:
        return get_monthly_costs()
    except Exception:
        return []


def _db_videos(limit: int = 50) -> list:
    if not _DB_AVAILABLE:
        return []
    try:
        return get_video_history(limit)
    except Exception:
        return []


def _db_ypp() -> dict:
    if not _DB_AVAILABLE:
        return {}
    try:
        return get_ypp_progress()
    except Exception:
        return {}


def _db_queue() -> list:
    if not _DB_AVAILABLE:
        return []
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT id, topic, type, scheduled, status, priority, added_at "
            "FROM topic_queue ORDER BY "
            "CASE WHEN status='pending' THEN 0 ELSE 1 END, priority ASC, id DESC LIMIT 200"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _db_settings() -> dict:
    if not _DB_AVAILABLE:
        return {}
    try:
        return get_settings()
    except Exception:
        return {}


# ── Exposed .env keys ──────────────────────────────────────────────────────────
_EXPOSED_KEYS = {
    "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID",
    "PEXELS_API_KEY", "CHANNEL_NAME", "CHANNEL_NICHE", "CHANNEL_LANGUAGE",
    "CHANNEL_AUDIENCE", "VIDEOS_PER_WEEK", "DEFAULT_VISIBILITY",
    "YOUTUBE_CATEGORY_ID", "VOICE_STABILITY", "VOICE_SIMILARITY",
    "VOICE_STYLE", "YOUTUBE_CLIENT_SECRETS", "YOUTUBE_WEB_CLIENT_ID",
    "VISUAL_MODE", "GTTS_SPEECH_RATE",
    "TTS_PROVIDER", "EDGE_TTS_VOICE",
    "KEN_BURNS_ZOOM", "CROSSFADE_DURATION", "BG_MUSIC_VOLUME_DB",
    "BG_MUSIC_PATH", "INTRO_DURATION", "OUTRO_DURATION", "OUTRO_CTA_TEXT",
}

_ENV_PATH = str(Path(__file__).parent / ".env")
_LOCALHOST = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}

# Public static allowlist for hosted mode. This avoids exposing repository
# internals (source, tokens, env files) through the raw file server.
_PUBLIC_STATIC_FILES = {
    "/youtube_automation_dashboard.html",
    "/thumbnail_designer.html",
    "/southasian_youtube_dashboard.html",
    "/thumbnail.jpg",
    "/favicon.ico",
    "/voices.json",
}
_PUBLIC_STATIC_PREFIXES = (
    "/output/",
    "/audio/",
    "/images/",
    "/branding/",
    "/music/",
    "/scripts/voice_samples/",
)
_BLOCKED_STATIC_PREFIXES = (
    "/.git",
    "/.github",
    "/.vscode",
    "/tokens/",
    "/runs/",
    "/.jobs/",
    "/.env",
)
_BLOCKED_STATIC_EXTENSIONS = (
    ".py",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".sh",
    ".pem",
    ".key",
    ".log",
)

_DB_ROUTES = {
    "/api/db/stats":  _db_stats,
    "/api/db/costs":  _db_costs,
    "/api/db/videos": _db_videos,
    "/api/db/ypp":    _db_ypp,
    "/api/db/queue":  _db_queue,
    "/api/settings":  _db_settings,
}

# ── HTTP Basic Authentication ──────────────────────────────────────────────────
# Set DASHBOARD_USERNAME and DASHBOARD_PASSWORD env vars to enable auth.
# If not set, the dashboard is public (no auth required).
_DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "").strip()
_DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "").strip()
_AUTH_ENABLED = bool(_DASHBOARD_USERNAME and _DASHBOARD_PASSWORD)

# ── Pipeline preview state ─────────────────────────────────────────────────────
_pipeline_job: dict = {
    "status":        "idle",   # idle | running | ready | uploading | done | failed
    "topic":         None,
    "channel_slug":  None,
    "message":       "",
    "video_url":     None,
    "thumbnail_url": None,
    "title":         None,
    "vid_db_id":     None,
    "youtube_url":   None,
    "error":         None,
    # internal — not sent to client
    "_content":      None,
    "_video_path":   None,
    "_thumb_path":   None,
    "_shorts_paths": [],
}
_pipeline_lock = threading.Lock()

# Hosted OAuth pending state for adding YouTube channels from production UI.
_pending_channel_oauth: dict = {}
_pending_channel_oauth_lock = threading.Lock()


def _run_pipeline_bg(topic: str, script_text=None, seo=None, thumb_data_url=None, guidance=None, voice_id=None, shorts_count=0, channel_slug=None, language=None, duration_hint=None) -> None:
    """Background thread: runs pipeline steps 1-5, updates _pipeline_job."""
    try:
        from pipeline import run_preview
    except Exception as e:
        with _pipeline_lock:
            _pipeline_job.update({"status": "failed", "message": str(e), "error": str(e)})
        return

    def _progress(msg: str) -> None:
        with _pipeline_lock:
            _pipeline_job["message"] = msg

    try:
        video_path, thumb_path, content, vid_id = run_preview(
            topic, progress_cb=_progress,
            script_text=script_text, seo=seo, thumb_data_url=thumb_data_url,
            channel_slug=channel_slug, guidance=guidance, voice_id=voice_id,
            shorts_count=shorts_count, language=language, duration_hint=duration_hint,
        )
        slug = video_path.replace("\\", "/").split("/")[-1]  # just the filename
        shorts_paths = content.pop("_shorts_paths", [])
        with _pipeline_lock:
            _pipeline_job.update({
                "status":        "ready",
                "message":       "✓ Video ready for review!",
                "video_url":     f"/output/{slug}",
                "thumbnail_url": "/thumbnail.jpg",
                "title":         content.get("title", topic),
                "vid_db_id":     vid_id,
                "shorts_count":  len(shorts_paths),
                "channel_slug":  channel_slug,
                "_content":      content,
                "_video_path":   video_path,
                "_thumb_path":   thumb_path,
                "_shorts_paths": shorts_paths,
            })
    except Exception as exc:
        with _pipeline_lock:
            _pipeline_job.update({
                "status":  "failed",
                "message": str(exc),
                "error":   str(exc),
            })


class DashboardHandler(SimpleHTTPRequestHandler):

    def _check_auth(self) -> bool:
        """Check HTTP Basic Auth credentials. Returns True if auth is valid or not required."""
        if not _AUTH_ENABLED:
            return True
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="YouTube Automation Dashboard"')
            self.end_headers()
            return False
        try:
            encoded = auth_header[6:]
            decoded = base64.b64decode(encoded).decode("utf-8")
            username, password = decoded.split(":", 1)
            if username == _DASHBOARD_USERNAME and password == _DASHBOARD_PASSWORD:
                return True
        except Exception:
            pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="YouTube Automation Dashboard"')
        self.end_headers()
        return False

    def _is_localhost(self) -> bool:
        """Check if request is from localhost. Allows 127.0.0.1, ::1, ::ffff:127.0.0.1"""
        return self.client_address[0] in _LOCALHOST

    def _is_request_allowed(self, require_localhost: bool = False) -> bool:
        """Check if request is allowed.
        Args:
            require_localhost: If True, require localhost when auth is not enabled.
                             If False, allow any address when auth is not enabled.
        Returns True if request should be allowed.
        """
        # Always allow localhost
        if self._is_localhost():
            return True
        # If auth is enabled, request already passed _check_auth, so allow it
        if _AUTH_ENABLED:
            return True
        # If auth is not enabled and require_localhost is False, allow (production mode)
        if not require_localhost:
            return True
        # If auth is not enabled and require_localhost is True, deny remote requests
        return False

    def _deny_request(self, reason: str = "Not allowed", status_code: int = 403) -> bool:
        """Send error response and return True to signal early exit."""
        self._json_response({"ok": False, "error": reason}, status_code=status_code)
        return True

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        # OAuth callback must be reachable without credentials (Google redirects here via popup)
        if path != "/api/channels/oauth/callback":
            if not self._check_auth():
                return
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/youtube_automation_dashboard.html")
            self.end_headers()
            return
        if path == "/api/env":
            self._json_response(self._handle_env())
        elif path == "/api/debug/paths":
            self._json_response(self._handle_debug_paths())
        elif path == "/api/pipeline/status":
            with _pipeline_lock:
                safe = {k: v for k, v in _pipeline_job.items() if not k.startswith("_")}
            self._json_response(safe)
        elif path == "/api/pipeline/lock-status":
            from pipeline import pipeline_status
            self._json_response(pipeline_status())
        elif path == "/api/pipeline/jobs":
            from pipeline import list_jobs
            self._json_response({"jobs": list_jobs()})
        elif path == "/api/channels":
            self._handle_channels_get()
        elif path == "/api/channels/oauth/callback":
            self._handle_channel_oauth_callback()
        elif path == "/api/youtube/oauth-diagnostics":
            self._handle_youtube_oauth_diagnostics()
        elif path == "/api/channels/export-tokens":
            self._handle_channels_export_tokens()
        elif path == "/api/voices/samples":
            self._handle_voices_samples()
        elif path.startswith("/api/channels/") and path.endswith("/voice"):
            self._handle_channel_voice_get(path)
        elif path == "/api/social/platforms":
            self._handle_social_platforms_get()
        elif path == "/api/branding/assets":
            self._handle_branding_assets_get()
        elif path == "/api/queue/pending":
            self._handle_queue_pending_get()
        elif path.startswith("/api/channel/audit"):
            self._handle_channel_audit()
        elif path == "/api/studio/videos":
            self._handle_studio_videos_get()
        elif path.startswith("/api/studio/info/"):
            self._handle_studio_video_info(path)
        elif path.startswith("/api/studio/download/"):
            self._handle_studio_download_get(path)
        elif path in _DB_ROUTES:
            self._json_response(_DB_ROUTES[path]())
        else:
            if not self._is_allowed_static_path(path):
                self.send_response(404)
                self.end_headers()
                return
            super().do_GET()

    def do_POST(self) -> None:
        if not self._check_auth():
            return
        path = self.path.split("?")[0]

        if path == "/api/pipeline/run":
            self._handle_pipeline_run()
        elif path == "/api/scheduler/run-next":
            self._handle_scheduler_run_next()
        elif path == "/api/pipeline/upload":
            self._handle_pipeline_upload()
        elif path == "/api/pipeline/cancel":
            with _pipeline_lock:
                _pipeline_job.update({
                    "status": "idle", "topic": None, "message": "",
                    "video_url": None, "thumbnail_url": None, "title": None,
                    "vid_db_id": None, "youtube_url": None, "error": None, "channel_slug": None,
                    "_content": None, "_video_path": None, "_thumb_path": None, "_shorts_paths": [],
                })
            self._json_response({"ok": True})
        elif path == "/api/pipeline/kill" or path.startswith("/api/pipeline/kill/"):
            self._handle_pipeline_kill(path)
        elif path == "/api/settings/sync-env":
            self._handle_settings_sync_env()
        elif path == "/api/settings":
            self._handle_settings_post()
        elif path == "/api/upload-music":
            self._handle_music_upload()
        elif path == "/api/channels/add":
            self._handle_channel_add()
        elif path == "/api/channels/import-tokens":
            self._handle_channels_import_tokens()
        elif path == "/api/channels/default":
            self._handle_channel_set_default()
        elif path.startswith("/api/channels/") and path.endswith("/voice"):
            self._handle_channel_voice_post(path)
        elif path == "/api/social/config":
            self._handle_social_config_post()
        elif path == "/api/social/upload":
            self._handle_social_upload()
        elif path == "/api/branding/generate":
            self._handle_branding_generate()
        elif path == "/api/branding/upload-banner":
            self._handle_branding_upload_banner()
        elif path == "/api/branding/set-trailer":
            self._handle_branding_set_trailer()
        elif path == "/api/channel/update":
            self._handle_channel_update()
        elif path == "/api/channel/fix-video":
            self._handle_channel_fix_video()
        elif path == "/api/channel/fix-all":
            self._handle_channel_fix_all()
        elif path == "/api/studio/extract-clips":
            self._handle_studio_extract_clips()
        elif path == "/api/studio/upload-main":
            self._handle_studio_upload_main()
        elif path == "/api/studio/upload-clips":
            self._handle_studio_upload_clips()
        elif path == "/api/studio/delete":
            self._handle_studio_delete()
        elif path == "/api/community-post/generate":
            self._handle_community_post_generate()
        elif path == "/api/queue/reorder":
            self._handle_queue_reorder_post()
        elif path == "/api/queue/replace":
            self._handle_queue_replace_post()
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self) -> None:
        if not self._check_auth():
            return
        path = self.path.split("?")[0]
        if path == "/api/upload-music":
            self._handle_music_delete()
        elif path == "/api/studio/delete":
            self._handle_studio_delete()
        elif path.startswith("/api/channels/"):
            self._handle_channel_remove(path)
        elif path.startswith("/api/social/platforms/"):
            self._handle_social_platform_remove(path)
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_pipeline_run(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            topic = data.get("topic", "").strip()
            channel_slug   = data.get("channel_slug", "").strip() or None
            if not topic:
                self._json_response({"ok": False, "error": "topic required"}); return
            with _pipeline_lock:
                if _pipeline_job["status"] == "running":
                    self._json_response({"ok": False, "error": "Pipeline already running"}); return
                _pipeline_job.update({
                    "status": "running", "topic": topic, "message": "Starting…",
                    "video_url": None, "thumbnail_url": None, "title": None,
                    "vid_db_id": None, "youtube_url": None, "error": None, "channel_slug": channel_slug,
                    "_content": None, "_video_path": None, "_thumb_path": None, "_shorts_paths": [],
                })
            # Optional pre-computed assets from dashboard
            script_text    = data.get("scriptText", "").strip() or None
            seo_title      = data.get("seoTitle", "").strip() or None
            seo_description= data.get("seoDescription", "").strip() or None
            seo_tags_raw   = data.get("seoTags", "").strip() or None
            thumb_data_url = data.get("thumbDataUrl", "").strip() or None
            guidance       = data.get("guidance", "").strip() or None
            voice_id       = data.get("voice_id", "").strip() or None
            language       = data.get("language", "").strip() or None
            duration_hint  = data.get("duration_hint", "").strip() or None
            shorts_count   = int(data.get("shortsCount", 0) or 0)
            seo = None
            if seo_title or seo_description or seo_tags_raw:
                seo = {
                    "title":       seo_title or "",
                    "description": seo_description or "",
                    "tags":        [t.strip() for t in (seo_tags_raw or "").split(",") if t.strip()],
                }
            t = threading.Thread(
                target=_run_pipeline_bg,
                args=(topic,),
                kwargs={"script_text": script_text, "seo": seo, "thumb_data_url": thumb_data_url,
                    "guidance": guidance, "voice_id": voice_id, "shorts_count": shorts_count,
                    "channel_slug": channel_slug, "language": language, "duration_hint": duration_hint},
                daemon=True,
            )
            t.start()
            self._json_response({"ok": True})
        except Exception as ex:
            self._json_response({"ok": False, "error": str(ex)})

    def _handle_scheduler_run_next(self) -> None:
        """Dequeue the next pending topic and run the pipeline — same logic as the scheduler."""
        try:
            from topic_queue import dequeue_topic, mark_topic_done, mark_topic_failed, pending_count
            from config import SCHEDULER_CHANNEL, SCHEDULER_SHORTS_COUNT
        except Exception as ex:
            self._json_response({"ok": False, "error": f"Import error: {ex}"}); return

        with _pipeline_lock:
            if _pipeline_job["status"] == "running":
                self._json_response({"ok": False, "error": "Pipeline already running"}); return

        topic = dequeue_topic()
        if not topic:
            self._json_response({"ok": False, "error": "Queue is empty — no pending topics"}); return

        # Read optional channel override from request body
        channel_slug = None
        shorts_count = None
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                body = json.loads(self.rfile.read(length))
                channel_slug = body.get("channel_slug", "").strip() or None
                if isinstance(body, dict) and body.get("shorts_count") is not None:
                    shorts_count = int(body.get("shorts_count"))
        except Exception:
            pass
        channel_slug = channel_slug or SCHEDULER_CHANNEL or None
        if shorts_count is None:
            shorts_count = SCHEDULER_SHORTS_COUNT
        try:
            shorts_count = max(0, min(3, int(shorts_count)))
        except Exception:
            shorts_count = 2

        with _pipeline_lock:
            _pipeline_job.update({
                "status": "running", "topic": topic, "message": "Starting…",
                "video_url": None, "thumbnail_url": None, "title": None,
                "vid_db_id": None, "youtube_url": None, "error": None, "channel_slug": channel_slug,
                "_content": None, "_video_path": None, "_thumb_path": None, "_shorts_paths": [],
            })

        def _bg():
            try:
                _run_pipeline_bg(topic, channel_slug=channel_slug, shorts_count=shorts_count)
                mark_topic_done(topic)
            except Exception as exc:
                mark_topic_failed(topic)
                with _pipeline_lock:
                    _pipeline_job.update({"status": "failed", "error": str(exc)})

        t = threading.Thread(target=_bg, daemon=True)
        t.start()
        self._json_response({"ok": True, "topic": topic, "shorts_count": shorts_count})

    def _handle_pipeline_upload(self) -> None:
        if not _DB_AVAILABLE:
            self._json_response({"ok": False, "error": "DB not available"}); return
        # Read optional channel selection from request body
        channel_slug = None
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                body = json.loads(self.rfile.read(length))
                channel_slug = body.get("channel") or None
        except Exception:
            pass
        with _pipeline_lock:
            job_status = _pipeline_job["status"]
            video_path = _pipeline_job["_video_path"]
            thumb_path = _pipeline_job["_thumb_path"]
            content    = _pipeline_job["_content"]
            vid_db_id  = _pipeline_job["vid_db_id"]
            shorts_paths = _pipeline_job.get("_shorts_paths", [])
        if job_status != "ready":
            self._json_response({"ok": False, "error": f"No video ready (status: {job_status})"}); return
        # Validate video file before attempting upload
        if not video_path or not os.path.isfile(video_path):
            self._json_response({"ok": False, "error": "Video file not found on disk"}); return
        if os.path.getsize(video_path) < 1024:
            self._json_response({"ok": False, "error": "Video file is too small — likely corrupt"}); return
        with _pipeline_lock:
            _pipeline_job["status"] = "uploading"
            _pipeline_job["message"] = "Uploading to YouTube…"
        try:
            from youtube_uploader import upload_video as _upload
            from database import log_video_complete, is_video_uploaded, get_video_record
            # Guard: skip main video upload if already uploaded
            if is_video_uploaded(vid_db_id):
                rec = get_video_record(vid_db_id)
                youtube_id = rec["youtube_id"]
                yt_url = f"https://youtube.com/watch?v={youtube_id}"
                import logging as _log
                _log.getLogger(__name__).info("Video already uploaded (vid=%d, yt=%s) — skipping", vid_db_id, youtube_id)
            else:
                youtube_id = _upload(video_path, thumb_path, content, channel_slug=channel_slug)
                segments = content.get("segments", [])
                duration_s = sum(seg.get("duration_s", 45) for seg in segments)
                log_video_complete(vid_db_id, content.get("title", ""), youtube_id, duration_s)
                yt_url = f"https://youtube.com/watch?v={youtube_id}"
            # Upload Shorts if any were generated
            shorts_uploaded = 0
            for sp in (shorts_paths or []):
                try:
                    import os as _os
                    if not _os.path.isfile(sp):
                        continue
                    short_title = f"{content.get('title', '')} #Shorts"
                    short_content = {
                        "title": short_title[:100],
                        "description": content.get("description", ""),
                        "tags": content.get("tags", []) + ["Shorts"],
                    }
                    _upload(sp, thumb_path, short_content, channel_slug=channel_slug)
                    shorts_uploaded += 1
                except Exception as se:
                    import logging as _log
                    _log.getLogger(__name__).error("Shorts upload failed: %s", se)
            with _pipeline_lock:
                msg = f"✓ Uploaded! {yt_url}"
                if shorts_uploaded:
                    msg += f" + {shorts_uploaded} Short(s)"
                _pipeline_job.update({
                    "status":      "done",
                    "message":     msg,
                    "youtube_url": yt_url,
                })
            self._json_response({"ok": True, "youtube_url": yt_url})
        except Exception as exc:
            with _pipeline_lock:
                _pipeline_job.update({"status": "failed", "message": str(exc), "error": str(exc)})
            self._json_response({"ok": False, "error": str(exc)})

    def _handle_queue_pending_get(self) -> None:
        """GET /api/queue/pending — pending queue in run-next order."""
        try:
            from topic_queue import get_pending_topics
            self._json_response({"ok": True, "items": get_pending_topics(limit=300)})
        except Exception as exc:
            self._json_response({"ok": False, "error": str(exc)})

    def _handle_queue_reorder_post(self) -> None:
        """POST /api/queue/reorder — persist pending queue order.

        Body: {ordered_ids: [12, 8, 5, ...]}
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            ordered_ids = data.get("ordered_ids") if isinstance(data, dict) else None
            if not isinstance(ordered_ids, list) or not ordered_ids:
                self._json_response({"ok": False, "error": "ordered_ids list is required"})
                return
            from topic_queue import reorder_pending_topics
            changed = reorder_pending_topics(ordered_ids)
            self._json_response({"ok": True, "updated": changed})
        except Exception as exc:
            self._json_response({"ok": False, "error": str(exc)})

    def _handle_queue_replace_post(self) -> None:
        """POST /api/queue/replace — clear queue and seed new topics.

        Body:
          {
            "topics": ["...", "..."],
            "clear_existing": true,
            "topic_type": "AI-generated"
          }
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            topics = data.get("topics") if isinstance(data, dict) else None
            clear_existing = bool(data.get("clear_existing", True)) if isinstance(data, dict) else True
            topic_type = (data.get("topic_type") or "AI-generated").strip() if isinstance(data, dict) else "AI-generated"

            if not isinstance(topics, list) or not topics:
                self._json_response({"ok": False, "error": "topics list is required"})
                return

            clean_topics = [str(t).strip() for t in topics if str(t).strip()]
            if not clean_topics:
                self._json_response({"ok": False, "error": "no valid topics provided"})
                return

            if clear_existing:
                from database import _conn
                with _conn() as conn:
                    conn.execute("DELETE FROM topic_queue")
                    conn.commit()

            from topic_queue import enqueue_topics, pending_count
            added = enqueue_topics(clean_topics, topic_type=topic_type)
            self._json_response({
                "ok": True,
                "added": added,
                "pending": pending_count(),
                "cleared": clear_existing,
            })
        except Exception as exc:
            self._json_response({"ok": False, "error": str(exc)})

    def _handle_pipeline_kill(self, path: str = "/api/pipeline/kill") -> None:
        """POST /api/pipeline/kill[/<job_id>] — Kill running pipeline job(s) and clear lock."""
        from pipeline import kill_pipeline
        job_id = None
        if path.startswith("/api/pipeline/kill/"):
            job_id = path.rsplit("/", 1)[-1].strip() or None
        if not job_id:
            try:
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length)) if length else {}
                if isinstance(data, dict):
                    job_id = (data.get("job_id") or "").strip() or None
            except Exception:
                job_id = None

        result = kill_pipeline(job_id=job_id)
        # Also reset the in-memory pipeline state
        with _pipeline_lock:
            _pipeline_job.update({
                "status": "idle", "topic": None, "message": "",
                "video_url": None, "thumbnail_url": None, "title": None,
                "vid_db_id": None, "youtube_url": None, "error": None, "channel_slug": None,
                "_content": None, "_video_path": None, "_thumb_path": None, "_shorts_paths": [],
            })
        self._json_response(result)

    def _handle_settings_sync_env(self) -> None:
        """POST /api/settings/sync-env — Write dashboard production settings to .env."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            # Map of dashboard field → .env key
            env_map = {
                "channelName":    "CHANNEL_NAME",
                "outroCta":       "OUTRO_CTA_TEXT",
                "introDur":       "INTRO_DURATION",
                "outroDur":       "OUTRO_DURATION",
                "kenBurns":       "KEN_BURNS_ZOOM",
                "crossfade":      "CROSSFADE_DURATION",
                "musicVol":       "BG_MUSIC_VOLUME_DB",
                "ttsProvider":    "TTS_PROVIDER",
                "edgeVoice":      "EDGE_TTS_VOICE",
                "ytVis":          "DEFAULT_VISIBILITY",
                "ytCategory":     "YOUTUBE_CATEGORY_ID",
                # YouTube Automation features
                "autoChapters":      "AUTO_CHAPTERS",
                "pinComment":        "PIN_FIRST_COMMENT",
                "pinnedCommentText": "PINNED_COMMENT_TEXT",
                "autoEndScreens":    "AUTO_END_SCREENS",
                # Reddit distribution
                "redditEnabled":     "REDDIT_ENABLED",
                "redditSubreddits":  "REDDIT_SUBREDDITS",
                "redditFlair":       "REDDIT_POST_FLAIR",
            }
            updated = []
            for js_key, env_key in env_map.items():
                val = data.get(js_key)
                if val is not None and str(val).strip():
                    # Convert kenBurns percentage (5) to decimal (0.05)
                    if js_key == "kenBurns":
                        val = str(float(val) / 100)
                    _update_env_key(env_key, str(val))
                    updated.append(env_key)
            self._json_response({"ok": True, "updated": updated})
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_settings_post(self) -> None:
        if not _DB_AVAILABLE:
            self._json_response({"ok": False, "error": "DB not available"}); return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            data = json.loads(raw)
            dtype = data.get("type", "config")
            if dtype == "__clear__":
                conn = get_conn()
                conn.execute("DELETE FROM settings")
                conn.commit()
                conn.close()
            else:
                save_setting(dtype, data.get("data", {}))
            self._json_response({"ok": True})
        except Exception as ex:
            self._json_response({"ok": False, "error": str(ex)})

    def _handle_music_upload(self) -> None:
        """Accept a multipart/form-data .mp3 upload and save to music/bg_music.mp3."""
        if not self._is_request_allowed(require_localhost=False): return
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._json_response({"ok": False, "error": "Expected multipart/form-data"})
            return
        # Extract boundary
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[len("boundary="):].strip('"')
        if not boundary:
            self._json_response({"ok": False, "error": "No boundary found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        # Find file data between boundary markers
        sep = ("--" + boundary).encode()
        parts = body.split(sep)
        file_data = None
        for part in parts:
            if b"filename=" in part and b"Content-Type" in part:
                # Split headers from body (double CRLF)
                idx = part.find(b"\r\n\r\n")
                if idx >= 0:
                    file_data = part[idx + 4:]
                    # Remove trailing \r\n
                    if file_data.endswith(b"\r\n"):
                        file_data = file_data[:-2]
        if not file_data:
            self._json_response({"ok": False, "error": "No file data found"})
            return
        music_dir = Path(__file__).parent / "music"
        music_dir.mkdir(exist_ok=True)
        dest = music_dir / "bg_music.mp3"
        with open(dest, "wb") as f:
            f.write(file_data)
        _update_env_key("BG_MUSIC_PATH", str(dest))
        self._json_response({"ok": True, "path": str(dest)})

    def _handle_music_delete(self) -> None:
        """Remove background music file and clear the .env key."""
        if not self._is_request_allowed(require_localhost=False): return
        dest = Path(__file__).parent / "music" / "bg_music.mp3"
        if dest.exists():
            dest.unlink()
        _update_env_key("BG_MUSIC_PATH", "")
        self._json_response({"ok": True})

    # ── Channel management ─────────────────────────────────────────────────

    def _handle_channels_get(self) -> None:
        if not self._is_request_allowed(require_localhost=False):
            self._json_response({"ok": False, "error": "Not allowed"}, status_code=403); return
        try:
            from youtube_uploader import list_channels
            self._json_response({"ok": True, "channels": list_channels()})
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)}, status_code=500)

    def _handle_youtube_oauth_diagnostics(self) -> None:
        """GET /api/youtube/oauth-diagnostics — safe checks for hosted OAuth setup."""
        origin = self.headers.get("Origin", "")
        host = self.headers.get("Host", "")
        scheme = "https" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else "http"
        if host and not origin:
            origin = f"{scheme}://{host}"

        env_client_id = os.getenv("YOUTUBE_WEB_CLIENT_ID", "")
        env_client_id_set = bool(env_client_id)
        env_client_id_masked = ""
        if env_client_id_set:
            env_client_id_masked = f"{env_client_id[:12]}...{env_client_id[-18:]}"

        client_secrets_path = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")
        client_secrets_exists = os.path.exists(client_secrets_path)

        diagnostics = {
            "ok": True,
            "origin": origin,
            "host": host,
            "web_client_id": {
                "present": env_client_id_set,
                "masked": env_client_id_masked,
            },
            "web_client_secret": {
                "present": bool(os.getenv("YOUTUBE_WEB_CLIENT_SECRET", "").strip()),
            },
            "desktop_client_secrets": {
                "path": client_secrets_path,
                "exists": client_secrets_exists,
            },
            "required_google_console": {
                "authorized_javascript_origins": [origin] if origin else [],
                "oauth_client_type": "Web application",
                "scope": "https://www.googleapis.com/auth/youtube.force-ssl",
            },
            "channels": [],
        }

        try:
            from youtube_uploader import list_channels

            channels = list_channels()
            for ch in channels:
                diagnostics["channels"].append({
                    "slug": ch.get("slug"),
                    "name": ch.get("name"),
                    "is_default": bool(ch.get("is_default")),
                    "has_token": bool(ch.get("has_token")),
                })
        except Exception as exc:
            diagnostics["channels_error"] = str(exc)

        tips = []
        if not env_client_id_set:
            tips.append("Set YOUTUBE_WEB_CLIENT_ID in hosted environment variables.")
        if not os.getenv("YOUTUBE_WEB_CLIENT_SECRET", "").strip():
            tips.append("Set YOUTUBE_WEB_CLIENT_SECRET in hosted environment variables.")
        if origin:
            tips.append(f"Add {origin} to Authorized JavaScript origins in Google Cloud OAuth Web client.")
            tips.append(f"Add {origin}/api/channels/oauth/callback to Authorized redirect URIs in Google Cloud OAuth Web client.")
        if not client_secrets_exists:
            tips.append("Upload client_secrets.json to hosted volume and set YOUTUBE_CLIENT_SECRETS path.")
        if not any(c.get("has_token") for c in diagnostics["channels"]):
            tips.append("No server upload token found; add channel once via backend OAuth flow.")

        diagnostics["tips"] = tips
        self._json_response(diagnostics)

    def _handle_channels_export_tokens(self) -> None:
        """GET /api/channels/export-tokens — Export all tokens as base64 env var values.

        Returns a dict of env var names → base64 values ready to paste into Render.
        """
        if not self._is_request_allowed(require_localhost=False): return
        import base64
        from youtube_uploader import _TOKENS_DIR, _CHANNELS_FILE
        result: dict = {}
        try:
            if os.path.exists(_CHANNELS_FILE):
                with open(_CHANNELS_FILE, "rb") as f:
                    result["YOUTUBE_CHANNELS_REGISTRY"] = base64.b64encode(f.read()).decode()
            files = [fn for fn in os.listdir(_TOKENS_DIR) if fn.endswith(".json") and fn != "channels.json"] if os.path.isdir(_TOKENS_DIR) else []
            for fn in files:
                slug = fn[:-5].upper().replace("-", "_")
                with open(os.path.join(_TOKENS_DIR, fn), "rb") as f:
                    result[f"YOUTUBE_TOKEN_{slug}"] = base64.b64encode(f.read()).decode()
            self._json_response({"ok": True, "env_vars": result})
        except Exception as exc:
            self._json_response({"ok": False, "error": str(exc)})

    def _handle_channels_import_tokens(self) -> None:
        """POST /api/channels/import-tokens — Write token files from base64 payload.

        Body: {"channels_b64": "...", "tokens": {"slug": "base64_content", ...}}
        """
        if not self._is_request_allowed(require_localhost=False): return
        import base64
        from youtube_uploader import _TOKENS_DIR, _CHANNELS_FILE, _ensure_tokens_dir
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            _ensure_tokens_dir()
            written = []
            channels_b64 = data.get("channels_b64", "").strip()
            if channels_b64:
                with open(_CHANNELS_FILE, "wb") as f:
                    f.write(base64.b64decode(channels_b64))
                written.append("channels.json")
            for slug, token_b64 in (data.get("tokens") or {}).items():
                token_path = os.path.join(_TOKENS_DIR, f"{slug}.json")
                with open(token_path, "wb") as f:
                    f.write(base64.b64decode(token_b64.strip()))
                written.append(f"{slug}.json")
            self._json_response({"ok": True, "written": written})
        except Exception as exc:
            self._json_response({"ok": False, "error": str(exc)})

    def _handle_channel_add(self) -> None:
        """POST /api/channels/add — Run OAuth flow to add a YouTube channel."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            name = data.get("name", "").strip()
            if not name:
                self._json_response({"ok": False, "error": "name required"}); return

            origin = self.headers.get("Origin", "").strip().lower()
            host = self.headers.get("Host", "").strip().lower()
            is_railway = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))
            is_local_host_header = (
                host.startswith("localhost")
                or host.startswith("127.0.0.1")
                or host.startswith("[::1]")
            )
            is_local_origin = (
                (not origin)
                or origin.startswith("http://localhost")
                or origin.startswith("http://127.0.0.1")
            )
            use_local_browser_flow = (not is_railway) and is_local_host_header and is_local_origin

            # Localhost can keep using installed-app flow.
            if use_local_browser_flow:
                from youtube_uploader import add_channel
                slug, channel_id = add_channel(name)
                self._json_response({"ok": True, "slug": slug, "channel_id": channel_id})
                return

            # Hosted flow: return an OAuth URL to open in browser popup.
            from config import YOUTUBE_CLIENT_SECRETS, YOUTUBE_SCOPES
            from google_auth_oauthlib.flow import Flow

            scheme = "https" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else "http"
            if not origin and host:
                origin = f"{scheme}://{host}"
            if not origin:
                self._json_response({"ok": False, "error": "Cannot resolve dashboard origin for OAuth callback."})
                return

            redirect_uri = f"{origin}/api/channels/oauth/callback"

            web_client_id = os.getenv("YOUTUBE_WEB_CLIENT_ID", "").strip()
            web_client_secret = os.getenv("YOUTUBE_WEB_CLIENT_SECRET", "").strip()
            flow = None

            if web_client_id and web_client_secret:
                web_cfg = {
                    "web": {
                        "client_id": web_client_id,
                        "client_secret": web_client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [redirect_uri],
                    }
                }
                flow = Flow.from_client_config(web_cfg, scopes=YOUTUBE_SCOPES)
            else:
                # Fallback: if client_secrets has a `web` block, use it.
                try:
                    cfg = json.loads(Path(YOUTUBE_CLIENT_SECRETS).read_text(encoding="utf-8"))
                    if "web" in cfg:
                        flow = Flow.from_client_config(cfg, scopes=YOUTUBE_SCOPES)
                except Exception:
                    pass

            if flow is None:
                self._json_response({
                    "ok": False,
                    "error": (
                        "Hosted OAuth is not configured for Web client. "
                        "Set YOUTUBE_WEB_CLIENT_ID and YOUTUBE_WEB_CLIENT_SECRET in Railway, "
                        f"and add redirect URI: {redirect_uri}"
                    ),
                })
                return

            flow.redirect_uri = redirect_uri
            auth_url, state = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            with _pending_channel_oauth_lock:
                _pending_channel_oauth[state] = {"flow": flow, "name": name}

            self._json_response({
                "ok": True,
                "requires_oauth": True,
                "oauth_url": auth_url,
                "message": "Open the OAuth popup and finish Google sign-in.",
            })
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_channel_oauth_callback(self) -> None:
        """GET /api/channels/oauth/callback — Complete hosted OAuth and save channel token."""
        if not self._is_request_allowed(require_localhost=False):
            self.send_response(403)
            self.end_headers()
            return

        qs = parse_qs(urlparse(self.path).query)
        state = (qs.get("state") or [""])[0]
        error = (qs.get("error") or [""])[0]

        if error:
            body = (
                "<html><body style='font-family:sans-serif;padding:20px'>"
                f"<h3>Google OAuth Error</h3><p>{error}</p>"
                "<script>if(window.opener){window.opener.postMessage({type:'yt_channel_added',ok:false,error:'oauth_error'},'*');}window.close();</script>"
                "</body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        with _pending_channel_oauth_lock:
            pending = _pending_channel_oauth.pop(state, None)

        if not pending:
            body = (
                "<html><body style='font-family:sans-serif;padding:20px'>"
                "<h3>OAuth session expired</h3><p>Please try adding the channel again.</p>"
                "</body></html>"
            ).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        flow = pending["flow"]
        channel_name = pending["name"]
        try:
            proto = self.headers.get("X-Forwarded-Proto", "https") or "https"
            host = self.headers.get("Host", "")
            full_url = f"{proto}://{host}{self.path}"
            flow.fetch_token(authorization_response=full_url)

            from youtube_uploader import add_channel_from_credentials
            slug, channel_id = add_channel_from_credentials(channel_name, flow.credentials)

            body = (
                "<html><body style='font-family:sans-serif;padding:20px'>"
                "<h3>Channel Connected</h3><p>You can close this window now.</p>"
                f"<script>if(window.opener){{window.opener.postMessage({{type:'yt_channel_added',ok:true,slug:{json.dumps(slug)},channel_id:{json.dumps(channel_id)}}},'*');}}window.close();</script>"
                "</body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = (
                "<html><body style='font-family:sans-serif;padding:20px'>"
                f"<h3>Channel Connect Failed</h3><p>{str(exc)}</p>"
                "<script>if(window.opener){window.opener.postMessage({type:'yt_channel_added',ok:false,error:'callback_failed'},'*');}</script>"
                "</body></html>"
            ).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _handle_channel_set_default(self) -> None:
        """POST /api/channels/default — Set a channel as default."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            slug = data.get("slug", "").strip()
            if not slug:
                self._json_response({"ok": False, "error": "slug required"}); return
            from youtube_uploader import set_default_channel
            ok = set_default_channel(slug)
            self._json_response({"ok": ok, "error": None if ok else "Channel not found"})
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_channel_remove(self, path: str) -> None:
        """DELETE /api/channels/<slug> — Remove a channel."""
        if not self._is_request_allowed(require_localhost=False): return
        slug = path.replace("/api/channels/", "").strip("/")
        if not slug:
            self._json_response({"ok": False, "error": "slug required"}); return
        from youtube_uploader import remove_channel
        ok = remove_channel(slug)
        self._json_response({"ok": ok, "error": None if ok else "Channel not found"})

    def _handle_channel_voice_get(self, path: str) -> None:
        """GET /api/channels/<slug>/voice — Get channel's voice setting."""
        if not self._is_request_allowed(require_localhost=False):
            self._json_response({"ok": False, "error": "Not allowed"}, status_code=403); return
        try:
            slug = path.replace("/api/channels/", "").replace("/voice", "").strip("/")
            if not slug:
                self._json_response({"ok": False, "error": "slug required"}); return
            from voice_config import get_channel_voice
            voice_id = get_channel_voice(slug)
            self._json_response({"ok": True, "voice_id": voice_id})
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_channel_voice_post(self, path: str) -> None:
        """POST /api/channels/<slug>/voice — Set channel's voice."""
        if not self._is_request_allowed(require_localhost=False):
            self._json_response({"ok": False, "error": "Not allowed"}, status_code=403); return
        try:
            slug = path.replace("/api/channels/", "").replace("/voice", "").strip("/")
            if not slug:
                self._json_response({"ok": False, "error": "slug required"}); return
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            voice_id = data.get("voice_id", "").strip()
            if not voice_id:
                self._json_response({"ok": False, "error": "voice_id required"}); return
            from voice_config import set_channel_voice
            ok = set_channel_voice(slug, voice_id)
            self._json_response({
                "ok": ok,
                "voice_id": voice_id if ok else None,
                "error": None if ok else "Failed to set voice"
            })
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    # ── Voice endpoints ───────────────────────────────────────────────────────

    def _handle_voices_samples(self) -> None:
        """GET /api/voices/samples — List available voice samples organized by language."""
        if not self._is_request_allowed(require_localhost=False):
            self._json_response({"ok": False, "error": "Not allowed"}, status_code=403); return
        
        from pathlib import Path
        voice_samples_dir = Path(__file__).parent / "scripts" / "voice_samples"
        
        # Organize voice samples by language
        voices_by_lang = {}
        
        if voice_samples_dir.exists():
            for mp3_file in sorted(voice_samples_dir.glob("*.mp3")):
                filename = mp3_file.name
                # Parse filename: lang_voiceid_name.mp3
                parts = filename.replace(".mp3", "").split("_", 2)
                if len(parts) >= 3:
                    lang, voice_id = parts[0], parts[1]
                    voice_name = parts[2].replace("_", " ")
                    
                    if lang not in voices_by_lang:
                        voices_by_lang[lang] = []
                    
                    voices_by_lang[lang].append({
                        "voice_id": voice_id,
                        "name": voice_name,
                        "url": f"/scripts/voice_samples/{filename}",
                        "file": filename,
                    })
        
        self._json_response({
            "ok": True,
            "voices": voices_by_lang,
            "total": sum(len(v) for v in voices_by_lang.values()),
        })

    # ── Social platform endpoints ─────────────────────────────────────────────

    def _handle_social_platforms_get(self) -> None:
        """GET /api/social/platforms — List configured social platforms."""
        if not self._is_request_allowed(require_localhost=False): return
        from social_uploader import list_platforms
        self._json_response(list_platforms())

    # ── Branding endpoints ─────────────────────────────────────────────────

    def _handle_branding_assets_get(self) -> None:
        """GET /api/branding/assets — List existing branding files."""
        if not self._is_request_allowed(require_localhost=False): return
        from branding_manager import list_assets
        self._json_response({"ok": True, "assets": list_assets()})

    def _handle_branding_generate(self) -> None:
        """POST /api/branding/generate — Generate banner, avatar, watermark."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            channel_name = data.get("channelName", "TRUTH THAT NEVER SHARED")
            tagline = data.get("tagline", "Geopolitics  •  Hidden History  •  Global Crisis Analysis")
            from branding_manager import generate_assets
            paths = generate_assets(channel_name=channel_name, tagline=tagline)
            from branding_manager import list_assets
            self._json_response({"ok": True, "assets": list_assets()})
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_branding_upload_banner(self) -> None:
        """POST /api/branding/upload-banner — Upload banner to YouTube."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            channel_slug = data.get("channel") or None
            from branding_manager import upload_banner_to_youtube
            result = upload_banner_to_youtube(channel_slug)
            self._json_response(result)
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_branding_set_trailer(self) -> None:
        """POST /api/branding/set-trailer — Set channel trailer video."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            video_id = data.get("videoId", "").strip()
            channel_slug = data.get("channel") or None
            from branding_manager import set_channel_trailer
            result = set_channel_trailer(video_id, channel_slug)
            self._json_response(result)
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    # ── Channel Health endpoints ───────────────────────────────────────────

    def _handle_channel_audit(self) -> None:
        """GET /api/channel/audit — Full channel SEO audit."""
        if not self._is_request_allowed(require_localhost=False): return
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        slug = (qs.get("slug") or [None])[0] or None
        try:
            from channel_manager import audit_channel
            result = audit_channel(slug)
            self._json_response(result)
        except Exception as e:
            err = str(e)
            if err.startswith("TOKEN_REVOKED:"):
                channel_name = err.split("TOKEN_REVOKED:", 1)[1]
                self._json_response({
                    "ok": False,
                    "error": f"YouTube token for '{channel_name}' has been revoked or expired by Google.",
                    "error_code": "token_revoked",
                    "channel": channel_name,
                })
            else:
                self._json_response({"ok": False, "error": err})

    def _handle_channel_update(self) -> None:
        """POST /api/channel/update — Update channel description/keywords/etc."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            from channel_manager import update_channel_info
            result = update_channel_info(
                description=data.get("description"),
                keywords=data.get("keywords"),
                country=data.get("country"),
                language=data.get("language"),
                trailer_video_id=data.get("trailerVideoId"),
                channel_slug=data.get("channel"),
            )
            self._json_response(result)
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_channel_fix_video(self) -> None:
        """POST /api/channel/fix-video — Fix a single video's SEO."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            video_id = data.get("videoId", "").strip()
            if not video_id:
                self._json_response({"ok": False, "error": "videoId required"})
                return
            from channel_manager import fix_video
            result = fix_video(video_id, data.get("channel"))
            self._json_response(result)
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_channel_fix_all(self) -> None:
        """POST /api/channel/fix-all — Fix all videos with issues."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            from channel_manager import fix_all_videos
            result = fix_all_videos(data.get("channel") or None)
            self._json_response(result)
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    # ── Upload Studio endpoints ─────────────────────────────────────────

    def _handle_studio_videos_get(self) -> None:
        """GET /api/studio/videos — List video files in output/."""
        if not self._is_request_allowed(require_localhost=False): return
        from media_hub import list_videos
        self._json_response(list_videos())

    def _handle_studio_video_info(self, path: str) -> None:
        """GET /api/studio/info/<encoded_path> — Probe video metadata."""
        if not self._is_request_allowed(require_localhost=False): return
        import urllib.parse
        video_path = urllib.parse.unquote(path.replace("/api/studio/info/", "", 1))
        from media_hub import video_info
        self._json_response(video_info(video_path))

    def _handle_studio_extract_clips(self) -> None:
        """POST /api/studio/extract-clips — Extract time-range clips from a video."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            video_path = data.get("video_path", "")
            clips = data.get("clips", [])
            if not video_path or not clips:
                self._json_response({"ok": False, "error": "video_path and clips[] required"})
                return
            from media_hub import extract_clips
            self._json_response(extract_clips(video_path, clips))
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_studio_upload_main(self) -> None:
        """POST /api/studio/upload-main — Upload existing video to YouTube."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            video_path = data.get("video_path", "")
            content = {
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "tags": data.get("tags", []),
            }
            channel = data.get("channel") or None
            if not video_path or not content["title"]:
                self._json_response({"ok": False, "error": "video_path and title required"})
                return
            from media_hub import upload_main_video
            self._json_response(upload_main_video(video_path, content, channel))
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_studio_upload_clips(self) -> None:
        """POST /api/studio/upload-clips — Upload clips to YouTube Shorts + social."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            raw_paths = data.get("clip_paths", [])
            clip_paths = [p for p in raw_paths if isinstance(p, str) and p.strip()]
            content = {
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "tags": data.get("tags", []),
            }
            if not clip_paths:
                self._json_response({"ok": False, "error": "clip_paths[] required"})
                return
            from media_hub import upload_clips_to_platforms
            self._json_response(upload_clips_to_platforms(
                clip_paths, content,
                channel_slug=data.get("channel"),
                youtube_shorts=data.get("youtube_shorts", True),
                social_platforms=data.get("social_platforms", True),
                include_stories=data.get("include_stories", False),
            ))
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_community_post_generate(self) -> None:
        """POST /api/community-post/generate — AI-generate a community post draft."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            title = data.get("title", "")
            desc = data.get("description", "")
            tags = data.get("tags", [])
            api_key = data.get("api_key", "")
            if not title:
                self._json_response({"ok": False, "error": "title required"})
                return
            from community_post import generate_post
            self._json_response(generate_post(title, desc, tags, api_key or None))
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_studio_delete(self) -> None:
        """DELETE or POST /api/studio/delete — Delete a local video file from output/."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            video_path = (data.get("video_path") or "").strip()
            if not video_path:
                self._json_response({"ok": False, "error": "video_path required"}); return
            from media_hub import delete_video
            self._json_response(delete_video(video_path))
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_studio_download_get(self, path: str) -> None:
        """GET /api/studio/download/<encoded_filename> — Stream a video file for download."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            import shutil
            import urllib.parse
            from config import OUTPUT_DIR
            
            filename = urllib.parse.unquote(path.replace("/api/studio/download/", "", 1))
            video_path = Path(OUTPUT_DIR) / filename
            
            # Path traversal protection
            if not str(video_path.resolve()).startswith(str(Path(OUTPUT_DIR).resolve())):
                self.send_response(403)
                self.end_headers()
                return
            
            if not video_path.exists():
                self._json_response({"ok": False, "error": "File not found"})
                return
            
            # Stream file
            self.send_response(200)
            file_size = video_path.stat().st_size
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Content-Disposition", f"attachment; filename={filename}")
            self.end_headers()
            
            with open(video_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        except Exception as e:
            try:
                self._json_response({"ok": False, "error": str(e)})
            except:
                pass

    def _handle_social_config_post(self) -> None:
        """POST /api/social/config — Save platform credentials.
        Body: {platform, access_token, user_id/page_id, enabled, ...}"""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            platform = data.pop("platform", "").lower().strip()
            if platform not in ("instagram", "facebook", "tiktok"):
                self._json_response({"ok": False, "error": "Invalid platform"})
                return
            from social_uploader import save_platform_config
            save_platform_config(platform, data)
            self._json_response({"ok": True})
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_social_platform_remove(self, path: str) -> None:
        """DELETE /api/social/platforms/<name> — Remove a social platform config."""
        if not self._is_request_allowed(require_localhost=False): return
        platform = path.replace("/api/social/platforms/", "").strip("/")
        from social_uploader import remove_platform
        ok = remove_platform(platform)
        self._json_response({"ok": ok, "error": None if ok else "Platform not found"})

    def _handle_social_upload(self) -> None:
        """POST /api/social/upload — Upload Shorts to selected social platforms.
        Body: {platforms: ["instagram", "facebook", "tiktok"]}
        Uses the Shorts from the current pipeline job."""
        if not self._is_request_allowed(require_localhost=False): return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            target_platforms = data.get("platforms", [])
            if not target_platforms:
                self._json_response({"ok": False, "error": "No platforms selected"})
                return
        except Exception:
            self._json_response({"ok": False, "error": "Invalid request body"})
            return

        with _pipeline_lock:
            shorts_paths = _pipeline_job.get("_shorts_paths", [])
            content = _pipeline_job.get("_content")
            job_status = _pipeline_job["status"]

        if job_status not in ("ready", "done"):
            self._json_response({"ok": False, "error": f"No video ready (status: {job_status})"})
            return
        if not shorts_paths:
            self._json_response({"ok": False, "error": "No Shorts available to upload"})
            return

        from social_uploader import upload_to_platforms
        title = content.get("title", "") if content else ""
        description = content.get("description", "") if content else ""

        all_results = {}
        for sp in shorts_paths:
            if not os.path.isfile(sp):
                continue
            results = upload_to_platforms(
                sp, title=title, description=description,
                platforms_list=target_platforms,
            )
            for platform, result in results.items():
                if platform not in all_results:
                    all_results[platform] = result
                elif not result["ok"]:
                    all_results[platform] = result  # keep error

        self._json_response({"ok": True, "results": all_results})

    def _handle_env(self) -> dict:
        # Runtime environment first (Railway/hosted), then .env fallback.
        merged: dict = {}
        file_env = _read_env(_ENV_PATH)
        for key in _EXPOSED_KEYS:
            val = os.getenv(key)
            if val is None or val == "":
                val = file_env.get(key)
            if val not in (None, ""):
                merged[key] = val

        # DB-backed settings can fill gaps when env variables are not present.
        # This keeps dashboard fields consistent after "Save all settings".
        db_settings = _db_settings() if _DB_AVAILABLE else {}
        cfg = db_settings.get("config", {}) if isinstance(db_settings, dict) else {}
        if isinstance(cfg, dict):
            map_from_cfg = {
                "anthropic": "ANTHROPIC_API_KEY",
                "elevenlabs": "ELEVENLABS_API_KEY",
                "pexels": "PEXELS_API_KEY",
                "voiceId": "ELEVENLABS_VOICE_ID",
                "voiceStab": "VOICE_STABILITY",
                "voiceSim": "VOICE_SIMILARITY",
                "voiceStyle": "VOICE_STYLE",
                "ytVis": "DEFAULT_VISIBILITY",
                "ytCategory": "YOUTUBE_CATEGORY_ID",
                "ytClientId": "YOUTUBE_WEB_CLIENT_ID",
                "ytSecretsPath": "YOUTUBE_CLIENT_SECRETS",
                "freq": "VIDEOS_PER_WEEK",
                "ttsProvider": "TTS_PROVIDER",
                "edgeVoice": "EDGE_TTS_VOICE",
            }
            for cfg_key, env_key in map_from_cfg.items():
                if env_key not in merged:
                    value = cfg.get(cfg_key)
                    if value not in (None, ""):
                        merged[env_key] = str(value)

        return merged

    def _handle_debug_paths(self) -> dict:
        """GET /api/debug/paths — dump runtime path config and disk state."""
        import shutil
        from config import DB_PATH, AUDIO_DIR, IMAGES_DIR, OUTPUT_DIR
        dirs_to_check = {
            "/data": "/data",
            "/tmp": "/tmp",
            "db": DB_PATH,
            "audio": AUDIO_DIR,
            "images": IMAGES_DIR,
            "output": OUTPUT_DIR,
            "runs": os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs"),
        }
        result = {}
        for label, p in dirs_to_check.items():
            entry = {"path": p, "exists": os.path.exists(p)}
            if os.path.exists(p):
                try:
                    entry["writable"] = os.access(p, os.W_OK)
                    if os.path.isdir(p):
                        total, used, free = shutil.disk_usage(p)
                        entry["disk_free_mb"] = round(free / 1024 / 1024, 1)
                        entry["files"] = len(os.listdir(p))
                except Exception as e:
                    entry["error"] = str(e)
            result[label] = entry
        env_keys = ["DB_PATH", "AUDIO_DIR", "IMAGES_DIR", "OUTPUT_DIR", "RENDER", "RENDER_SERVICE_ID"]
        result["env"] = {k: os.getenv(k, "") for k in env_keys}
        return result

    def _is_allowed_static_path(self, path: str) -> bool:
        if not path or not path.startswith("/"):
            return False
        if path.endswith("/"):
            return False
        if any(path.startswith(prefix) for prefix in _BLOCKED_STATIC_PREFIXES):
            return False
        lowered = path.lower()
        if any(lowered.endswith(ext) for ext in _BLOCKED_STATIC_EXTENSIONS):
            return False
        if path in _PUBLIC_STATIC_FILES:
            return True
        return any(path.startswith(prefix) for prefix in _PUBLIC_STATIC_PREFIXES)

    def list_directory(self, path):
        self.send_response(403)
        self.end_headers()
        return None

    def _json_response(self, data, status_code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "http://localhost:8080")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        path = args[0] if args else ""
        if any(ext in str(path) for ext in (".css", ".js", ".png", ".ico", ".woff")):
            return
        super().log_message(fmt, *args)


def main() -> None:
    port = int(os.environ.get("PORT", 8080))
    use_threaded = os.environ.get("SERVER_THREADED", "1") == "1"
    server_cls = ThreadingHTTPServer if use_threaded else HTTPServer
    server = server_cls(("", port), DashboardHandler)
    db_status = "✓ SQLite connected" if _DB_AVAILABLE else "✗ SQLite unavailable"
    print(f"╔══════════════════════════════════════════════════════════╗")
    print(f"║  YouTube Automation Dashboard  →  http://localhost:{port}  ║")
    print(f"║  {db_status:<54}║")
    print(f"╚══════════════════════════════════════════════════════════╝")
    print(f"  /api/env          →  .env values (Settings auto-fill)")
    print(f"  /api/db/stats     →  channel stats")
    print(f"  /api/db/costs     →  monthly API costs")
    print(f"  /api/db/videos    →  video history")
    print(f"  /api/db/ypp       →  YPP progress")
    print(f"  /api/db/queue     →  topic queue")
    print(f"  /api/channels     →  YouTube channel management\n")
    mode = "threaded" if use_threaded else "single-thread"
    print(f"  Server mode       →  {mode}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()

