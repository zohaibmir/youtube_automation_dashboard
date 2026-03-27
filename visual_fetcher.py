"""visual_fetcher.py — Pexels stock image & video downloader.

Single responsibility: resolve a visual keyword to a local media file.
Supports VISUAL_MODE=images (JPEG) or VISUAL_MODE=videos (MP4).
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from config import IMAGES_DIR, PEXELS_API_KEY

logger = logging.getLogger(__name__)

_PEXELS_PHOTO_URL  = "https://api.pexels.com/v1/search"
_PEXELS_VIDEO_URL  = "https://api.pexels.com/videos/search"
_PICSUM_FALLBACK   = "https://picsum.photos/seed/{seed}/1920/1080"
_REQUEST_TIMEOUT   = 20
_MAX_RETRIES       = 3
_PARALLEL_WORKERS  = 5


def _pexels_headers() -> dict:
    return {"Authorization": PEXELS_API_KEY}


def _retry_get(url: str, **kwargs) -> requests.Response:
    """GET with exponential backoff (3 attempts)."""
    timeout = kwargs.pop("timeout", _REQUEST_TIMEOUT)
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except (requests.RequestException, requests.HTTPError) as e:
            if attempt == _MAX_RETRIES:
                raise
            wait = 2 ** attempt
            logger.warning("Retry %d/%d for %s: %s (wait %ds)", attempt, _MAX_RETRIES, url[:80], e, wait)
            time.sleep(wait)


# ── Images ────────────────────────────────────────────────────────────────────

def _fetch_single_image(i: int, segment: dict, out_dir: str) -> str:
    """Download one image for a single segment (used by ThreadPoolExecutor)."""
    keyword = segment.get("visual_keyword", "cityscape")
    logger.info("Fetching image %d: '%s'", i + 1, keyword)

    try:
        resp = _retry_get(
            _PEXELS_PHOTO_URL,
            headers=_pexels_headers(),
            params={"query": keyword, "per_page": 5, "orientation": "landscape"},
        )
        photos = resp.json().get("photos", [])
    except Exception:
        photos = []

    if photos:
        best = max(photos, key=lambda p: p["width"] * p["height"])
        # Use large2x (1920px) instead of original (can be 6000px+)
        image_url = best["src"].get("large2x") or best["src"]["original"]
    else:
        logger.warning("No Pexels results for '%s' — using picsum fallback", keyword)
        image_url = _PICSUM_FALLBACK.format(seed=i)

    path = f"{out_dir}/img_{i:03d}.jpg"
    data = _retry_get(image_url).content
    with open(path, "wb") as f:
        f.write(data)
    return path


def fetch_segment_images(
    segments: list[dict],
    out_dir: str = IMAGES_DIR,
) -> list[str]:
    """Download one background image per segment in parallel (JPEG, 1920x wide)."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    # Parallel download
    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_single_image, i, seg, out_dir): i
            for i, seg in enumerate(segments)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logger.error("Image fetch failed for segment %d: %s", idx, e)
                # Fallback: picsum placeholder
                path = f"{out_dir}/img_{idx:03d}.jpg"
                data = requests.get(_PICSUM_FALLBACK.format(seed=idx), timeout=_REQUEST_TIMEOUT).content
                with open(path, "wb") as f:
                    f.write(data)
                results[idx] = path

    paths = [results[i] for i in range(len(segments))]
    logger.info("Image download complete: %d files written to %s", len(paths), out_dir)
    return paths


# ── Videos ───────────────────────────────────────────────────────────────────

def _search_pexels_video(keyword: str) -> str | None:
    """Search Pexels videos for *keyword*.

    Returns the best HD URL found, or None.
    """
    try:
        resp = _retry_get(
            _PEXELS_VIDEO_URL,
            headers=_pexels_headers(),
            params={"query": keyword, "per_page": 15, "orientation": "landscape"},
        )
        videos = resp.json().get("videos", [])
    except Exception:
        return None

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


def _fetch_single_video(i: int, segment: dict, out_dir: str) -> str:
    """Download one video clip for a single segment (used by ThreadPoolExecutor)."""
    keyword = segment.get("visual_keyword", "cityscape")
    fallback_kw = segment.get("visual_keyword_fallback", "")
    candidates = [keyword]
    if fallback_kw and fallback_kw.lower() != keyword.lower():
        candidates.append(fallback_kw)
    simplified = " ".join(keyword.split()[:2])
    if simplified and simplified.lower() not in [c.lower() for c in candidates]:
        candidates.append(simplified)

    logger.info("Fetching video %d: '%s'", i + 1, keyword)

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
        data = _retry_get(video_url, timeout=60).content
        with open(path, "wb") as f:
            f.write(data)
    else:
        # Fallback: grab an image instead (video_builder handles .jpg transparently)
        logger.warning("No Pexels video for '%s' — falling back to image", keyword)
        try:
            fallback_resp = _retry_get(
                _PEXELS_PHOTO_URL,
                headers=_pexels_headers(),
                params={"query": keyword, "per_page": 3, "orientation": "landscape"},
            )
            photos = fallback_resp.json().get("photos", [])
            image_url = photos[0]["src"]["large2x"] if photos else _PICSUM_FALLBACK.format(seed=i)
        except Exception:
            image_url = _PICSUM_FALLBACK.format(seed=i)
        path = f"{out_dir}/vid_{i:03d}.jpg"
        data = _retry_get(image_url).content
        with open(path, "wb") as f:
            f.write(data)

    return path


def fetch_segment_videos(
    segments: list[dict],
    out_dir: str = IMAGES_DIR,
) -> list[str]:
    """Download one stock video clip per segment in parallel (MP4, HD preferred)."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_single_video, i, seg, out_dir): i
            for i, seg in enumerate(segments)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logger.error("Video fetch failed for segment %d: %s", idx, e)
                path = f"{out_dir}/vid_{idx:03d}.jpg"
                data = requests.get(_PICSUM_FALLBACK.format(seed=idx), timeout=_REQUEST_TIMEOUT).content
                with open(path, "wb") as f:
                    f.write(data)
                results[idx] = path

    paths = [results[i] for i in range(len(segments))]
    logger.info("Visual download complete: %d files written to %s", len(paths), out_dir)
    return paths
