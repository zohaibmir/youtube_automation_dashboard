"""pipeline.py — Full video production pipeline orchestrator.

Single responsibility: coordinate the end-to-end pipeline by calling
the individual specialist modules in the correct order. Nothing else.
All business logic lives in the modules it calls.

Parallel execution: each run() / run_preview() call creates its own
isolated working directory under runs/<job_id>/ so multiple pipelines
can execute simultaneously without interfering with each other.
"""

import glob
import json
import logging
import os
import signal
import shutil
import subprocess
import uuid

from audio_generator import generate_audio_segments
from config import BG_MUSIC_PATH, CHANNEL_LANGUAGE, CHANNEL_NICHE, CROSSFADE_DURATION, INTRO_DURATION, VISUAL_MODE, AUTO_CHAPTERS, PIN_FIRST_COMMENT, PINNED_COMMENT_TEXT, CHANNEL_NAME, REDDIT_ENABLED, REDDIT_SUBREDDITS, REDDIT_POST_FLAIR

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_RUNS_DIR = os.path.join(_BASE_DIR, "runs")          # runs/<job_id>/ per-run workdirs
_JOBS_DIR = os.path.join(_BASE_DIR, ".jobs")         # .jobs/<job_id>.json per-job status

os.makedirs(_RUNS_DIR, exist_ok=True)
os.makedirs(_JOBS_DIR, exist_ok=True)

from content_generator import generate_script, script_text_to_segments
from database import log_cost, log_video_complete, log_video_error, log_video_start, get_video_record, is_video_uploaded
from shorts_builder import build_shorts
from thumbnail import make_thumbnail
from video_builder import build_video
from visual_fetcher import fetch_segment_images, fetch_segment_videos
from youtube_uploader import upload_video, pin_first_comment
from reddit_poster import post_to_reddit

logger = logging.getLogger(__name__)


# ── Chapter / timestamp helpers ───────────────────────────────────────────────

