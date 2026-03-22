"""youtube_uploader.py — YouTube Data API v3 uploader.

Single responsibility: authenticate and upload a video + thumbnail
to YouTube. Nothing else.
"""

import logging
import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from config import DEFAULT_VISIBILITY, YOUTUBE_CATEGORY_ID, YOUTUBE_CLIENT_SECRETS, YOUTUBE_SCOPES

logger = logging.getLogger(__name__)

_TOKEN_PATH = os.path.join(os.path.dirname(__file__), "token.json")


def _get_credentials() -> Credentials:
    """Load saved credentials from token.json, refreshing if needed.
    Falls back to browser OAuth flow if no token exists."""
    creds = None
    if os.path.exists(_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(_TOKEN_PATH, YOUTUBE_SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        logger.info("Refreshing expired YouTube token...")
        creds.refresh(Request())
        _save_token(creds)
        return creds

    # First-time or token missing — open browser
    logger.info("No valid token found — opening browser for YouTube OAuth...")
    flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CLIENT_SECRETS, YOUTUBE_SCOPES)
    creds = flow.run_local_server(port=0)
    _save_token(creds)
    return creds


def _save_token(creds: Credentials) -> None:
    with open(_TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    logger.info("Token saved to %s", _TOKEN_PATH)


def upload_video(
    video_path: str,
    thumbnail_path: str,
    content: dict,
) -> str:
    """Authenticate via OAuth and upload a video (+ optional thumbnail) to YouTube.

    Reuses saved token.json automatically — no browser popup on repeat runs.
    Thumbnail upload is skipped gracefully if the account lacks permission
    (requires channel verification / 1000+ subscribers).

    Args:
        video_path:      Path to the MP4 file.
        thumbnail_path:  Path to the JPEG thumbnail.
        content:         Script dict with keys: title, description, tags.

    Returns:
        The YouTube video ID (e.g. "dQw4w9WgXcQ").
    """
    logger.info("Authenticating with YouTube OAuth...")
    credentials = _get_credentials()
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
            },
            "status": {
                "privacyStatus": DEFAULT_VISIBILITY,
                "selfDeclaredMadeForKids": False,
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
