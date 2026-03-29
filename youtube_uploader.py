"""youtube_uploader.py — YouTube Data API v3 uploader.

Single responsibility: authenticate and upload a video + thumbnail
to YouTube. Supports multiple channels via named token files in tokens/.
"""

import json
import logging
import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from config import DEFAULT_VISIBILITY, YOUTUBE_CATEGORY_ID, YOUTUBE_CLIENT_SECRETS, YOUTUBE_SCOPES

# Scopes needed only for upload — narrower than YOUTUBE_SCOPES.
# Using the exact scopes the token was originally granted prevents
# 'invalid_scope' errors when refreshing old tokens.
_UPLOAD_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(__file__)
_TOKENS_DIR = os.path.join(_BASE_DIR, "tokens")
_LEGACY_TOKEN = os.path.join(_BASE_DIR, "token.json")
_CHANNELS_FILE = os.path.join(_TOKENS_DIR, "channels.json")


# ── Channel registry ──────────────────────────────────────────────────────────

def _ensure_tokens_dir() -> None:
    os.makedirs(_TOKENS_DIR, exist_ok=True)


def _load_channels() -> dict:
    """Load the channel registry. Returns {slug: {name, token_file, channel_id, is_default}}."""
    if os.path.exists(_CHANNELS_FILE):
        with open(_CHANNELS_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_channels(channels: dict) -> None:
    _ensure_tokens_dir()
    with open(_CHANNELS_FILE, "w") as f:
        json.dump(channels, f, indent=2, ensure_ascii=False)


def _migrate_legacy_token() -> None:
    """Auto-migrate legacy token.json → tokens/ on first run."""
    if not os.path.exists(_LEGACY_TOKEN):
        return
    channels = _load_channels()
    if channels:
        return  # Already has channels, don't auto-migrate

    import shutil
    _ensure_tokens_dir()
    dest = os.path.join(_TOKENS_DIR, "default.json")
    shutil.copy2(_LEGACY_TOKEN, dest)

    # Try to get channel info from the token
    channel_name = "Default Channel"
    channel_id = ""
    try:
        creds = Credentials.from_authorized_user_file(dest, _UPLOAD_SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(dest, "w") as f:
                f.write(creds.to_json())
        if creds and creds.valid:
            yt = build("youtube", "v3", credentials=creds)
            resp = yt.channels().list(part="snippet", mine=True).execute()
            items = resp.get("items", [])
            if items:
                channel_id = items[0]["id"]
                channel_name = items[0]["snippet"]["title"]
    except Exception as e:
        logger.warning("Could not fetch channel info during migration: %s", e)

    channels["default"] = {
        "name": channel_name,
        "token_file": "default.json",
        "channel_id": channel_id,
        "is_default": True,
    }
    _save_channels(channels)
    logger.info("Migrated legacy token.json → tokens/default.json (%s)", channel_name)


def list_channels() -> list[dict]:
    """Return all registered channels as a list of dicts."""
    _migrate_legacy_token()
    channels = _load_channels()
    result = []
    for slug, info in channels.items():
        result.append({
            "slug": slug,
            "name": info.get("name", slug),
            "handle": info.get("handle", ""),
            "channel_id": info.get("channel_id", ""),
            "is_default": info.get("is_default", False),
            "has_token": os.path.exists(os.path.join(_TOKENS_DIR, info.get("token_file", ""))),
        })
    return result


def get_default_channel() -> str | None:
    """Return the slug of the default channel, or None."""
    channels = _load_channels()
    for slug, info in channels.items():
        if info.get("is_default"):
            return slug
    # If only one channel, treat it as default
    if len(channels) == 1:
        return next(iter(channels))
    return None


def set_default_channel(slug: str) -> bool:
    """Set the specified channel as default."""
    channels = _load_channels()
    if slug not in channels:
        return False
    for s in channels:
        channels[s]["is_default"] = (s == slug)
    _save_channels(channels)
    return True


def add_channel(name: str) -> tuple[str, str]:
    """Register a new channel and run OAuth flow.
    Returns (slug, channel_id). Opens browser for auth."""
    slug = name.lower().replace(" ", "-").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")[:40]

    _ensure_tokens_dir()
    channels = _load_channels()

    token_file = f"{slug}.json"
    token_path = os.path.join(_TOKENS_DIR, token_file)

    # Run OAuth flow
    logger.info("Opening browser for YouTube OAuth — channel: %s", name)
    flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CLIENT_SECRETS, YOUTUBE_SCOPES)
    creds = flow.run_local_server(port=0)

    # Save token
    with open(token_path, "w") as f:
        f.write(creds.to_json())

    # Get channel ID + title from YouTube API
    channel_id = ""
    channel_title = name
    try:
        yt = build("youtube", "v3", credentials=creds)
        resp = yt.channels().list(part="snippet", mine=True).execute()
        items = resp.get("items", [])
        if items:
            channel_id = items[0]["id"]
            channel_title = items[0]["snippet"]["title"]
    except Exception as e:
        logger.warning("Could not fetch channel info (scope issue?): %s", e)

    # Register in channels.json
    is_first = len(channels) == 0
    channels[slug] = {
        "name": channel_title,
        "token_file": token_file,
        "channel_id": channel_id,
        "is_default": is_first,
    }
    _save_channels(channels)

    # Migrate legacy token.json if this is the first channel
    if is_first and os.path.exists(_LEGACY_TOKEN):
        logger.info("Migrating legacy token.json → tokens/%s", token_file)

    logger.info("Channel added: %s (%s) — default=%s", channel_title, channel_id, is_first)
    return slug, channel_id


def remove_channel(slug: str) -> bool:
    """Remove a channel from the registry and delete its token."""
    channels = _load_channels()
    if slug not in channels:
        return False
    info = channels.pop(slug)
    token_path = os.path.join(_TOKENS_DIR, info.get("token_file", ""))
    if os.path.exists(token_path):
        os.remove(token_path)
    # If removed channel was default, make the first remaining channel default
    if info.get("is_default") and channels:
        first = next(iter(channels))
        channels[first]["is_default"] = True
    _save_channels(channels)
    return True


def _get_token_path(channel_slug: str | None = None) -> str:
    """Resolve the token file path for a given channel slug."""
    channels = _load_channels()

    if channel_slug and channel_slug in channels:
        return os.path.join(_TOKENS_DIR, channels[channel_slug]["token_file"])

    # Try default channel
    for slug, info in channels.items():
        if info.get("is_default"):
            return os.path.join(_TOKENS_DIR, info["token_file"])

    # Single channel
    if len(channels) == 1:
        info = next(iter(channels.values()))
        return os.path.join(_TOKENS_DIR, info["token_file"])

    # Legacy fallback
    if os.path.exists(_LEGACY_TOKEN):
        return _LEGACY_TOKEN

    return os.path.join(_TOKENS_DIR, "default.json")


def _get_credentials(channel_slug: str | None = None) -> Credentials:
    """Load saved credentials for a channel, refreshing if needed.
    Falls back to browser OAuth flow if no token exists."""
    token_path = _get_token_path(channel_slug)
    creds = None
    if os.path.exists(token_path):
        # Load with only the upload scope so tokens originally created without
        # youtube.readonly can still refresh without invalid_scope errors.
        creds = Credentials.from_authorized_user_file(token_path, _UPLOAD_SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        logger.info("Refreshing expired YouTube token for channel...")
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        return creds

    # No valid token — need to add channel first
    raise RuntimeError(
        f"No valid token found at {token_path}. "
        "Add a channel first via Settings → YouTube Channels → Add Channel."
    )


def upload_video(
    video_path: str,
    thumbnail_path: str,
    content: dict,
    channel_slug: str | None = None,
) -> str:
    """Authenticate via OAuth and upload a video (+ optional thumbnail) to YouTube.

    Uses the token for the specified channel slug, or the default channel.
    Thumbnail upload is skipped gracefully if the account lacks permission
    (requires channel verification / 1000+ subscribers).

    Args:
        video_path:      Path to the MP4 file.
        thumbnail_path:  Path to the JPEG thumbnail.
        content:         Script dict with keys: title, description, tags.
        channel_slug:    Optional channel slug. Uses default if omitted.

    Returns:
        The YouTube video ID (e.g. "dQw4w9WgXcQ").
    """
    logger.info("Authenticating with YouTube OAuth (channel=%s)...", channel_slug or "default")
    credentials = _get_credentials(channel_slug)
    youtube = build("youtube", "v3", credentials=credentials)

    logger.info("Uploading video: %s", video_path)
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": content["title"],
                "description": content["description"],
                "tags": content["tags"],
                "categoryId": YOUTUBE_CATEGORY_ID,
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en",
            },
            "status": {
                "privacyStatus": DEFAULT_VISIBILITY,
                "selfDeclaredMadeForKids": False,
                "embeddable": True,
                "publicStatsViewable": True,
            },
        },
        media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True),
    )
    response = request.execute()
    video_id: str = response["id"]

    # Thumbnail upload — requires verified channel (1000+ subs)
    # Skip gracefully if permission denied
    try:
        logger.info("Uploading thumbnail: %s", thumbnail_path)
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path),
        ).execute()
        logger.info("Thumbnail uploaded successfully")
    except HttpError as e:
        if e.resp.status == 403:
            logger.warning(
                "Thumbnail upload skipped — account not yet verified for custom thumbnails "
                "(need 1000+ subscribers or channel verification). Video still uploaded OK."
            )
        else:
            raise

    logger.info("Published: https://youtube.com/watch?v=%s", video_id)
    return video_id


