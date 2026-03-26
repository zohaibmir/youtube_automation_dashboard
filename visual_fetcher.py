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

def _search_pexels_video(keyword: str) -> str | None:
    """Search Pexels videos for *keyword*.

    Returns the best HD URL found, or None.
    Picks the highest-resolution HD/UHD file across all returned results
    (not just the first video) so quality and relevance improve.
    """
    resp = requests.get(
        _PEXELS_VIDEO_URL,
        headers=_pexels_headers(),
        params={"query": keyword, "per_page": 15, "orientation": "landscape"},
        timeout=_REQUEST_TIMEOUT,
    )
    videos = resp.json().get("videos", [])
    if not videos:
        return None

    best_url = None
    best_pixels = 0
    for vid in videos:
        for vf in vid.get("video_files", []):
            if vf.get("quality") not in ("hd", "uhd"):
                continue
            w, h = vf.get("width", 0), vf.get("height", 0)
            if w < 1280:
                continue
            pixels = w * h
            if pixels > best_pixels:
                best_pixels = pixels
                best_url = vf["link"]

    # If no hd/uhd found, fall back to any file with decent width
    if not best_url:
        for vid in videos:
            all_files = vid.get("video_files", [])
            all_files.sort(key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)
            if all_files:
                best_url = all_files[0]["link"]
                break

    return best_url


def fetch_segment_videos(
    segments: list[dict],
    out_dir: str = IMAGES_DIR,
) -> list[str]:
    """Download one stock video clip per segment (MP4, HD preferred).

    Search strategy per segment (most-specific → least-specific):
      1. visual_keyword   — 3-5 word specific term from the script
      2. visual_keyword_fallback — 2-word fallback from the script
      3. First word of visual_keyword (single broad term)
      4. Generic fallback → static image from Pexels

    video_builder handles .jpg files transparently via Ken Burns zoom.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for i, segment in enumerate(segments):
        keyword = segment.get("visual_keyword", "cityscape")
        fallback_kw = segment.get("visual_keyword_fallback", "")
        # Build a ranked list of search terms to try
        candidates = [keyword]
        if fallback_kw and fallback_kw.lower() != keyword.lower():
            candidates.append(fallback_kw)
        # Simplified: first two words of main keyword
        simplified = " ".join(keyword.split()[:2])
        if simplified and simplified.lower() not in [c.lower() for c in candidates]:
            candidates.append(simplified)

        logger.info("Fetching video %d/%d: '%s'", i + 1, len(segments), keyword)

        video_url = None
        used_kw = None
        for kw in candidates:
            video_url = _search_pexels_video(kw)
            if video_url:
                used_kw = kw
                break

        if used_kw and used_kw != keyword:
            logger.info("  Resolved via fallback keyword: '%s'", used_kw)

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
