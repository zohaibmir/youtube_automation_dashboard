"""Fetch and analyze YouTube channel details for SEO optimization.

Usage:
    python scripts/channel_audit.py [--channel <slug>]
"""
import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from youtube_uploader import _get_token_path

# Need readonly scope to read channel details
_READ_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
]


def _get_read_credentials(channel_slug=None):
    """Load credentials with readonly scope for reading channel data."""
    token_path = _get_token_path(channel_slug)
    if not os.path.exists(token_path):
        raise RuntimeError(f"No token found at {token_path}")
    creds = Credentials.from_authorized_user_file(token_path, _READ_SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def fetch_channel_details(channel_slug=None):
    """Fetch full channel details from YouTube API."""
    creds = _get_read_credentials(channel_slug)
    yt = build("youtube", "v3", credentials=creds)

    resp = yt.channels().list(
        part="snippet,brandingSettings,statistics,status,contentDetails,topicDetails",
        mine=True,
    ).execute()

    if not resp.get("items"):
        print("Error: No channel found for this token.")
        sys.exit(1)

    return resp["items"][0]


def fetch_recent_videos(channel_id, creds, max_results=10):
    """Fetch recent videos for analysis."""
    yt = build("youtube", "v3", credentials=creds)

    search_resp = yt.search().list(
        part="snippet",
        channelId=channel_id,
        order="date",
        maxResults=max_results,
        type="video",
    ).execute()

    video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
    if not video_ids:
        return []

    videos_resp = yt.videos().list(
        part="snippet,statistics,contentDetails",
        id=",".join(video_ids),
    ).execute()

    return videos_resp.get("items", [])


def analyze_channel(channel, videos):
    """Produce SEO audit report."""
    snippet = channel.get("snippet", {})
    branding = channel.get("brandingSettings", {})
    stats = channel.get("statistics", {})
    topics = channel.get("topicDetails", {})

    ch_title = snippet.get("title", "N/A")
    ch_desc = snippet.get("description", "")
    ch_keywords_raw = branding.get("channel", {}).get("keywords", "")
    ch_country = snippet.get("country", "Not set")
    ch_custom_url = snippet.get("customUrl", "Not set")
    subs = int(stats.get("subscriberCount", 0))
    views = int(stats.get("viewCount", 0))
    video_count = int(stats.get("videoCount", 0))

    print("=" * 70)
    print(f"  CHANNEL SEO AUDIT: {ch_title}")
    print("=" * 70)

    # ── Basic Stats ──
    print(f"\n📊 CHANNEL STATS")
    print(f"  Subscribers:  {subs:,}")
    print(f"  Total views:  {views:,}")
    print(f"  Video count:  {video_count}")
    print(f"  Custom URL:   {ch_custom_url}")
    print(f"  Country:      {ch_country}")

    # ── Description Analysis ──
    print(f"\n📝 DESCRIPTION ({len(ch_desc)} chars)")
    if ch_desc:
        print(f"  Current: {ch_desc[:200]}{'...' if len(ch_desc) > 200 else ''}")
    else:
        print("  ⚠️  EMPTY — this is critical for discoverability!")

    issues = []
    if len(ch_desc) < 100:
        issues.append("Description too short (< 100 chars). Aim for 300-1000 chars.")
    if len(ch_desc) > 1000:
        issues.append("Description is very long. First 150 chars appear in search — front-load keywords.")
    if ch_desc and not any(c in ch_desc for c in ["http://", "https://"]):
        issues.append("No links in description. Add social media / website links.")
    if not ch_desc:
        issues.append("CRITICAL: No channel description at all!")

    # ── Keywords Analysis ──
    print(f"\n🔑 CHANNEL KEYWORDS")
    if ch_keywords_raw:
        # Keywords can be space-separated or quoted phrases
        print(f"  Raw: {ch_keywords_raw[:200]}")
    else:
        print("  ⚠️  NO KEYWORDS SET — major SEO miss!")
        issues.append("CRITICAL: No channel keywords. Add 5-15 relevant keywords.")

    # ── Country ──
    if ch_country == "Not set":
        issues.append("Country not set. Set it to target local search results.")

    # ── Thumbnail/Banner ──
    banner = branding.get("image", {}).get("bannerExternalUrl")
    if not banner:
        issues.append("No custom banner image. Add a branded banner (2560×1440 recommended).")

    thumb = snippet.get("thumbnails", {}).get("high", {}).get("url", "")
    if not thumb or "default" in thumb:
        issues.append("Using default profile picture. Upload a branded avatar.")

    # ── Topic Categories ──
    topic_cats = topics.get("topicCategories", [])
    if topic_cats:
        print(f"\n🏷️  TOPIC CATEGORIES")
        for tc in topic_cats:
            print(f"  - {tc.split('/')[-1]}")

    # ── Video Analysis ──
    if videos:
        print(f"\n🎬 RECENT VIDEOS ({len(videos)} analyzed)")
        total_views = 0
        no_tags = 0
        short_titles = 0
        short_descs = 0

        for v in videos:
            vs = v.get("snippet", {})
            vstat = v.get("statistics", {})
            title = vs.get("title", "")
            desc = vs.get("description", "")
            tags = vs.get("tags", [])
            vviews = int(vstat.get("viewCount", 0))
            total_views += vviews

            print(f"  • {title[:60]}")
            print(f"    Views: {vviews:,} | Tags: {len(tags)} | Desc: {len(desc)} chars")

            if len(title) < 30:
                short_titles += 1
            if len(desc) < 100:
                short_descs += 1
            if not tags:
                no_tags += 1

        avg_views = total_views // len(videos) if videos else 0
        print(f"\n  Avg views/video: {avg_views:,}")

        if no_tags > 0:
            issues.append(f"{no_tags}/{len(videos)} videos have NO tags. Add 8-15 relevant tags per video.")
        if short_titles > 0:
            issues.append(f"{short_titles}/{len(videos)} videos have short titles (< 30 chars). Aim for 50-70 chars.")
        if short_descs > 0:
            issues.append(f"{short_descs}/{len(videos)} videos have short descriptions. Aim for 200+ chars with keywords.")

    # ── Issues Summary ──
    print(f"\n{'=' * 70}")
    print(f"  ⚠️  ISSUES FOUND: {len(issues)}")
    print(f"{'=' * 70}")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")

    # ── Recommendations ──
    print(f"\n{'=' * 70}")
    print(f"  💡 RECOMMENDATIONS")
    print(f"{'=' * 70}")

    recs = [
        "Write a keyword-rich channel description (300-1000 chars) with your niche, upload schedule, and value proposition.",
        "Add 10-15 channel keywords matching your niche topics.",
        "Set channel country to improve local search visibility.",
        "Create a channel trailer for non-subscribers.",
        "Use consistent branding: banner (2560×1440), avatar, watermark.",
        "Add end screens + cards to every video to boost watch time.",
        "Create playlists grouping related videos — playlists rank in search.",
        "Use 8-15 tags per video mixing broad + specific keywords.",
        "Write video descriptions 200+ chars with target keywords in first 2 lines.",
        "Post consistently — YouTube rewards regular upload schedules.",
        "Engage with comments in first 24h to boost algorithmic ranking.",
        "Use YouTube Shorts to drive subscribers to long-form content.",
    ]
    for i, r in enumerate(recs, 1):
        print(f"  {i:2d}. {r}")

    return {
        "channel_id": channel.get("id"),
        "title": ch_title,
        "description": ch_desc,
        "keywords": ch_keywords_raw,
        "country": ch_country,
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(description="Audit YouTube channel SEO")
    parser.add_argument("--channel", default=None, help="Channel slug")
    parser.add_argument("--json", action="store_true", help="Output raw JSON data")
    args = parser.parse_args()

    channel = fetch_channel_details(args.channel)
    creds = _get_read_credentials(args.channel)
    videos = fetch_recent_videos(channel["id"], creds)

    if args.json:
        print(json.dumps({"channel": channel, "videos": videos}, indent=2))
    else:
        analyze_channel(channel, videos)


if __name__ == "__main__":
    main()
