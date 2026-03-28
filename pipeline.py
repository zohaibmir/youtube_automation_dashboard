"""pipeline.py — Full video production pipeline orchestrator.

Single responsibility: coordinate the end-to-end pipeline by calling
the individual specialist modules in the correct order. Nothing else.
All business logic lives in the modules it calls.
"""

import glob
import logging
import os
import signal
import shutil

from audio_generator import generate_audio_segments
from config import BG_MUSIC_PATH, CHANNEL_LANGUAGE, CHANNEL_NICHE, VISUAL_MODE

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_THUMB_OUT = os.path.join(_BASE_DIR, "thumbnail.jpg")
_IMAGES_DIR = os.path.join(_BASE_DIR, "images")
_AUDIO_DIR = os.path.join(_BASE_DIR, "audio")
_LOCK_FILE = os.path.join(_BASE_DIR, ".pipeline.lock")
from content_generator import generate_script, script_text_to_segments
from database import log_cost, log_video_complete, log_video_error, log_video_start, get_video_record, is_video_uploaded
from shorts_builder import build_shorts
from thumbnail import make_thumbnail
from video_builder import build_video
from visual_fetcher import fetch_segment_images, fetch_segment_videos
from youtube_uploader import upload_video

logger = logging.getLogger(__name__)


# ── Pipeline process guard ────────────────────────────────────────────────────

