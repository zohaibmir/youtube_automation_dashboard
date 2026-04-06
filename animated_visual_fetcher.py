"""animated_visual_fetcher.py — Kling AI animated clip generator.

Replaces Pexels stock footage with AI-generated animated clips when
VISUAL_MODE=animated. Each segment gets a unique 5-second animated
video clip matching its visual_keyword/description.

Kling AI API docs: https://klingai.com/dev
Pricing: ~$0.14 per 5-second std clip, ~$0.35 per 5s pro clip.

Authentication uses JWT (HS256) signed with your KLING_API_KEY + KLING_API_SECRET.
"""

import logging
import os
import time
from pathlib import Path

import requests

from config import KLING_API_KEY, KLING_API_SECRET, IMAGES_DIR

logger = logging.getLogger(__name__)

_KLING_BASE = "https://api.klingai.com"
_TEXT2VIDEO  = f"{_KLING_BASE}/v1/videos/text2video"
_IMAGE2VIDEO = f"{_KLING_BASE}/v1/videos/image2video"
_POLL_TIMEOUT = 300   # seconds to wait for generation before giving up
_POLL_INTERVAL = 5    # seconds between status checks


# ── JWT auth ──────────────────────────────────────────────────────────────────

def _make_jwt() -> str:
    """Generate a short-lived JWT for Kling API authentication."""
    try:
        import jwt as _jwt
    except ImportError:
        raise RuntimeError(
            "PyJWT is required for animated mode. Run: pip install PyJWT>=2.8.0"
        )
    now = int(time.time())
    payload = {
        "iss": KLING_API_KEY,
        "exp": now + 1800,
        "nbf": now - 5,
    }
    return _jwt.encode(payload, KLING_API_SECRET, algorithm="HS256")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_make_jwt()}",
        "Content-Type": "application/json",
    }


# ── Single clip generation ────────────────────────────────────────────────────

def _submit_text2video(prompt: str, aspect_ratio: str = "16:9", duration: str = "5") -> str:
    """Submit a text-to-video task. Returns task_id."""
    payload = {
        "model_name": "kling-v1",
        "prompt": prompt,
        "negative_prompt": "blurry, watermark, text overlay, low quality, static image",
        "cfg_scale": 0.5,
        "mode": "std",
        "aspect_ratio": aspect_ratio,
        "duration": duration,
    }
    resp = requests.post(_TEXT2VIDEO, headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Kling API error: {data.get('message', data)}")
    return data["data"]["task_id"]


def _poll_task(task_id: str) -> str:
    """Poll a task until complete. Returns the video download URL."""
    url = f"{_TEXT2VIDEO}/{task_id}"
    deadline = time.time() + _POLL_TIMEOUT
    while time.time() < deadline:
        resp = requests.get(url, headers=_headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        task = data.get("data", {})
        status = task.get("task_status", "")
        if status == "succeed":
            videos = task.get("task_result", {}).get("videos", [])
            if not videos:
                raise RuntimeError(f"Task {task_id} succeeded but no videos returned")
            return videos[0]["url"]
        if status == "failed":
            raise RuntimeError(f"Kling task {task_id} failed: {task.get('task_status_msg', '')}")
        logger.debug("Kling task %s status: %s — waiting…", task_id, status)
        time.sleep(_POLL_INTERVAL)
    raise TimeoutError(f"Kling task {task_id} did not complete within {_POLL_TIMEOUT}s")


def _download_clip(url: str, out_path: str) -> str:
    """Download a generated MP4 to a local file."""
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    return out_path


def generate_one_clip(
    prompt: str,
    out_path: str,
    aspect_ratio: str = "16:9",
    duration: str = "5",
) -> str:
    """Generate one animated clip for a given text prompt.

    Submits the task, polls until ready, downloads to out_path.
    Returns the local file path.
    """
    if not KLING_API_KEY or not KLING_API_SECRET:
        raise RuntimeError(
            "KLING_API_KEY and KLING_API_SECRET must be set to use animated mode. "
            "Get your keys at https://klingai.com/dev"
        )
    logger.info("Kling: submitting clip — %s", prompt[:60])
    task_id = _submit_text2video(prompt, aspect_ratio=aspect_ratio, duration=duration)
    logger.info("Kling: task_id=%s — polling…", task_id)
    video_url = _poll_task(task_id)
    logger.info("Kling: task %s complete — downloading", task_id)
    return _download_clip(video_url, out_path)


# ── Batch fetch (replaces Pexels for full pipeline) ──────────────────────────

def fetch_animated_clips(
    segments: list[dict],
    out_dir: str = IMAGES_DIR,
    aspect_ratio: str = "16:9",
) -> list[str]:
    """Generate one animated MP4 clip per segment (sequential, to respect API limits).

    drop-in replacement for fetch_segment_images / fetch_segment_videos.
    Returns list of local .mp4 file paths in segment order.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for i, seg in enumerate(segments):
        # Build a rich prompt from the segment data
        keyword = seg.get("visual_keyword", "")
        caption = seg.get("caption", "")
        title = seg.get("title", "")
        prompt_parts = [p for p in [keyword, caption, title] if p]
        prompt = ". ".join(prompt_parts[:2]) if prompt_parts else f"cinematic scene {i+1}"
        # Append style guidance
        prompt = (
            f"{prompt}. Cinematic camera motion, realistic lighting, "
            "news documentary style, high quality."
        )

        out_path = os.path.join(out_dir, f"anim_{i:03d}.mp4")

        try:
            generate_one_clip(prompt, out_path, aspect_ratio=aspect_ratio)
            paths.append(out_path)
        except Exception as e:
            logger.warning("Kling clip %d failed (%s) — falling back to Pexels", i, e)
            # Soft fallback: use Pexels image so pipeline doesn't crash
            from visual_fetcher import _fetch_single_image
            fallback = _fetch_single_image(i, seg, out_dir)
            paths.append(fallback)

    logger.info("Animated clip generation complete: %d clips in %s", len(paths), out_dir)
    return paths


# ── Shorts-specific helper ────────────────────────────────────────────────────

def fetch_animated_shorts_clips(
    segments: list[dict],
    out_dir: str = IMAGES_DIR,
) -> list[str]:
    """Same as fetch_animated_clips but forces 9:16 vertical for Shorts/Reels."""
    return fetch_animated_clips(segments, out_dir=out_dir, aspect_ratio="9:16")


# ── Standalone single-short generator (used by /api/shorts/generate-animated) ──

def generate_animated_short(
    topic: str,
    hooks: list[str],
    out_dir: str = IMAGES_DIR,
    aspect_ratio: str = "9:16",
) -> list[str]:
    """Generate a set of animated clips from a list of hook prompts for one Short.

    Returns list of local MP4 paths.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for i, hook in enumerate(hooks):
        prompt = (
            f"{hook}. Topic: {topic}. Vertical format, cinematic, "
            "close-up motion, dramatic lighting, documentary style."
        )
        out_path = os.path.join(out_dir, f"short_anim_{i:03d}.mp4")
        try:
            generate_one_clip(prompt, out_path, aspect_ratio=aspect_ratio, duration="5")
            paths.append(out_path)
        except Exception as e:
            logger.warning("Short clip %d failed: %s", i, e)
    return paths
