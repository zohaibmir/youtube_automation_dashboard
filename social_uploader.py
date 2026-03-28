"""social_uploader.py — Multi-platform video uploader for Shorts/Reels.

Supports: Instagram Reels, Facebook Reels, TikTok.
Each platform has its own OAuth token and upload flow.
Tokens are stored in tokens/<platform>.json alongside YouTube tokens.
"""

import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(__file__)
_TOKENS_DIR = os.path.join(_BASE_DIR, "tokens")
_PLATFORMS_FILE = os.path.join(_TOKENS_DIR, "social_platforms.json")


# ── Platform registry ─────────────────────────────────────────────────────────

def _ensure_tokens_dir() -> None:
    os.makedirs(_TOKENS_DIR, exist_ok=True)


def _load_platforms() -> dict:
    """Load platform config. Returns {platform: {enabled, access_token, ...}}."""
    if os.path.exists(_PLATFORMS_FILE):
        with open(_PLATFORMS_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_platforms(platforms: dict) -> None:
    _ensure_tokens_dir()
    with open(_PLATFORMS_FILE, "w") as f:
        json.dump(platforms, f, indent=2, ensure_ascii=False)


def list_platforms() -> list[dict]:
    """Return all configured social platforms with their status."""
    platforms = _load_platforms()
    result = []
    for name in ["instagram", "facebook", "tiktok"]:
        info = platforms.get(name, {})
        result.append({
            "platform": name,
            "enabled": info.get("enabled", False),
            "connected": bool(info.get("access_token")),
            "account_name": info.get("account_name", ""),
            "stories_enabled": info.get("stories_enabled", False),
        })
    return result


def save_platform_config(platform: str, config: dict) -> None:
    """Save or update a platform's configuration."""
    platforms = _load_platforms()
    existing = platforms.get(platform, {})
    existing.update(config)
    platforms[platform] = existing
    _save_platforms(platforms)


def remove_platform(platform: str) -> bool:
    """Remove a platform's configuration and token."""
    platforms = _load_platforms()
    if platform not in platforms:
        return False
    del platforms[platform]
    _save_platforms(platforms)
    return True


# ── Instagram Reels (Meta Graph API) ─────────────────────────────────────────
# Setup:
#   1. Create a Meta Developer App at https://developers.facebook.com
#   2. Add Instagram Graph API product
#   3. Link Instagram Professional account to a Facebook Page
#   4. Generate long-lived access token with:
#      - instagram_basic, instagram_content_publish, pages_show_list
#   5. Enter token + IG User ID in dashboard Settings → Social Platforms
#
# Upload flow:
#   POST /{ig-user-id}/media → create container (upload phase)
#   GET /{container-id}?fields=status_code → poll until FINISHED
#   POST /{ig-user-id}/media_publish → publish the container

_META_GRAPH_URL = "https://graph.facebook.com/v21.0"


def _ig_create_container(video_path: str, caption: str, token: str,
                         ig_user_id: str) -> str:
    """Create an Instagram media container for a Reel via direct video upload."""
    url = f"{_META_GRAPH_URL}/{ig_user_id}/media"

    file_size = os.path.getsize(video_path)

    # Step 1: Initialize resumable upload
    init_resp = requests.post(url, params={
        "media_type": "REELS",
        "caption": caption[:2200],
        "upload_type": "resumable",
        "access_token": token,
    }, timeout=30)
    init_resp.raise_for_status()
    container_id = init_resp.json()["id"]
    upload_url = init_resp.json().get("uri")

    if upload_url:
        # Step 2: Upload video binary via resumable upload
        with open(video_path, "rb") as f:
            headers = {
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(file_size),
            }
            upload_resp = requests.post(upload_url, headers=headers,
                                        data=f, timeout=300)
            upload_resp.raise_for_status()
    else:
        # Fallback: non-resumable (requires public video_url — not supported locally)
        raise RuntimeError(
            "Instagram API did not return a resumable upload URI. "
            "Ensure your app has instagram_content_publish permission."
        )

    return container_id


def _ig_wait_for_processing(container_id: str, token: str,
                            max_wait: int = 120) -> str:
    """Poll container status until FINISHED or error."""
    url = f"{_META_GRAPH_URL}/{container_id}"
    start = time.time()
    while time.time() - start < max_wait:
        resp = requests.get(url, params={
            "fields": "status_code",
            "access_token": token,
        }, timeout=15)
        resp.raise_for_status()
        status = resp.json().get("status_code")
        if status == "FINISHED":
            return status
        if status == "ERROR":
            raise RuntimeError(f"Instagram container {container_id} failed processing")
        time.sleep(5)
    raise TimeoutError(f"Instagram processing timed out after {max_wait}s")


def _ig_publish(container_id: str, token: str, ig_user_id: str) -> str:
    """Publish a processed media container."""
    url = f"{_META_GRAPH_URL}/{ig_user_id}/media_publish"
    resp = requests.post(url, params={
        "creation_id": container_id,
        "access_token": token,
    }, timeout=30)
    resp.raise_for_status()
    media_id = resp.json()["id"]
    logger.info("Instagram Reel published: media_id=%s", media_id)
    return media_id


def upload_instagram_reel(video_path: str, caption: str) -> str:
    """Upload a Reel to Instagram. Returns the media ID."""
    platforms = _load_platforms()
    ig = platforms.get("instagram", {})
    token = ig.get("access_token")
    ig_user_id = ig.get("user_id")
    if not token or not ig_user_id:
        raise RuntimeError(
            "Instagram not configured. Go to Settings → Social Platforms → Instagram "
            "and enter your access token + IG User ID."
        )

    logger.info("Uploading Reel to Instagram (user=%s)…", ig_user_id)
    container_id = _ig_create_container(video_path, caption, token, ig_user_id)
    _ig_wait_for_processing(container_id, token)
    media_id = _ig_publish(container_id, token, ig_user_id)
    return media_id


def upload_instagram_story(video_path: str, caption: str = "") -> str:
    """Upload a Story to Instagram. Returns the media ID.

    Uses the same Graph API as Reels but with media_type=STORIES.
    Stories disappear after 24hrs. Max 60s video.
    Same token permissions as Reels (instagram_content_publish).
    """
    platforms = _load_platforms()
    ig = platforms.get("instagram", {})
    token = ig.get("access_token")
    ig_user_id = ig.get("user_id")
    if not token or not ig_user_id:
        raise RuntimeError(
            "Instagram not configured. Go to Settings → Social Platforms → Instagram "
            "and enter your access token + IG User ID."
        )

    logger.info("Uploading Story to Instagram (user=%s)…", ig_user_id)

    # Create STORIES container via resumable upload
    url = f"{_META_GRAPH_URL}/{ig_user_id}/media"
    file_size = os.path.getsize(video_path)

    init_resp = requests.post(url, params={
        "media_type": "STORIES",
        "upload_type": "resumable",
        "access_token": token,
    }, timeout=30)
    init_resp.raise_for_status()
    container_id = init_resp.json()["id"]
    upload_url = init_resp.json().get("uri")

    if not upload_url:
        raise RuntimeError("Instagram API did not return a resumable upload URI for Stories.")

    with open(video_path, "rb") as f:
        headers = {
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(file_size),
        }
        upload_resp = requests.post(upload_url, headers=headers, data=f, timeout=300)
        upload_resp.raise_for_status()

    _ig_wait_for_processing(container_id, token)
    media_id = _ig_publish(container_id, token, ig_user_id)
    logger.info("Instagram Story published: media_id=%s", media_id)
    return media_id


# ── Facebook Reels (Pages API) ───────────────────────────────────────────────
# Setup:
#   1. Same Meta Developer App as Instagram
#   2. Get a Page Access Token with pages_manage_posts, pages_read_engagement
#   3. Enter Page ID + Page Access Token in dashboard Settings
#
# Upload flow:
#   POST /{page-id}/video_reels?upload_phase=start → get video_id + upload_url
#   PUT upload_url → upload binary
#   POST /{page-id}/video_reels?upload_phase=finish → publish

def upload_facebook_reel(video_path: str, title: str, description: str) -> str:
    """Upload a Reel to a Facebook Page. Returns the video ID."""
    platforms = _load_platforms()
    fb = platforms.get("facebook", {})
    token = fb.get("access_token")
    page_id = fb.get("page_id")
    if not token or not page_id:
        raise RuntimeError(
            "Facebook not configured. Go to Settings → Social Platforms → Facebook "
            "and enter your Page Access Token + Page ID."
        )

    logger.info("Uploading Reel to Facebook Page (page=%s)…", page_id)

    # Step 1: Start upload
    start_resp = requests.post(
        f"{_META_GRAPH_URL}/{page_id}/video_reels",
        params={"upload_phase": "start", "access_token": token},
        timeout=30,
    )
    start_resp.raise_for_status()
    data = start_resp.json()
    video_id = data["video_id"]
    upload_url = data["upload_url"]

    # Step 2: Upload binary
    file_size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(file_size),
            },
            data=f,
            timeout=300,
        )
        upload_resp.raise_for_status()

    # Step 3: Finish + publish
    finish_resp = requests.post(
        f"{_META_GRAPH_URL}/{page_id}/video_reels",
        params={
            "upload_phase": "finish",
            "video_id": video_id,
            "title": title[:255],
            "description": description[:2000],
            "access_token": token,
        },
        timeout=30,
    )
    finish_resp.raise_for_status()
    result = finish_resp.json()
    logger.info("Facebook Reel published: video_id=%s", video_id)
    return result.get("video_id", video_id)