def pin_first_comment(
    video_id: str,
    comment_text: str,
    channel_slug: str | None = None,
) -> str | None:
    """Post a comment on a video and pin it as the top comment.

    Requires the youtube scope (not just youtube.upload).
    Fails gracefully — a pinning error never blocks the pipeline.

    Args:
        video_id:     YouTube video ID (e.g. "dQw4w9WgXcQ").
        comment_text: Text of the comment to post and pin.
        channel_slug: Channel slug; uses default if omitted.

    Returns:
        The comment ID on success, None on failure.
    """
    try:
        token_path = _get_token_path(channel_slug)
        creds = Credentials.from_authorized_user_file(
            token_path,
            ["https://www.googleapis.com/auth/youtube"],
        )
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        youtube = build("youtube", "v3", credentials=creds)

        # Insert the top-level comment
        comment_resp = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": comment_text}
                    },
                }
            },
        ).execute()

        comment_id = comment_resp["id"]
        logger.info("Comment posted: %s", comment_id)

        # Pin it
        youtube.comments().setModerationStatus(
            id=comment_id,
            moderationStatus="published",
            banAuthor=False,
        ).execute()

        logger.info("Comment pinned on video %s", video_id)
        return comment_id

    except HttpError as e:
        logger.warning(
            "Pin comment failed (video=%s, status=%s) — continuing: %s",
            video_id, e.resp.status, e,
        )
        return None
    except Exception as e:
        logger.warning("Pin comment failed (video=%s) — continuing: %s", video_id, e)
        return None
