"""visual_fetcher.py — Pexels stock image & video downloader.

Single responsibility: resolve a visual keyword to a local media file.
Supports VISUAL_MODE=images (JPEG) or VISUAL_MODE=videos (MP4).
"""

import logging
from pathlib import Path

import requests

from config import IMAGES_DIR, PEXELS_API_KEY

logger = logging.getLogger(__name__)

_PEXELS_PHOTO_URL  = "https://api.pexels.com/v1/search"
_PEXELS_VIDEO_URL  = "https://api.pexels.com/videos/search"
_PICSUM_FALLBACK   = "https://picsum.photos/seed/{seed}/1920/1080"
_REQUEST_TIMEOUT   = 20


def _pexels_headers() -> dict:
    return {"Authorization": PEXELS_API_KEY}


# ── Images ────────────────────────────────────────────────────────────────────

def fetch_segment_images(
    segments: list[dict],
    out_dir: str = IMAGES_DIR,
) -> list[str]:
    """Download one background image per segment (JPEG, 1920×1080+)."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for i, segment in enumerate(segments):
        keyword = segment.get("visual_keyword", "cityscape")
        logger.info("Fetching image %d/%d: '%s'", i + 1, len(segments), keyword)

        resp = requests.get(
            _PEXELS_PHOTO_URL,
            headers=_pexels_headers(),
            params={"query": keyword, "per_page": 5, "orientation": "landscape"},
            timeout=_REQUEST_TIMEOUT,
        )
        photos = resp.json().get("photos", [])

        if photos:
            # Prefer highest-resolution landscape shot
            best = max(photos, key=lambda p: p["width"] * p["height"])
            image_url = best["src"].get("original") or best["src"]["large2x"]
        else:
            logger.warning("No Pexels results for '%s' — using picsum fallback", keyword)
            image_url = _PICSUM_FALLBACK.format(seed=i)

        path = f"{out_dir}/img_{i:03d}.jpg"
        with open(path, "wb") as f:
            f.write(requests.get(image_url, timeout=_REQUEST_TIMEOUT).content)
        paths.append(path)

    logger.info("Image download complete: %d files written to %s", len(paths), out_dir)
    return paths


# ── Videos ───────────────────────────────────────────────────────────────────

def fetch_segment_videos(
    segments: list[dict],
    out_dir: str = IMAGES_DIR,
) -> list[str]:
    """Download one stock video clip per segment (MP4, HD preferred).

    Falls back to a static image (renamed .jpg) if no video is found,
    which video_builder handles automatically by checking the extension.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for i, segment in enumerate(segments):
        keyword = segment.get("visual_keyword", "cityscape")
        logger.info("Fetching video %d/%d: '%s'", i + 1, len(segments), keyword)

        resp = requests.get(
            _PEXELS_VIDEO_URL,
            headers=_pexels_headers(),
            params={"query": keyword, "per_page": 5, "orientation": "landscape"},
            timeout=_REQUEST_TIMEOUT,
        )
        data = resp.json()
        videos = data.get("videos", [])

        video_url = None
        if videos:
            # Pick the best HD file from the first result
            video_files = videos[0].get("video_files", [])
            # Prefer HD landscape files
            hd_files = [
                vf for vf in video_files
                if vf.get("quality") in ("hd", "uhd") and vf.get("width", 0) >= 1280
            ]
            chosen = (hd_files or video_files)
            if chosen:
                # Largest resolution first
                chosen.sort(key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)
                video_url = chosen[0]["link"]

        if video_url:
            path = f"{out_dir}/vid_{i:03d}.mp4"
            logger.info("Downloading video clip → %s", path)
            with open(path, "wb") as f:
                f.write(requests.get(video_url, timeout=60).content)
        else:
            # Fallback: grab an image instead (video_builder handles .jpg transparently)
            logger.warning("No Pexels video for '%s' — falling back to image", keyword)
            fallback_resp = requests.get(
                _PEXELS_PHOTO_URL,
                headers=_pexels_headers(),
                params={"query": keyword, "per_page": 3, "orientation": "landscape"},
                timeout=_REQUEST_TIMEOUT,
            )
            photos = fallback_resp.json().get("photos", [])
            image_url = photos[0]["src"]["large2x"] if photos else _PICSUM_FALLBACK.format(seed=i)
            path = f"{out_dir}/vid_{i:03d}.jpg"
            with open(path, "wb") as f:
                f.write(requests.get(image_url, timeout=_REQUEST_TIMEOUT).content)

        paths.append(path)

    logger.info("Visual download complete: %d files written to %s", len(paths), out_dir)
    return paths