def upload_facebook_story(video_path: str) -> str:
    """Upload a Story to a Facebook Page. Returns the post ID.

    Uses the Pages Photo/Video Stories API.
    Stories disappear after 24hrs. Max 120s video.
    Same Page token as Reels (pages_manage_posts).
    """
    platforms = _load_platforms()
    fb = platforms.get("facebook", {})
    token = fb.get("access_token")
    page_id = fb.get("page_id")
    if not token or not page_id:
        raise RuntimeError(
            "Facebook not configured. Go to Settings → Social Platforms → Facebook "
            "and enter your Page Access Token + Page ID."
        )

    logger.info("Uploading Story to Facebook Page (page=%s)…", page_id)

    # Upload video story via multipart form
    url = f"{_META_GRAPH_URL}/{page_id}/video_stories"
    with open(video_path, "rb") as f:
        resp = requests.post(
            url,
            files={"source": (os.path.basename(video_path), f, "video/mp4")},
            data={"upload_phase": "start", "access_token": token},
            timeout=300,
        )
    resp.raise_for_status()
    post_id = resp.json().get("id", "")
    logger.info("Facebook Story published: post_id=%s", post_id)
    return post_id


# ── TikTok (Content Posting API v2) ──────────────────────────────────────────
# Setup:
#   1. Create TikTok Developer App at https://developers.tiktok.com
#   2. Apply for video.publish scope
#   3. Run OAuth flow to get access token
#   4. Enter Client Key, Client Secret, and Access Token in dashboard Settings
#
# Upload flow:
#   POST /v2/post/publish/video/init/ → get publish_id + upload_url
#   PUT upload_url → upload binary chunks
#   Video enters TikTok review pipeline automatically

