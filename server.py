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
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
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
    "_shorts_paths": [],
}
_pipeline_lock = threading.Lock()


def _run_pipeline_bg(topic: str, script_text=None, seo=None, thumb_data_url=None, guidance=None, shorts_count=0) -> None:
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
            guidance=guidance, shorts_count=shorts_count,
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

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/env":
            self._json_response(self._handle_env())
        elif path == "/api/pipeline/status":
            with _pipeline_lock:
                safe = {k: v for k, v in _pipeline_job.items() if not k.startswith("_")}
            self._json_response(safe)
        elif path == "/api/pipeline/lock-status":
            from pipeline import pipeline_status
            self._json_response(pipeline_status())
        elif path == "/api/channels":
            self._handle_channels_get()
        elif path == "/api/social/platforms":
            self._handle_social_platforms_get()
        elif path == "/api/branding/assets":
            self._handle_branding_assets_get()
        elif path == "/api/channel/audit":
            self._handle_channel_audit()
        elif path == "/api/studio/videos":
            self._handle_studio_videos_get()
        elif path.startswith("/api/studio/info/"):
            self._handle_studio_video_info(path)
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
                    "_content": None, "_video_path": None, "_thumb_path": None, "_shorts_paths": [],
                })
            self._json_response({"ok": True})
        elif path == "/api/pipeline/kill":
            self._handle_pipeline_kill()
        elif path == "/api/settings/sync-env":
            self._handle_settings_sync_env()
        elif path == "/api/settings":
            self._handle_settings_post()
        elif path == "/api/upload-music":
            self._handle_music_upload()
        elif path == "/api/channels/add":
            self._handle_channel_add()
        elif path == "/api/channels/default":
            self._handle_channel_set_default()
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
        elif path == "/api/community-post/generate":
            self._handle_community_post_generate()
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/upload-music":
            self._handle_music_delete()
        elif path.startswith("/api/channels/"):
            self._handle_channel_remove(path)
        elif path.startswith("/api/social/platforms/"):
            self._handle_social_platform_remove(path)
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
                    "_content": None, "_video_path": None, "_thumb_path": None, "_shorts_paths": [],
                })
            # Optional pre-computed assets from dashboard
            script_text    = data.get("scriptText", "").strip() or None
            seo_title      = data.get("seoTitle", "").strip() or None
            seo_description= data.get("seoDescription", "").strip() or None
            seo_tags_raw   = data.get("seoTags", "").strip() or None
            thumb_data_url = data.get("thumbDataUrl", "").strip() or None
            guidance       = data.get("guidance", "").strip() or None
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
                        "guidance": guidance, "shorts_count": shorts_count},
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

    def _handle_pipeline_kill(self) -> None:
        """POST /api/pipeline/kill — Kill a running pipeline process and clear lock."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        from pipeline import kill_pipeline
        result = kill_pipeline()
        # Also reset the in-memory pipeline state
        with _pipeline_lock:
            _pipeline_job.update({
                "status": "idle", "topic": None, "message": "",
                "video_url": None, "thumbnail_url": None, "title": None,
                "vid_db_id": None, "youtube_url": None, "error": None,
                "_content": None, "_video_path": None, "_thumb_path": None, "_shorts_paths": [],
            })
        self._json_response(result)

    def _handle_settings_sync_env(self) -> None:
        """POST /api/settings/sync-env — Write dashboard production settings to .env."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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

    def _handle_music_upload(self) -> None:
        """Accept a multipart/form-data .mp3 upload and save to music/bg_music.mp3."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        dest = Path(__file__).parent / "music" / "bg_music.mp3"
        if dest.exists():
            dest.unlink()
        _update_env_key("BG_MUSIC_PATH", "")
        self._json_response({"ok": True})

    # ── Channel management ─────────────────────────────────────────────────

    def _handle_channels_get(self) -> None:
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        from youtube_uploader import list_channels
        self._json_response({"ok": True, "channels": list_channels()})

    def _handle_channel_add(self) -> None:
        """POST /api/channels/add — Run OAuth flow to add a YouTube channel."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            name = data.get("name", "").strip()
            if not name:
                self._json_response({"ok": False, "error": "name required"}); return
            from youtube_uploader import add_channel
            slug, channel_id = add_channel(name)
            self._json_response({"ok": True, "slug": slug, "channel_id": channel_id})
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_channel_set_default(self) -> None:
        """POST /api/channels/default — Set a channel as default."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        slug = path.replace("/api/channels/", "").strip("/")
        if not slug:
            self._json_response({"ok": False, "error": "slug required"}); return
        from youtube_uploader import remove_channel
        ok = remove_channel(slug)
        self._json_response({"ok": ok, "error": None if ok else "Channel not found"})

    # ── Social platform endpoints ─────────────────────────────────────────────

    def _handle_social_platforms_get(self) -> None:
        """GET /api/social/platforms — List configured social platforms."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        from social_uploader import list_platforms
        self._json_response(list_platforms())

    # ── Branding endpoints ─────────────────────────────────────────────────

    def _handle_branding_assets_get(self) -> None:
        """GET /api/branding/assets — List existing branding files."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        from branding_manager import list_assets
        self._json_response({"ok": True, "assets": list_assets()})

    def _handle_branding_generate(self) -> None:
        """POST /api/branding/generate — Generate banner, avatar, watermark."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        try:
            from channel_manager import audit_channel
            result = audit_channel()
            self._json_response(result)
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_channel_update(self) -> None:
        """POST /api/channel/update — Update channel description/keywords/etc."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        try:
            from channel_manager import fix_all_videos
            result = fix_all_videos()
            self._json_response(result)
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    # ── Upload Studio endpoints ─────────────────────────────────────────

    def _handle_studio_videos_get(self) -> None:
        """GET /api/studio/videos — List video files in output/."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        from media_hub import list_videos
        self._json_response(list_videos())

    def _handle_studio_video_info(self, path: str) -> None:
        """GET /api/studio/info/<encoded_path> — Probe video metadata."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        import urllib.parse
        video_path = urllib.parse.unquote(path.replace("/api/studio/info/", "", 1))
        from media_hub import video_info
        self._json_response(video_info(video_path))

    def _handle_studio_extract_clips(self) -> None:
        """POST /api/studio/extract-clips — Extract time-range clips from a video."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            clip_paths = data.get("clip_paths", [])
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
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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

    def _handle_social_config_post(self) -> None:
        """POST /api/social/config — Save platform credentials.
        Body: {platform, access_token, user_id/page_id, enabled, ...}"""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
        platform = path.replace("/api/social/platforms/", "").strip("/")
        from social_uploader import remove_platform
        ok = remove_platform(platform)
        self._json_response({"ok": ok, "error": None if ok else "Platform not found"})

    def _handle_social_upload(self) -> None:
        """POST /api/social/upload — Upload Shorts to selected social platforms.
        Body: {platforms: ["instagram", "facebook", "tiktok"]}
        Uses the Shorts from the current pipeline job."""
        if self.client_address[0] not in _LOCALHOST:
            self.send_response(403); self.end_headers(); return
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
    server = ThreadingHTTPServer(("", port), DashboardHandler)
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
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()

