"""channel_manager.py — Channel-level SEO audit and management.

Single responsibility: audit all videos on a channel, return structured
health data, and perform channel-level updates (description, keywords, etc.)
via the YouTube Data API.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _get_yt(channel_slug: str | None = None):
    """Get authenticated YouTube service for a channel."""
    from youtube_uploader import _get_credentials
    from googleapiclient.discovery import build
    creds = _get_credentials(channel_slug)
    return build("youtube", "v3", credentials=creds)


# ── Video Audit ──────────────────────────────────────────────────────────

def audit_channel(channel_slug: str | None = None) -> dict:
    """Full audit of all videos + channel settings. Returns structured data."""
    yt = _get_yt(channel_slug)

    # Get channel info
    ch_resp = yt.channels().list(
        part="snippet,brandingSettings,statistics,contentDetails", mine=True,
    ).execute()
    if not ch_resp.get("items"):
        return {"ok": False, "error": "No channel found for this account."}

    ch = ch_resp["items"][0]
    ch_snippet = ch["snippet"]
    ch_branding = ch.get("brandingSettings", {}).get("channel", {})
    ch_stats = ch.get("statistics", {})

    channel_info = {
        "id": ch["id"],
        "title": ch_snippet.get("title", ""),
        "description": ch_branding.get("description", ""),
        "description_len": len(ch_branding.get("description", "")),
        "keywords": ch_branding.get("keywords", ""),
        "country": ch_branding.get("country", ""),
        "default_language": ch_branding.get("defaultLanguage", ""),
        "subscriber_count": int(ch_stats.get("subscriberCount", 0)),
        "video_count": int(ch_stats.get("videoCount", 0)),
        "view_count": int(ch_stats.get("viewCount", 0)),
        "trailer": ch_branding.get("unsubscribedTrailer", ""),
        "banner_url": ch.get("brandingSettings", {}).get("image", {}).get("bannerExternalUrl", ""),
    }

    # Get all videos
    search = yt.search().list(
        part="snippet", channelId=ch["id"],
        type="video", maxResults=50, order="date",
    ).execute()
    video_ids = [i["id"]["videoId"] for i in search.get("items", [])]

    videos = []
    issues_count = 0
    if video_ids:
        vids = yt.videos().list(
            part="snippet,status,statistics,contentDetails",
            id=",".join(video_ids),
        ).execute()

        for v in vids.get("items", []):
            s = v["snippet"]
            st = v["status"]
            stats = v["statistics"]
            tags = s.get("tags", [])

            vid_issues = []
            if st["privacyStatus"] != "public":
                vid_issues.append("Not public")
            if len(tags) < 8:
                vid_issues.append(f"Only {len(tags)} tags")
            if len(s.get("description", "")) < 200:
                vid_issues.append("Short description")
            if not s.get("defaultLanguage"):
                vid_issues.append("No language set")
            if s.get("categoryId") not in ("25", "27", "28"):
                vid_issues.append(f"Category {s.get('categoryId')}")

            if vid_issues:
                issues_count += 1

            videos.append({
                "id": v["id"],
                "title": s["title"],
                "status": st["privacyStatus"],
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "tags_count": len(tags),
                "desc_len": len(s.get("description", "")),
                "category": s.get("categoryId", ""),
                "language": s.get("defaultLanguage", ""),
                "published": s.get("publishedAt", ""),
                "is_short": "#Shorts" in s.get("title", "") or "#shorts" in s.get("title", ""),
                "issues": vid_issues,
            })

    # Channel-level issues
    ch_issues = []
    if not ch_branding.get("description") or len(ch_branding.get("description", "")) < 100:
        ch_issues.append("Channel description missing or too short")
    if not ch_branding.get("keywords"):
        ch_issues.append("No channel keywords")
    if not ch_branding.get("country"):
        ch_issues.append("No country set")
    if not channel_info["banner_url"]:
        ch_issues.append("No banner uploaded")
    if not ch_branding.get("unsubscribedTrailer"):
        ch_issues.append("No channel trailer set")

    # Playlists
    pl_resp = yt.playlists().list(
        part="snippet,contentDetails", channelId=ch["id"], maxResults=50,
    ).execute()
    playlists = [{
        "id": p["id"],
        "title": p["snippet"]["title"],
        "count": p["contentDetails"]["itemCount"],
    } for p in pl_resp.get("items", [])]

    return {
        "ok": True,
        "channel": channel_info,
        "channel_issues": ch_issues,
        "videos": videos,
        "video_issues_count": issues_count,
        "playlists": playlists,
        "total_videos": len(videos),
        "score": _calculate_score(channel_info, ch_issues, videos, issues_count, playlists),
    }


def _calculate_score(ch: dict, ch_issues: list, videos: list, vid_issues: int, playlists: list) -> int:
    """Simple 0-100 channel health score."""
    score = 100
    score -= len(ch_issues) * 10  # -10 per channel issue
    if videos:
        issue_pct = vid_issues / len(videos)
        score -= int(issue_pct * 30)  # up to -30 for video issues
    if not playlists:
        score -= 5
    if ch["description_len"] < 300:
        score -= 5
    return max(0, min(100, score))


# ── Channel Updates ──────────────────────────────────────────────────────

def update_channel_info(
    description: str | None = None,
    keywords: str | None = None,
    country: str | None = None,
    language: str | None = None,
    trailer_video_id: str | None = None,
    channel_slug: str | None = None,
) -> dict:
    """Update channel branding settings."""
    yt = _get_yt(channel_slug)

    try:
        ch_resp = yt.channels().list(part="brandingSettings", mine=True).execute()
        if not ch_resp.get("items"):
            return {"ok": False, "error": "No channel found."}

        channel = ch_resp["items"][0]
        ch_settings = channel["brandingSettings"]["channel"]

        if description is not None:
            ch_settings["description"] = description
        if keywords is not None:
            ch_settings["keywords"] = keywords
        if country is not None:
            ch_settings["country"] = country
        if language is not None:
            ch_settings["defaultLanguage"] = language
        if trailer_video_id is not None:
            ch_settings["unsubscribedTrailer"] = trailer_video_id

        yt.channels().update(part="brandingSettings", body=channel).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fix_video(video_id: str, channel_slug: str | None = None) -> dict:
    """Fix a single video's SEO: set public, embeddable, category 25, language en."""
    yt = _get_yt(channel_slug)
    try:
        v = yt.videos().list(part="snippet,status", id=video_id).execute()
        if not v.get("items"):
            return {"ok": False, "error": "Video not found."}

        vid = v["items"][0]
        s = vid["snippet"]
        resp = yt.videos().update(
            part="snippet,status",
            body={
                "id": video_id,
                "snippet": {
                    "title": s["title"],
                    "description": s.get("description", ""),
                    "tags": s.get("tags", []),
                    "categoryId": "25",
                    "defaultLanguage": "en",
                    "defaultAudioLanguage": "en",
                },
                "status": {
                    "privacyStatus": "public",
                    "embeddable": True,
                    "publicStatsViewable": True,
                    "selfDeclaredMadeForKids": False,
                },
            },
        ).execute()
        return {"ok": True, "tags": len(resp["snippet"].get("tags", []))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fix_all_videos(channel_slug: str | None = None) -> dict:
    """Fix all videos on the channel."""
    audit = audit_channel(channel_slug)
    if not audit.get("ok"):
        return audit

    fixed = 0
    errors = []
    for v in audit["videos"]:
        if v["issues"]:
            result = fix_video(v["id"], channel_slug)
            if result["ok"]:
                fixed += 1
            else:
                errors.append(f"{v['id']}: {result['error']}")

    return {"ok": True, "fixed": fixed, "total": len(audit["videos"]), "errors": errors}