_TIKTOK_API_URL = "https://open.tiktokapis.com"


def _tiktok_refresh_token(tt_config: dict) -> str | None:
    """Refresh TikTok access token if refresh_token is available."""
    refresh_token = tt_config.get("refresh_token")
    client_key = tt_config.get("client_key")
    client_secret = tt_config.get("client_secret")
    if not all([refresh_token, client_key, client_secret]):
        return None

    resp = requests.post(f"{_TIKTOK_API_URL}/v2/oauth/token/", json={
        "client_key": client_key,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        new_token = data.get("access_token")
        new_refresh = data.get("refresh_token")
        if new_token:
            platforms = _load_platforms()
            platforms["tiktok"]["access_token"] = new_token
            if new_refresh:
                platforms["tiktok"]["refresh_token"] = new_refresh
            _save_platforms(platforms)
            logger.info("TikTok token refreshed")
            return new_token
    return None


def upload_tiktok_video(video_path: str, title: str) -> str:
    """Upload a video to TikTok. Returns the publish_id."""
    platforms = _load_platforms()
    tt = platforms.get("tiktok", {})
    token = tt.get("access_token")
    if not token:
        raise RuntimeError(
            "TikTok not configured. Go to Settings → Social Platforms → TikTok "
            "and enter your access token."
        )

    file_size = os.path.getsize(video_path)
    logger.info("Uploading video to TikTok (%d bytes)…", file_size)

    # Step 1: Initialize upload
    init_resp = requests.post(
        f"{_TIKTOK_API_URL}/v2/post/publish/video/init/",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8"},
        json={
            "post_info": {
                "title": title[:150],
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_comment": False,
                "disable_duet": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,  # single chunk upload
                "total_chunk_count": 1,
            },
        },
        timeout=30,
    )

    if init_resp.status_code == 401:
        # Try token refresh
        new_token = _tiktok_refresh_token(tt)
        if new_token:
            token = new_token
            init_resp = requests.post(
                f"{_TIKTOK_API_URL}/v2/post/publish/video/init/",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json; charset=UTF-8"},
                json={
                    "post_info": {
                        "title": title[:150],
                        "privacy_level": "PUBLIC_TO_EVERYONE",
                        "disable_comment": False,
                        "disable_duet": False,
                        "disable_stitch": False,
                    },
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": file_size,
                        "chunk_size": file_size,
                        "total_chunk_count": 1,
                    },
                },
                timeout=30,
            )

    init_resp.raise_for_status()
    init_data = init_resp.json().get("data", {})
    publish_id = init_data.get("publish_id")
    upload_url = init_data.get("upload_url")

    if not upload_url:
        error = init_resp.json().get("error", {})
        raise RuntimeError(f"TikTok init failed: {error}")

    # Step 2: Upload video binary
    with open(video_path, "rb") as f:
        chunk_data = f.read()
        upload_resp = requests.put(
            upload_url,
            headers={
                "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
                "Content-Type": "video/mp4",
            },
            data=chunk_data,
            timeout=300,
        )
        upload_resp.raise_for_status()

    logger.info("TikTok video uploaded: publish_id=%s (enters review pipeline)", publish_id)
    return publish_id


# ── Unified multi-platform upload ─────────────────────────────────────────────

def upload_to_platforms(
    video_path: str,
    title: str,
    description: str,
    caption: str | None = None,
    platforms_list: list[str] | None = None,
) -> dict[str, dict]:
    """Upload a video to all enabled social platforms.

    Args:
        video_path:      Path to the MP4 file (vertical 1080×1920).
        title:           Video title.
        description:     Video description.
        caption:         Caption text (used for Instagram). Falls back to title.
        platforms_list:  Specific platforms to upload to. None = all enabled.
                         Supports: instagram, facebook, tiktok,
                                   instagram_story, facebook_story

    Returns:
        Dict of {platform: {"ok": bool, "id": str, "error": str}}.
    """
    all_platforms = _load_platforms()
    results = {}

    # Build default target list
    if platforms_list is not None:
        targets = platforms_list
    else:
        targets = []
        for p, cfg in all_platforms.items():
            if cfg.get("enabled") and cfg.get("access_token"):
                targets.append(p)
            if cfg.get("stories_enabled") and cfg.get("access_token"):
                if p in ("instagram", "facebook"):
                    targets.append(f"{p}_story")

    ig_caption = caption or f"{title}\n\n{description}"

    for platform in targets:
        base_platform = platform.replace("_story", "")
        cfg = all_platforms.get(base_platform, {})
        if not cfg.get("access_token"):
            results[platform] = {"ok": False, "error": "Not configured (no access token)"}
            continue

        try:
            if platform == "instagram":
                media_id = upload_instagram_reel(video_path, ig_caption)
                results["instagram"] = {"ok": True, "id": media_id}

            elif platform == "instagram_story":
                media_id = upload_instagram_story(video_path, ig_caption)
                results["instagram_story"] = {"ok": True, "id": media_id}

            elif platform == "facebook":
                video_id = upload_facebook_reel(video_path, title, description)
                results["facebook"] = {"ok": True, "id": video_id}

            elif platform == "facebook_story":
                post_id = upload_facebook_story(video_path)
                results["facebook_story"] = {"ok": True, "id": post_id}

            elif platform == "tiktok":
                pub_id = upload_tiktok_video(video_path, title)
                results["tiktok"] = {"ok": True, "id": pub_id}

            else:
                results[platform] = {"ok": False, "error": f"Unknown platform: {platform}"}

        except Exception as e:
            logger.error("Upload to %s failed: %s", platform, e)
            results[platform] = {"ok": False, "error": str(e)}

    return results


# ── TikTok OAuth helper (browser-based flow) ─────────────────────────────────

def get_tiktok_auth_url(client_key: str, redirect_uri: str = "http://localhost:8080/auth/tiktok/callback") -> str:
    """Generate TikTok OAuth authorization URL for the user to visit."""
    params = {
        "client_key": client_key,
        "scope": "user.info.basic,video.publish",
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": "tiktok_auth",
    }
    return f"https://www.tiktok.com/v2/auth/authorize/?{urlencode(params)}"


def exchange_tiktok_code(code: str, client_key: str, client_secret: str,
                         redirect_uri: str = "http://localhost:8080/auth/tiktok/callback") -> dict:
    """Exchange TikTok auth code for access + refresh tokens."""
    resp = requests.post(f"{_TIKTOK_API_URL}/v2/oauth/token/", json={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return {
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "open_id": data.get("open_id"),
        "expires_in": data.get("expires_in"),
    }