def _audio_duration(path: str) -> float:
    """Return duration of an audio file in seconds via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
            capture_output=True, text=True, timeout=10,
        )
        streams = json.loads(r.stdout).get("streams", [])
        return float(streams[0]["duration"]) if streams else 0.0
    except Exception:
        return 0.0


def build_chapters(segments: list[dict], audio_files: list[str]) -> str:
    """Build a YouTube-compatible chapter string from segment audio durations.

    YouTube chapter requirements:
      - At least 3 chapters
      - First chapter must start at 0:00
      - Each chapter >= 10 seconds
      - Format: "MM:SS Chapter Title" (one per line)

    The intro clip (INTRO_DURATION seconds) is added as the first chapter.
    Crossfade overlap is subtracted between clips to match actual video timing.

    Returns a string block ready to append to the video description.
    """
    def _fmt(secs: float) -> str:
        s = int(secs)
        h, rem = divmod(s, 3600)
        m, sc = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{sc:02d}"
        return f"{m}:{sc:02d}"

    lines = []
    cursor = 0.0

    # Chapter 0 — branded intro
    if INTRO_DURATION >= 10:
        lines.append(f"{_fmt(cursor)} Introduction")
        cursor += INTRO_DURATION - CROSSFADE_DURATION
    else:
        # Intro too short for its own chapter — first content chapter anchors at 0:00
        # and we still offset the cursor for subsequent chapters
        first_content_at_zero = True
        cursor += INTRO_DURATION - CROSSFADE_DURATION

    for i, (seg, audio_path) in enumerate(zip(segments, audio_files)):
        duration = _audio_duration(audio_path)
        if duration < 10:
            # Too short — merge into running cursor without a new chapter
            cursor += max(duration - CROSSFADE_DURATION, 0)
            continue
        caption = seg.get("caption") or seg.get("title") or f"Part {i + 1}"
        # Clean up caption for chapter label (strip quotes, trim length)
        caption = caption.strip('"\' ').split("\n")[0][:60]
        # First content chapter must anchor at 0:00 if intro was too short
        if not lines and locals().get("first_content_at_zero"):
            lines.append(f"0:00 {caption}")
        else:
            lines.append(f"{_fmt(max(cursor, 0))} {caption}")
        cursor += duration - CROSSFADE_DURATION

    if len(lines) < 3:
        return ""  # YouTube requires at least 3 chapters

    return "\n".join(lines)


# ── Per-job workdir helpers ───────────────────────────────────────────────────

def _new_job_dir() -> tuple[str, str]:
    """Create a unique working directory for one pipeline run.

    Returns (job_id, job_dir) where job_dir is runs/<job_id>/.
    Each run gets its own images/, audio/, thumbnail.jpg inside.
    """
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(_RUNS_DIR, job_id)
    os.makedirs(os.path.join(job_dir, "images"), exist_ok=True)
    os.makedirs(os.path.join(job_dir, "audio"), exist_ok=True)
    return job_id, job_dir


def _cleanup_job_dir(job_dir: str) -> None:
    """Remove the per-run working directory and its contents."""
    try:
        shutil.rmtree(job_dir, ignore_errors=True)
        logger.debug("Cleaned job dir: %s", job_dir)
    except Exception:
        pass


# ── Parallel-safe jobs registry ──────────────────────────────────────────────

def _job_file(job_id: str) -> str:
    return os.path.join(_JOBS_DIR, f"{job_id}.json")


def _register_job(job_id: str, topic: str, pid: int) -> None:
    data = {"job_id": job_id, "pid": pid, "topic": topic, "status": "running"}
    with open(_job_file(job_id), "w") as f:
        json.dump(data, f)


def _finish_job(job_id: str, youtube_id: str | None = None,
                error: str | None = None) -> None:
    fp = _job_file(job_id)
    try:
        with open(fp) as f:
            data = json.load(f)
    except Exception:
        data = {"job_id": job_id}
    data["status"] = "error" if error else "done"
    if youtube_id:
        data["youtube_id"] = youtube_id
    if error:
        data["error"] = error
    with open(fp, "w") as f:
        json.dump(data, f)


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def list_jobs() -> list[dict]:
    """Return status of all known pipeline jobs (running + recent)."""
    jobs = []
    for fp in glob.glob(os.path.join(_JOBS_DIR, "*.json")):
        try:
            with open(fp) as f:
                data = json.load(f)
            # Mark stale running jobs
            if data.get("status") == "running" and not _is_pid_alive(data.get("pid", 0)):
                data["status"] = "stale"
            jobs.append(data)
        except Exception:
            pass
    return sorted(jobs, key=lambda j: j.get("job_id", ""))


def pipeline_status() -> dict:
    """Return summary of all running/recent jobs (replaces single-lock status)."""
    jobs = list_jobs()
    running = [j for j in jobs if j["status"] == "running"]
    return {
        "running": len(running) > 0,
        "running_count": len(running),
        "jobs": jobs,
        # Legacy compat: expose first running pid if any
        "pid": running[0]["pid"] if running else None,
    }


def kill_pipeline(job_id: str | None = None) -> dict:
    """Kill a running pipeline job. If job_id is None, kills all running jobs."""
    killed = []
    jobs = list_jobs()
    targets = [j for j in jobs if j["status"] == "running"]
    if job_id:
        targets = [j for j in targets if j["job_id"] == job_id]
    if not targets:
        return {"ok": True, "message": "No running pipeline jobs found"}
    for job in targets:
        pid = job.get("pid", 0)
        try:
            if _is_pid_alive(pid):
                os.kill(pid, signal.SIGTERM)
                logger.info("Killed job %s (PID %d)", job["job_id"], pid)
            _finish_job(job["job_id"], error="killed by user")
            killed.append(job["job_id"])
        except Exception as e:
            logger.warning("Failed to kill job %s: %s", job["job_id"], e)
    return {"ok": True, "message": f"Killed {len(killed)} job(s): {killed}"}


# ── Legacy single-lock compat (used by old dashboard endpoints) ───────────────
# These kept for backwards compat — server.py calls pipeline_status() / kill_pipeline()

_LOCK_FILE = os.path.join(_BASE_DIR, ".pipeline.lock")  # kept for reference only


def _cleanup_temp_files(job_dir: str | None = None) -> None:
    """Remove MoviePy TEMP_MPY_* scratch files from the job dir (or base dir)."""
    search_dir = job_dir or _BASE_DIR
    for pattern in ("*TEMP_MPY*", "images/*_thumb.jpg"):
        for f in glob.glob(os.path.join(search_dir, pattern)):
            try:
                os.remove(f)
                logger.debug("Cleaned up temp file: %s", f)
            except OSError:
                pass


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

    Parallel-safe: each call creates an isolated runs/<job_id>/ directory.
    Multiple videos can be generated simultaneously in separate processes.

    Args:
        topic:          The video topic.
        script_text:    Pre-written script from the dashboard Script Writer tab.
        seo:            Dict with 'title', 'description', 'tags' from the SEO tab.
        thumb_data_url: Base64 JPEG data URL from the dashboard Thumbnail tab.
        channel_slug:   YouTube channel slug for multi-account upload.
        guidance:       Optional creator instructions for AI script generation.
        shorts_count:   Number of Shorts to generate (0-3). 0 = skip.

    Returns:
        The YouTube video ID on success.
    """
    job_id, job_dir = _new_job_dir()
    images_dir = os.path.join(job_dir, "images")
    audio_dir  = os.path.join(job_dir, "audio")
    thumb_out  = os.path.join(job_dir, "thumbnail.jpg")

    _register_job(job_id, topic, os.getpid())
    logger.info("[job=%s] Pipeline starting: %s", job_id, topic)
    vid_id = log_video_start(topic, CHANNEL_NICHE, CHANNEL_LANGUAGE)

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
            content = generate_script(topic, guidance=guidance, max_tokens=8000)
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

        # Step 2 — Text-to-speech (into isolated audio dir)
        audio_files = generate_audio_segments(segments, out_dir=audio_dir)
        log_cost("elevenlabs", "tts", units=len(segments) * 300, cost_usd=0.05, video_id=vid_id)

        # Step 3 — Stock visuals (into isolated images dir)
        if VISUAL_MODE == "videos":
            visual_files = fetch_segment_videos(segments, out_dir=images_dir)
            log_cost("pexels", "video_search", units=len(segments), cost_usd=0.0, video_id=vid_id)
        else:
            visual_files = fetch_segment_images(segments, out_dir=images_dir)
            log_cost("pexels", "search", units=len(segments), cost_usd=0.0, video_id=vid_id)

        # Step 4 — Thumbnail
        thumbnail_path = None
        if thumb_data_url:
            thumbnail_path = _resolve_thumb_from_data_url(thumb_data_url, thumb_out)
        if not thumbnail_path:
            thumb_bg = next((f for f in visual_files if f.lower().endswith(".jpg")), None)
            if thumb_bg is None:
                from moviepy.editor import VideoFileClip as _VFC
                _vc = _VFC(visual_files[0], audio=False)
                thumb_bg = visual_files[0].replace(".mp4", "_thumb.jpg")
                _vc.save_frame(thumb_bg, t=0)
                _vc.close()
            thumbnail_path = make_thumbnail(content, bg_path=thumb_bg, out=thumb_out)
        thumbnail_path = os.path.abspath(thumbnail_path)
        logger.info("[job=%s] Thumbnail: %s (exists=%s)", job_id, thumbnail_path, os.path.exists(thumbnail_path))

        # Step 5 — Video assembly
        music = BG_MUSIC_PATH if BG_MUSIC_PATH else None
        video_path = build_video(segments, audio_files, visual_files,
                                 title=content.get("title"), music_path=music)

        # Step 5a — Inject YouTube chapters into description (if enabled)
        if AUTO_CHAPTERS:
            chapters = build_chapters(segments, audio_files)
            if chapters:
                sep = "\n\n" if content.get("description") else ""
                content["description"] = content.get("description", "") + sep + "CHAPTERS\n" + chapters
                logger.info("[job=%s] Chapters injected (%d lines)", job_id, len(chapters.splitlines()))
        else:
            logger.info("[job=%s] Auto chapters disabled — skipping", job_id)

        # Step 5b — YouTube Shorts
        short_paths = []
        if shorts_count and shorts_count > 0:
            logger.info("[job=%s] Building %d Short(s)…", job_id, shorts_count)
            short_paths = build_shorts(
                segments, audio_files, visual_files,
                title=content.get("title"), count=shorts_count, music_path=music,
            )

        # Step 6 — Upload main video
        if is_video_uploaded(vid_id):
            rec = get_video_record(vid_id)
            youtube_id = rec["youtube_id"]
            logger.info("[job=%s] Already uploaded (yt=%s) — skipping", job_id, youtube_id)
        else:
            youtube_id = upload_video(video_path, thumbnail_path, content, channel_slug=channel_slug)

        # Step 6b — Upload Shorts
        for sp in short_paths:
            try:
                short_content = {
                    "title": f"{content.get('title', topic)[:95]} #Shorts",
                    "description": content.get("description", ""),
                    "tags": content.get("tags", []) + ["Shorts"],
                }
                upload_video(sp, thumbnail_path, short_content, channel_slug=channel_slug)
                logger.info("[job=%s] Uploaded Short: %s", job_id, sp)
            except Exception as e:
                logger.error("[job=%s] Failed to upload Short %s: %s", job_id, sp, e)

        # Step 7 — Record success
        duration_s = sum(seg.get("duration_s", 45) for seg in segments)
        log_video_complete(vid_id, content["title"], youtube_id, duration_s)
        _finish_job(job_id, youtube_id=youtube_id)

        # Step 8 — Pin first comment (if enabled)
        if PIN_FIRST_COMMENT and youtube_id:
            ch_name = CHANNEL_NAME or "this channel"
            comment = (
                PINNED_COMMENT_TEXT
                or f"⬇️ WATCH NEXT — more signs & prophecies on {ch_name}\n"
                   f"🔔 Subscribe & hit the bell so you never miss a video\n"
                   f"💬 Share this with someone who needs to see it"
            )
            pin_first_comment(youtube_id, comment, channel_slug=channel_slug)

        # Step 9 — Reddit auto-post (if enabled)
        if REDDIT_ENABLED and youtube_id:
            yt_url = f"https://youtube.com/watch?v={youtube_id}"
            reddit_urls = post_to_reddit(
                title=content["title"],
                youtube_url=yt_url,
                subreddits_csv=REDDIT_SUBREDDITS,
                flair=REDDIT_POST_FLAIR or None,
            )
            if reddit_urls:
                logger.info("[job=%s] Reddit: posted to %d subreddit(s)", job_id, len(reddit_urls))

        logger.info("[job=%s] Pipeline complete: https://youtube.com/watch?v=%s", job_id, youtube_id)
        return youtube_id

    except Exception as exc:
        logger.error("[job=%s] Pipeline failed for '%s': %s", job_id, topic, exc)
        log_video_error(vid_id, str(exc))
        _finish_job(job_id, error=str(exc))
        raise
    finally:
        _cleanup_temp_files(job_dir)
        _cleanup_job_dir(job_dir)


