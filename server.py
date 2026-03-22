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

import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path

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
            "SELECT id, topic, type, scheduled, status, added_at "
            "FROM topic_queue ORDER BY id DESC LIMIT 100"
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
    "PEXELS_API_KEY", "CHANNEL_NICHE", "CHANNEL_LANGUAGE",
    "CHANNEL_AUDIENCE", "VIDEOS_PER_WEEK", "DEFAULT_VISIBILITY",
    "YOUTUBE_CATEGORY_ID", "VOICE_STABILITY", "VOICE_SIMILARITY",
    "VOICE_STYLE", "YOUTUBE_CLIENT_SECRETS", "YOUTUBE_WEB_CLIENT_ID",
    "VISUAL_MODE", "GTTS_SPEECH_RATE",
}

_ENV_PATH = str(Path(__file__).parent / ".env")
_LOCALHOST = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}

_DB_ROUTES = {
    "/api/db/stats":  _db_stats,
    "/api/db/costs":  _db_costs,
    "/api/db/videos": _db_videos,
    "/api/db/ypp":    _db_ypp,
    "/api/db/queue":  _db_queue,
    "/api/settings":  _db_settings,
}

# ── Pipeline preview state ─────────────────────────────────────────────────────
_pipeline_job: dict = {
    "status":        "idle",   # idle | running | ready | uploading | done | failed
    "topic":         None,
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
}
_pipeline_lock = threading.Lock()


def _run_pipeline_bg(topic: str, script_text=None, seo=None, thumb_data_url=None) -> None:
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
        )
        slug = video_path.replace("\\", "/").split("/")[-1]  # just the filename
        with _pipeline_lock:
            _pipeline_job.update({
                "status":        "ready",
                "message":       "✓ Video ready for review!",
                "video_url":     f"/output/{slug}",
                "thumbnail_url": "/thumbnail.jpg",
                "title":         content.get("title", topic),
                "vid_db_id":     vid_id,
                "_content":      content,
                "_video_path":   video_path,
                "_thumb_path":   thumb_path,
            })
    except Exception as exc:
        with _pipeline_lock:
            _pipeline_job.update({
                "status":  "failed",
                "message": str(exc),
                "error":   str(exc),
            })


class DashboardHandler(SimpleHTTPRequestHandler):

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/env":
            self._json_response(self._handle_env())
        elif path == "/api/pipeline/status":
            with _pipeline_lock:
                safe = {k: v for k, v in _pipeline_job.items() if not k.startswith("_")}
            self._json_response(safe)
        elif path in _DB_ROUTES:
            self._json_response(_DB_ROUTES[path]())
        else:
            super().do_GET()

    def do_POST(self) -> None:
        path = self.path.split("?")[0]

        if path == "/api/pipeline/run":
            self._handle_pipeline_run()
        elif path == "/api/pipeline/upload":
            self._handle_pipeline_upload()
        elif path == "/api/pipeline/cancel":
            with _pipeline_lock:
                _pipeline_job.update({
                    "status": "idle", "topic": None, "message": "",
                    "video_url": None, "thumbnail_url": None, "title": None,
                    "vid_db_id": None, "youtube_url": None, "error": None,
                    "_content": None, "_video_path": None, "_thumb_path": None,
                })
            self._json_response({"ok": True})
        elif path == "/api/settings":
            self._handle_settings_post()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_pipeline_run(self) -> None:
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            topic = data.get("topic", "").strip()
            if not topic:
                self._json_response({"ok": False, "error": "topic required"}); return
            with _pipeline_lock:
                if _pipeline_job["status"] == "running":
                    self._json_response({"ok": False, "error": "Pipeline already running"}); return
                _pipeline_job.update({
                    "status": "running", "topic": topic, "message": "Starting…",
                    "video_url": None, "thumbnail_url": None, "title": None,
                    "vid_db_id": None, "youtube_url": None, "error": None,
                    "_content": None, "_video_path": None, "_thumb_path": None,
                })
            # Optional pre-computed assets from dashboard
            script_text    = data.get("scriptText", "").strip() or None
            seo_title      = data.get("seoTitle", "").strip() or None
            seo_description= data.get("seoDescription", "").strip() or None
            seo_tags_raw   = data.get("seoTags", "").strip() or None
            thumb_data_url = data.get("thumbDataUrl", "").strip() or None
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
                kwargs={"script_text": script_text, "seo": seo, "thumb_data_url": thumb_data_url},
                daemon=True,
            )
            t.start()
            self._json_response({"ok": True})
        except Exception as ex:
            self._json_response({"ok": False, "error": str(ex)})

    def _handle_pipeline_upload(self) -> None:
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        if not _DB_AVAILABLE:
            self._json_response({"ok": False, "error": "DB not available"}); return
        with _pipeline_lock:
            job_status = _pipeline_job["status"]
            video_path = _pipeline_job["_video_path"]
            thumb_path = _pipeline_job["_thumb_path"]
            content    = _pipeline_job["_content"]
            vid_db_id  = _pipeline_job["vid_db_id"]
        if job_status != "ready":
            self._json_response({"ok": False, "error": f"No video ready (status: {job_status})"}); return
        with _pipeline_lock:
            _pipeline_job["status"] = "uploading"
            _pipeline_job["message"] = "Uploading to YouTube…"
        try:
            from youtube_uploader import upload_video as _upload
            from database import log_video_complete
            from pipeline import run as _run  # noqa — just to ensure imports don't break
            youtube_id = _upload(video_path, thumb_path, content)
            segments = content.get("segments", [])
            duration_s = sum(seg.get("duration_s", 45) for seg in segments)
            log_video_complete(vid_db_id, content.get("title", ""), youtube_id, duration_s)
            yt_url = f"https://youtube.com/watch?v={youtube_id}"
            with _pipeline_lock:
                _pipeline_job.update({
                    "status":      "done",
                    "message":     f"✓ Uploaded! {yt_url}",
                    "youtube_url": yt_url,
                })
            self._json_response({"ok": True, "youtube_url": yt_url})
        except Exception as exc:
            with _pipeline_lock:
                _pipeline_job.update({"status": "failed", "message": str(exc), "error": str(exc)})
            self._json_response({"ok": False, "error": str(exc)})

    def _handle_settings_post(self) -> None:
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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

    def _handle_env(self) -> dict:
        env = _read_env(_ENV_PATH)
        return {k: v for k, v in env.items() if k in _EXPOSED_KEYS}

    def _json_response(self, data) -> None:
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403)
            self.end_headers()
            return
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(200)
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
    server = HTTPServer(("", port), DashboardHandler)
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
    print(f"  /api/db/queue     →  topic queue\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()

