"""media_hub.py — Video discovery, analysis, and clip extraction for Upload Studio.

Lists existing video files, probes metadata via ffprobe, extracts clips
for Shorts / Reels at user-defined time ranges, and uploads to YouTube +
social platforms.
"""

import json
import os
import subprocess
from pathlib import Path

_OUTPUT_DIR = Path("output")
_SHORTS_DIR = _OUTPUT_DIR / "shorts"
_CLIPS_DIR = _OUTPUT_DIR / "clips"
_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi"}


# ── Discovery ──────────────────────────────────────────────────────────────

def list_videos() -> dict:
    """Return all video files under output/ with basic info."""
    try:
        videos = []
        for d in (_OUTPUT_DIR, _SHORTS_DIR):
            if not d.exists():
                continue
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in _VIDEO_EXTS and f.is_file():
                    videos.append({
                        "name": f.name,
                        "path": str(f),
                        "size_mb": round(f.stat().st_size / 1048576, 1),
                        "dir": str(d),
                    })
        return {"ok": True, "videos": videos}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def video_info(video_path: str) -> dict:
    """Probe a video file for duration, resolution, codec via ffprobe."""
    p = Path(video_path)
    if not p.exists():
        return {"ok": False, "error": "File not found"}
    # Validate path is under output/ to prevent path traversal
    try:
        p.resolve().relative_to(Path.cwd() / "output")
    except ValueError:
        return {"ok": False, "error": "Access denied — only files in output/ allowed"}
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(p)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return {"ok": False, "error": f"ffprobe failed: {result.stderr[:200]}"}
        probe = json.loads(result.stdout)
        fmt = probe.get("format", {})
        vstream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
        duration = float(fmt.get("duration", 0))
        return {
            "ok": True,
            "name": p.name,
            "path": str(p),
            "duration": round(duration, 2),
            "duration_str": f"{int(duration // 60)}:{int(duration % 60):02d}",
            "width": int(vstream.get("width", 0)),
            "height": int(vstream.get("height", 0)),
            "codec": vstream.get("codec_name", "unknown"),
            "fps": _parse_fps(vstream.get("r_frame_rate", "0/1")),
            "size_mb": round(p.stat().st_size / 1048576, 1),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _parse_fps(rate_str: str) -> float:
    """Parse '30000/1001' → 29.97."""
    try:
        num, den = rate_str.split("/")
        return round(int(num) / max(int(den), 1), 2)
    except Exception:
        return 0.0


# ── Clip extraction ─────────────────────────────────────────────────────────

def extract_clips(video_path: str, clips: list[dict]) -> dict:
    """Extract one or more clips from a video.

    Args:
        video_path: Path to source video (must be under output/).
        clips: List of {start: float, end: float, label: str}.
               Each clip will be trimmed and saved to output/clips/.

    Returns:
        {"ok": True, "clips": [{"path": ..., "label": ..., "duration": ...}]}
    """
    src = Path(video_path)
    if not src.exists():
        return {"ok": False, "error": "Source video not found"}
    try:
        src.resolve().relative_to(Path.cwd() / "output")
    except ValueError:
        return {"ok": False, "error": "Access denied — only files in output/ allowed"}

    _CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for i, clip in enumerate(clips):
        start = float(clip.get("start", 0))
        end = float(clip.get("end", 60))
        label = clip.get("label", f"clip-{i + 1}")
        duration = end - start
        if duration <= 0 or duration > 600:
            results.append({"label": label, "error": "Invalid time range (max 10 min)"})
            continue

        safe_label = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)
        stem = src.stem
        out_path = _CLIPS_DIR / f"{stem}-{safe_label}.mp4"
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-to", str(end),
            "-i", str(src), "-c:v", "libx264", "-preset", "fast",
            "-crf", "20", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            results.append({"label": label, "error": proc.stderr[:200]})
        else:
            results.append({
                "label": label,
                "path": str(out_path),
                "duration": round(duration, 2),
                "size_mb": round(out_path.stat().st_size / 1048576, 1),
            })
    return {"ok": True, "clips": results}


# ── Upload orchestration ────────────────────────────────────────────────────

def upload_main_video(video_path: str, content: dict,
                      channel_slug: str | None = None) -> dict:
    """Upload an existing video to YouTube as a main (landscape) video.

    Args:
        video_path: Path to the MP4 file.
        content: Dict with title, description, tags.
        channel_slug: Optional channel slug.
    """
    src = Path(video_path)
    if not src.exists():
        return {"ok": False, "error": "Video file not found"}
    try:
        from youtube_uploader import upload_video
        video_id = upload_video(
            video_path=str(src),
            thumbnail_path=None,
            content=content,
            channel_slug=channel_slug,
        )
        return {"ok": True, "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def upload_clips_to_platforms(clip_paths: list[str], content: dict,
                              channel_slug: str | None = None,
                              youtube_shorts: bool = True,
                              social_platforms: bool = True) -> dict:
    """Upload extracted clips to YouTube Shorts and/or social platforms.

    Args:
        clip_paths: List of clip file paths.
        content: Dict with title, description, tags.
        channel_slug: Optional channel slug for YouTube.
        youtube_shorts: If True, upload each clip as a YouTube Short.
        social_platforms: If True, upload each clip to all configured socials.
    """
    results = {"youtube_shorts": [], "social": []}
    for clip_path in clip_paths:
        cp = Path(clip_path)
        if not cp.exists():
            results["youtube_shorts"].append({"path": clip_path, "error": "File not found"})
            continue

        # YouTube Shorts upload
        if youtube_shorts:
            try:
                from youtube_uploader import upload_video
                short_content = {
                    "title": (content.get("title", "")[:90] + " #Shorts").strip(),
                    "description": content.get("description", ""),
                    "tags": content.get("tags", []),
                }
                vid_id = upload_video(
                    video_path=str(cp),
                    thumbnail_path=None,
                    content=short_content,
                    channel_slug=channel_slug,
                )
                results["youtube_shorts"].append({
                    "path": clip_path, "video_id": vid_id,
                    "url": f"https://www.youtube.com/shorts/{vid_id}",
                })
            except Exception as e:
                results["youtube_shorts"].append({"path": clip_path, "error": str(e)})

        # Social platforms upload
        if social_platforms:
            try:
                from social_uploader import upload_to_platforms
                social_result = upload_to_platforms(
                    video_path=str(cp),
                    title=content.get("title", ""),
                    description=content.get("description", ""),
                )
                results["social"].append({"path": clip_path, **social_result})
            except Exception as e:
                results["social"].append({"path": clip_path, "error": str(e)})

    return {"ok": True, "results": results}