def run_preview(topic: str, progress_cb=None, script_text: str | None = None,
               seo: dict | None = None, thumb_data_url: str | None = None,
               guidance: str | None = None, shorts_count: int = 0) -> tuple:
    """Run pipeline steps 1–5 (generate + build) WITHOUT uploading.

    Parallel-safe: uses an isolated runs/<job_id>/ working directory.

    Returns:
        (video_path, thumbnail_path, content_dict, vid_db_id)
    """

    def _p(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)
        logger.info(msg)

    job_id, job_dir = _new_job_dir()
    images_dir = os.path.join(job_dir, "images")
    audio_dir  = os.path.join(job_dir, "audio")
    thumb_out  = os.path.join(job_dir, "thumbnail.jpg")

    _register_job(job_id, topic, os.getpid())
    vid_id = log_video_start(topic, CHANNEL_NICHE, CHANNEL_LANGUAGE)
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
        audio_files = generate_audio_segments(segments, out_dir=audio_dir)
        log_cost("elevenlabs", "tts", units=len(segments) * 300, cost_usd=0.05, video_id=vid_id)

        _p(f"Fetching visuals ({VISUAL_MODE}) for {len(segments)} segments…")
        if VISUAL_MODE == "animated":
            from animated_visual_fetcher import fetch_animated_clips
            visual_files = fetch_animated_clips(segments, out_dir=images_dir)
            clip_cost = len(segments) * 0.14
            log_cost("kling", "text2video", units=len(segments), cost_usd=clip_cost, video_id=vid_id)
        elif VISUAL_MODE == "videos":
            visual_files = fetch_segment_videos(segments, out_dir=images_dir)
            log_cost("pexels", "video_search", units=len(segments), cost_usd=0.0, video_id=vid_id)
        else:
            visual_files = fetch_segment_images(segments, out_dir=images_dir)
            log_cost("pexels", "search", units=len(segments), cost_usd=0.0, video_id=vid_id)

        # Step 4 — Thumbnail
        thumbnail_path = None
        if thumb_data_url:
            _p("Using custom thumbnail from Thumbnail tab…")
            thumbnail_path = _resolve_thumb_from_data_url(thumb_data_url, thumb_out)
        if not thumbnail_path:
            _p("Creating thumbnail…")
            thumb_bg = next((f for f in visual_files if f.lower().endswith(".jpg")), None)
            if thumb_bg is None:
                from moviepy.editor import VideoFileClip as _VFC
                _vc = _VFC(visual_files[0], audio=False)
                thumb_bg = visual_files[0].replace(".mp4", "_thumb.jpg")
                _vc.save_frame(thumb_bg, t=0)
                _vc.close()
            thumbnail_path = make_thumbnail(content, bg_path=thumb_bg, out=thumb_out)
        thumbnail_path = os.path.abspath(thumbnail_path)

        _p("Building video (this may take a few minutes)…")
        music = BG_MUSIC_PATH if BG_MUSIC_PATH else None
        video_path = build_video(segments, audio_files, visual_files,
                                 title=content.get("title"), music_path=music)

        if shorts_count and shorts_count > 0:
            _p(f"Building {shorts_count} YouTube Short(s)…")
            short_paths = build_shorts(
                segments, audio_files, visual_files,
                title=content.get("title"), count=shorts_count, music_path=music,
            )
            content["_shorts_paths"] = short_paths

        _finish_job(job_id)  # preview done — no youtube_id yet
        _p("✓ Video ready for review!")
        return video_path, thumbnail_path, content, vid_id

    except Exception as exc:
        logger.error("[job=%s] Preview failed for '%s': %s", job_id, topic, exc)
        log_video_error(vid_id, str(exc))
        _finish_job(job_id, error=str(exc))
        raise
    finally:
        _cleanup_temp_files(job_dir)
        # NOTE: do NOT clean job_dir here — video_path / audio_files still needed for upload step