def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _acquire_lock() -> None:
    """Write current PID to lock file. Raises if another pipeline is running."""
    if os.path.exists(_LOCK_FILE):
        try:
            with open(_LOCK_FILE) as f:
                old_pid = int(f.read().strip())
            if _is_pid_alive(old_pid) and old_pid != os.getpid():
                raise RuntimeError(
                    f"Another pipeline is already running (PID {old_pid}). "
                    f"Kill it first or wait for it to finish."
                )
            # Stale lock — process is dead, we can take over
            logger.info("Removing stale lock from PID %d", old_pid)
        except (ValueError, FileNotFoundError):
            pass  # Corrupt lock file — remove it
    with open(_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def _release_lock() -> None:
    """Remove the lock file if it belongs to this process."""
    try:
        if os.path.exists(_LOCK_FILE):
            with open(_LOCK_FILE) as f:
                pid = int(f.read().strip())
            if pid == os.getpid():
                os.remove(_LOCK_FILE)
    except Exception:
        pass


def pipeline_status() -> dict:
    """Return the current pipeline lock status (for the dashboard)."""
    if not os.path.exists(_LOCK_FILE):
        return {"running": False, "pid": None}
    try:
        with open(_LOCK_FILE) as f:
            pid = int(f.read().strip())
        alive = _is_pid_alive(pid)
        return {"running": alive, "pid": pid if alive else None}
    except Exception:
        return {"running": False, "pid": None}


def kill_pipeline() -> dict:
    """Kill a running pipeline process (if any) and release the lock."""
    if not os.path.exists(_LOCK_FILE):
        return {"ok": True, "message": "No pipeline running"}
    try:
        with open(_LOCK_FILE) as f:
            pid = int(f.read().strip())
        if _is_pid_alive(pid):
            os.kill(pid, signal.SIGTERM)
            logger.info("Killed pipeline PID %d", pid)
            os.remove(_LOCK_FILE)
            return {"ok": True, "message": f"Killed pipeline (PID {pid})"}
        else:
            os.remove(_LOCK_FILE)
            return {"ok": True, "message": "Stale lock removed (process already dead)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _cleanup_temp_files() -> None:
    """Remove MoviePy TEMP_MPY_* scratch files left after video encoding."""
    base = os.path.dirname(os.path.abspath(__file__))
    for pattern in ("*TEMP_MPY*", "images/*_thumb.jpg"):
        for f in glob.glob(os.path.join(base, pattern)):
            try:
                os.remove(f)
                logger.debug("Cleaned up temp file: %s", f)
            except OSError:
                pass


def _cleanup_media_dirs() -> None:
    """Wipe images/ and audio/ directories before each pipeline run.

    This prevents stale files from a previous run from leaking into the
    current build (e.g. leftover segments that no longer match).
    """
    for d in (_IMAGES_DIR, _AUDIO_DIR):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            logger.debug("Cleaned media dir: %s", d)
        os.makedirs(d, exist_ok=True)


def _resolve_thumb_from_data_url(thumb_data_url: str, out_path: str) -> str | None:
    """Decode a base64 data URL thumbnail from the dashboard and save as JPEG."""
    try:
        import base64, re
        match = re.match(r"data:image/[^;]+;base64,(.*)", thumb_data_url, re.DOTALL)
        if not match:
            return None
        img_bytes = base64.b64decode(match.group(1))
        with open(out_path, "wb") as f:
            f.write(img_bytes)
        logger.info("Using dashboard thumbnail: %s", out_path)
        return out_path
    except Exception as e:
        logger.warning("Could not decode dashboard thumbnail: %s", e)
        return None


def run(topic: str, script_text: str | None = None, seo: dict | None = None,
        thumb_data_url: str | None = None, channel_slug: str | None = None,
        guidance: str | None = None, shorts_count: int = 0) -> str:
    """Execute the full pipeline for a given topic.

    Args:
        topic:          The video topic.
        script_text:    Pre-written script from the dashboard Script Writer tab.
                        If provided, skips AI script generation.
        seo:            Dict with 'title', 'description', 'tags' from the SEO tab.
                        If provided, overrides the generated SEO metadata.
        thumb_data_url: Base64 JPEG data URL from the dashboard Thumbnail tab.
                        If provided, skips thumbnail generation.
        channel_slug:   YouTube channel slug for multi-account upload.
        guidance:       Optional creator instructions for AI script generation.
        shorts_count:   Number of Shorts to generate (0–3). 0 = skip.

    Returns:
        The YouTube video ID on success.
    """
    _acquire_lock()
    logger.info("Pipeline starting: %s", topic)
    vid_id = log_video_start(topic, CHANNEL_NICHE, CHANNEL_LANGUAGE)
    _cleanup_media_dirs()

    try:
        # Step 1 — Script (use dashboard script if provided, else generate fresh)
        if script_text:
            logger.info("Using pre-written script from dashboard Script Writer")
            content = script_text_to_segments(script_text, topic, seo_override=seo)
            usage = content.pop("_usage", {})
            log_cost("anthropic", "script_convert",
                     units=usage.get("input_tokens", 500) + usage.get("output_tokens", 0),
                     cost_usd=usage.get("cost_usd", 0.001), video_id=vid_id)
        else:
            content = generate_script(topic, guidance=guidance)
            usage = content.pop("_usage", {})
            log_cost("anthropic", "script",
                     units=usage.get("input_tokens", 3000) + usage.get("output_tokens", 0),
                     cost_usd=usage.get("cost_usd", 0.07), video_id=vid_id)
            # Apply SEO overrides if provided from SEO tab
            if seo:
                if seo.get("title"):       content["title"]       = seo["title"]
                if seo.get("description"): content["description"] = seo["description"]
                if seo.get("tags"):        content["tags"]        = seo["tags"]

        segments = content["segments"]

        # Step 2 — Text-to-speech
        audio_files = generate_audio_segments(segments)
        log_cost("elevenlabs", "tts", units=len(segments) * 300, cost_usd=0.05, video_id=vid_id)

        # Step 3 — Stock visuals (images or video clips based on VISUAL_MODE)
        if VISUAL_MODE == "videos":
            visual_files = fetch_segment_videos(segments)
            log_cost("pexels", "video_search", units=len(segments), cost_usd=0.0, video_id=vid_id)
        else:
            visual_files = fetch_segment_images(segments)
            log_cost("pexels", "search", units=len(segments), cost_usd=0.0, video_id=vid_id)

        # Step 4 — Thumbnail (use dashboard design if provided, else generate)
        thumbnail_path = None
        if thumb_data_url:
            thumbnail_path = _resolve_thumb_from_data_url(
                thumb_data_url, _THUMB_OUT
            )
        if not thumbnail_path:
            thumb_bg = next((f for f in visual_files if f.lower().endswith(".jpg")), None)
            if thumb_bg is None:
                from moviepy.editor import VideoFileClip as _VFC
                _vc = _VFC(visual_files[0], audio=False)
                thumb_bg = visual_files[0].replace(".mp4", "_thumb.jpg")
                _vc.save_frame(thumb_bg, t=0)
                _vc.close()
            thumbnail_path = make_thumbnail(content, bg_path=thumb_bg, out=_THUMB_OUT)
        thumbnail_path = os.path.abspath(thumbnail_path)
        logger.info("Thumbnail path: %s (exists=%s)", thumbnail_path, os.path.exists(thumbnail_path))

        # Step 5 — Video assembly
        music = BG_MUSIC_PATH if BG_MUSIC_PATH else None
        video_path = build_video(segments, audio_files, visual_files,
                                 title=content.get("title"), music_path=music)

        # Step 5b — YouTube Shorts (optional)
        short_paths = []
        if shorts_count and shorts_count > 0:
            logger.info("Building %d YouTube Short(s)…", shorts_count)
            short_paths = build_shorts(
                segments, audio_files, visual_files,
                title=content.get("title"), count=shorts_count, music_path=music,
            )

        # Step 6 — Upload main video (skip if already uploaded)
        if is_video_uploaded(vid_id):
            rec = get_video_record(vid_id)
            youtube_id = rec["youtube_id"]
            logger.info("Video already uploaded (vid_id=%d, yt=%s) — skipping re-upload", vid_id, youtube_id)
        else:
            youtube_id = upload_video(video_path, thumbnail_path, content, channel_slug=channel_slug)

        # Step 6b — Upload Shorts (skip already-uploaded count)
        shorts_uploaded = 0
        for sp in short_paths:
            try:
                short_title = f"{content.get('title', topic)} #Shorts"
                short_content = {
                    "title": short_title[:100],
                    "description": content.get("description", ""),
                    "tags": content.get("tags", []) + ["Shorts"],
                }
                upload_video(sp, thumbnail_path, short_content, channel_slug=channel_slug)
                shorts_uploaded += 1
                logger.info("Uploaded Short: %s", sp)
            except Exception as e:
                logger.error("Failed to upload Short %s: %s", sp, e)

        # Step 7 — Record success
        duration_s = sum(seg.get("duration_s", 45) for seg in segments)
        log_video_complete(vid_id, content["title"], youtube_id, duration_s)

        logger.info(
            "Pipeline complete: https://youtube.com/watch?v=%s", youtube_id
        )
        return youtube_id

    except Exception as exc:
        logger.error("Pipeline failed for '%s': %s", topic, exc)
        log_video_error(vid_id, str(exc))
        raise
    finally:
        _cleanup_temp_files()
        _release_lock()


def run_preview(topic: str, progress_cb=None, script_text: str | None = None,
               seo: dict | None = None, thumb_data_url: str | None = None,
               guidance: str | None = None, shorts_count: int = 0) -> tuple:
    """Run pipeline steps 1–5 (generate + build video) WITHOUT uploading.

    Args:
        topic:          The video topic string.
        progress_cb:    Optional callable(message: str) called at each step.
        script_text:    Pre-written script from the dashboard Script Writer tab.
        seo:            Dict with 'title', 'description', 'tags' from SEO tab.
        thumb_data_url: Base64 JPEG data URL from the dashboard Thumbnail tab.
        guidance:       Optional creator instructions for AI script generation.
        shorts_count:   Number of Shorts to generate (0–3). 0 = skip.

    Returns:
        (video_path, thumbnail_path, content_dict, vid_db_id)
        content_dict will contain '_shorts_paths' list if shorts were generated.
    """

    def _p(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)
        logger.info(msg)

    _acquire_lock()
    vid_id = log_video_start(topic, CHANNEL_NICHE, CHANNEL_LANGUAGE)
    _cleanup_media_dirs()
    try:
        # Step 1 — Script
        if script_text:
            _p("Converting your Script Writer script to pipeline format…")
            content = script_text_to_segments(script_text, topic, seo_override=seo)
            usage = content.pop("_usage", {})
            log_cost("anthropic", "script_convert",
                     units=usage.get("input_tokens", 500) + usage.get("output_tokens", 0),
                     cost_usd=usage.get("cost_usd", 0.001), video_id=vid_id)
        else:
            _p("Generating AI script…")
            content = generate_script(topic, guidance=guidance)
            usage = content.pop("_usage", {})
            log_cost("anthropic", "script",
                     units=usage.get("input_tokens", 3000) + usage.get("output_tokens", 0),
                     cost_usd=usage.get("cost_usd", 0.07), video_id=vid_id)
            if seo:
                if seo.get("title"):       content["title"]       = seo["title"]
                if seo.get("description"): content["description"] = seo["description"]
                if seo.get("tags"):        content["tags"]        = seo["tags"]

        segments = content["segments"]

        _p(f"Generating audio for {len(segments)} segments…")
        audio_files = generate_audio_segments(segments)
        log_cost("elevenlabs", "tts", units=len(segments) * 300, cost_usd=0.05, video_id=vid_id)

        _p(f"Fetching visuals ({VISUAL_MODE}) for {len(segments)} segments…")
        if VISUAL_MODE == "videos":
            visual_files = fetch_segment_videos(segments)
            log_cost("pexels", "video_search", units=len(segments), cost_usd=0.0, video_id=vid_id)
        else:
            visual_files = fetch_segment_images(segments)
            log_cost("pexels", "search", units=len(segments), cost_usd=0.0, video_id=vid_id)

        # Step 4 — Thumbnail (use dashboard design if provided, else generate)
        thumbnail_path = None
        if thumb_data_url:
            _p("Using custom thumbnail from Thumbnail tab…")
            thumbnail_path = _resolve_thumb_from_data_url(thumb_data_url, _THUMB_OUT)
        if not thumbnail_path:
            _p("Creating thumbnail…")
            thumb_bg = next((f for f in visual_files if f.lower().endswith(".jpg")), None)
            if thumb_bg is None:
                from moviepy.editor import VideoFileClip as _VFC
                _vc = _VFC(visual_files[0], audio=False)
                thumb_bg = visual_files[0].replace(".mp4", "_thumb.jpg")
                _vc.save_frame(thumb_bg, t=0)
                _vc.close()
            thumbnail_path = make_thumbnail(content, bg_path=thumb_bg, out=_THUMB_OUT)
        thumbnail_path = os.path.abspath(thumbnail_path)
        logger.info("Thumbnail path: %s (exists=%s)", thumbnail_path, os.path.exists(thumbnail_path))

        _p("Building video (this may take a few minutes)…")
        music = BG_MUSIC_PATH if BG_MUSIC_PATH else None
        video_path = build_video(segments, audio_files, visual_files,
                                 title=content.get("title"), music_path=music)

        # Build Shorts if requested
        if shorts_count and shorts_count > 0:
            _p(f"Building {shorts_count} YouTube Short(s)…")
            short_paths = build_shorts(
                segments, audio_files, visual_files,
                title=content.get("title"), count=shorts_count, music_path=music,
            )
            content["_shorts_paths"] = short_paths

        _p("✓ Video ready for review!")
        return video_path, thumbnail_path, content, vid_id

    except Exception as exc:
        logger.error("Preview pipeline failed for '%s': %s", topic, exc)
        log_video_error(vid_id, str(exc))
        raise
    finally:
        _cleanup_temp_files()
        _release_lock()
