"""Deep SEO fix script — audit + fix all videos on the channel.

1. Set all videos to PUBLIC
2. Update video descriptions with SEO keywords
3. Add/optimize tags on all videos
4. Set proper language + category
5. Update channel upload defaults
6. Create playlist
"""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TOKEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tokens", "truth-that-never-shared.json")
CHANNEL_ID = "UCKCSOyMYHVdA92mXJQ3K3Qw"


def get_yt():
    creds = Credentials.from_authorized_user_file(TOKEN)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def audit_videos(yt):
    """Fetch and display all video details."""
    resp = yt.search().list(
        part="snippet", channelId=CHANNEL_ID,
        type="video", maxResults=50, order="date",
    ).execute()
    video_ids = [i["id"]["videoId"] for i in resp.get("items", [])]
    if not video_ids:
        print("No videos found!")
        return []

    vids = yt.videos().list(
        part="snippet,status,statistics,contentDetails",
        id=",".join(video_ids),
    ).execute()

    print(f"\n{'='*70}")
    print(f"  DEEP SEO AUDIT — {len(vids['items'])} videos")
    print(f"{'='*70}")

    for v in vids["items"]:
        s = v["snippet"]
        st = v["status"]
        stats = v["statistics"]
        tags = s.get("tags", [])
        desc = s.get("description", "")

        issues = []
        if st["privacyStatus"] != "public":
            issues.append(f"PRIVATE ({st['privacyStatus']})")
        if not st.get("embeddable", True):
            issues.append("Not embeddable")
        if not st.get("publicStatsViewable", True):
            issues.append("Stats hidden")
        if len(tags) < 8:
            issues.append(f"Only {len(tags)} tags (need 8-15)")
        if len(desc) < 200:
            issues.append(f"Short description ({len(desc)} chars)")
        if not s.get("defaultLanguage"):
            issues.append("No default language set")
        if not s.get("defaultAudioLanguage"):
            issues.append("No audio language set")
        if s.get("categoryId") != "25":  # News & Politics
            issues.append(f"Category {s.get('categoryId')} (should be 25=News/Politics)")

        status_icon = "PUBLIC" if st["privacyStatus"] == "public" else "PRIVATE"
        print(f"\n  [{status_icon}] {s['title'][:65]}")
        print(f"  ID: {v['id']}")
        print(f"  Views: {stats.get('viewCount', 0)} | Likes: {stats.get('likeCount', 0)}")
        print(f"  Tags: {len(tags)} | Desc: {len(desc)} chars | Category: {s.get('categoryId')}")
        print(f"  Language: {s.get('defaultLanguage', 'none')} | Audio: {s.get('defaultAudioLanguage', 'none')}")
        if issues:
            for issue in issues:
                print(f"  !! {issue}")
        else:
            print(f"  OK — No issues")

    return vids["items"]


def fix_video(yt, video):
    """Fix a single video's SEO issues."""
    vid_id = video["id"]
    s = video["snippet"]
    st = video["status"]
    title = s["title"]

    # Determine if this is a Short
    is_short = "#Shorts" in title or "#shorts" in title

    # Optimized tags for the Iran-US topic
    base_tags = [
        "Iran USA", "Nuclear Crisis", "World War 3", "Middle East",
        "Geopolitics", "Iran Nuclear Program", "US Military",
        "Persian Gulf", "Pakistan", "South Asia", "Nuclear Threats",
        "Truth That Never Shared", "Iran 2026", "Military Analysis",
        "Global Politics",
    ]
    if is_short:
        base_tags.extend(["Shorts", "YouTube Shorts", "Viral"])

    # Use existing tags + merge new ones (deduplicate)
    existing_tags = set(t.lower() for t in s.get("tags", []))
    merged_tags = list(s.get("tags", []))
    for tag in base_tags:
        if tag.lower() not in existing_tags:
            merged_tags.append(tag)
            existing_tags.add(tag.lower())

    # Optimized description
    current_desc = s.get("description", "")
    if len(current_desc) < 200 or "Truth That Never Shared" not in current_desc:
        if is_short:
            desc = (
                f"{title}\n\n"
                "Iran vs USA Nuclear Showdown 2026 \u2014 The untold truth about "
                "the escalating crisis in the Middle East.\n\n"
                "Subscribe for more: @truthnevershared\n\n"
                "#IranUSA #NuclearCrisis #WW3 #MiddleEast #Geopolitics "
                "#Iran2026 #WorldWar3 #TruthThatNeverShared #Shorts"
            )
        else:
            desc = current_desc if len(current_desc) > 200 else (
                "Iran vs USA Nuclear Showdown 2026 \u2014 Why World War 3 Could Start "
                "From the Middle East\n\n"
                "In this video, we break down the escalating tensions between Iran and "
                "the United States, the nuclear threat, and why experts warn that the "
                "Middle East could become the flashpoint for World War 3 in 2026.\n\n"
                "Topics covered:\n"
                "- Iran's nuclear program and enrichment timeline\n"
                "- US military buildup in the Persian Gulf\n"
                "- Pakistan's strategic position and nuclear arsenal\n"
                "- Oil prices, global economy impact\n"
                "- Israel-Iran proxy war escalation\n"
                "- Saudi Arabia and Gulf states caught in the middle\n"
                "- What happens if diplomacy fails?\n\n"
                "\U0001f50d Subscribe to Truth That Never Shared for weekly deep dives "
                "into geopolitics, hidden history, and the stories mainstream media "
                "won't tell you.\n\n"
                "\U0001f514 Hit the bell for notifications!\n\n"
                "#IranUSA #NuclearCrisis #WW3 #MiddleEast #Geopolitics "
                "#Iran2026 #WorldWar3 #TruthThatNeverShared"
            )
    else:
        desc = current_desc

    # Build the update body
    update_snippet = {
        "title": title,
        "description": desc,
        "tags": merged_tags[:30],  # YouTube max is ~500 chars total
        "categoryId": "25",  # News & Politics
        "defaultLanguage": "en",
        "defaultAudioLanguage": "en",
    }

    update_status = {
        "privacyStatus": "public",
        "embeddable": True,
        "publicStatsViewable": True,
        "selfDeclaredMadeForKids": False,
    }

    try:
        resp = yt.videos().update(
            part="snippet,status",
            body={
                "id": vid_id,
                "snippet": update_snippet,
                "status": update_status,
            },
        ).execute()
        new_status = resp["status"]["privacyStatus"]
        new_tags = len(resp["snippet"].get("tags", []))
        print(f"  FIXED {vid_id}: {new_status} | {new_tags} tags | cat=25 | lang=en")
        return True
    except Exception as e:
        print(f"  ERROR {vid_id}: {e}")
        return False


def update_channel_defaults(yt):
    """Update channel branding settings and upload defaults."""
    print(f"\n{'='*70}")
    print(f"  UPDATING CHANNEL DEFAULTS")
    print(f"{'='*70}")

    # Channel description (keyword-rich, 300-1000 chars)
    description = (
        "Truth That Never Shared \u2014 Uncovering the stories mainstream media "
        "won\u2019t tell you.\n\n"
        "We bring you in-depth analysis of global geopolitics, hidden history, "
        "nuclear threats, and power struggles shaping our world. From the Iran-US "
        "standoff to South Asian politics, Middle East conflicts, and the untold "
        "truths behind world events \u2014 we break it all down.\n\n"
        "\U0001f50d What you\u2019ll find here:\n"
        "\u2022 Geopolitical deep dives & crisis analysis\n"
        "\u2022 Hidden history the world forgot\n"
        "\u2022 Nuclear threats & military strategy breakdowns\n"
        "\u2022 South Asian & Middle East conflict analysis\n"
        "\u2022 Weekly news analysis with facts, not opinions\n\n"
        "\U0001f4c5 New videos every week \u2014 Subscribe and hit the bell "
        "\U0001f514 so you never miss the truth.\n\n"
        "\U0001f30d Follow us:\n"
        "YouTube: @truthnevershared\n\n"
        "#Geopolitics #HiddenTruth #WorldNews #NuclearCrisis #MiddleEast #SouthAsia"
    )

    # Channel keywords (15 keyword phrases)
    keywords = (
        '"truth that never shared" geopolitics "hidden history" "nuclear crisis" '
        '"world war 3" "middle east" "south asia" "iran usa" "global politics" '
        '"military analysis" "untold stories" "news analysis" "geopolitical analysis" '
        '"pakistan india" "conflict analysis" "current affairs" "world news"'
    )

    try:
        resp = yt.channels().update(
            part="brandingSettings",
            body={
                "id": CHANNEL_ID,
                "brandingSettings": {
                    "channel": {
                        "title": "Truth that never shared",
                        "description": description,
                        "keywords": keywords,
                        "country": "PK",
                        "defaultLanguage": "en",
                        "defaultTab": "Featured",
                        "unsubscribedTrailer": "",
                    },
                },
            },
        ).execute()
        ch = resp["brandingSettings"]["channel"]
        print(f"  Channel description: {len(ch.get('description', ''))} chars")
        print(f"  Channel keywords: {ch.get('keywords', '')[:80]}...")
        print(f"  Country: {ch.get('country')}")
        print(f"  Language: {ch.get('defaultLanguage')}")
    except Exception as e:
        print(f"  Channel update error: {e}")


def create_playlist(yt, video_ids):
    """Create a playlist and add all videos to it."""
    print(f"\n{'='*70}")
    print(f"  CREATING PLAYLIST")
    print(f"{'='*70}")

    # Check if playlist already exists
    playlists = yt.playlists().list(
        part="snippet", channelId=CHANNEL_ID, maxResults=50,
    ).execute()

    existing = [p for p in playlists.get("items", [])
                if "Iran" in p["snippet"]["title"] or "Geopolitics" in p["snippet"]["title"]]

    if existing:
        playlist_id = existing[0]["id"]
        print(f"  Playlist already exists: {existing[0]['snippet']['title']} ({playlist_id})")
    else:
        try:
            pl = yt.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": "Geopolitics & Global Crisis Analysis",
                        "description": (
                            "In-depth analysis of global geopolitical crises, nuclear threats, "
                            "and power struggles. Iran vs USA, Middle East conflicts, South Asian "
                            "politics, and the untold truths behind world events.\n\n"
                            "#Geopolitics #NuclearCrisis #MiddleEast #WorldNews"
                        ),
                        "tags": [
                            "geopolitics", "nuclear crisis", "iran usa", "middle east",
                            "world war 3", "military analysis", "global politics",
                        ],
                        "defaultLanguage": "en",
                    },
                    "status": {
                        "privacyStatus": "public",
                    },
                },
            ).execute()
            playlist_id = pl["id"]
            print(f"  Created playlist: {pl['snippet']['title']} ({playlist_id})")
        except Exception as e:
            print(f"  Playlist creation error: {e}")
            return

    # Add videos (skip shorts — only main videos)
    for vid_id in video_ids:
        try:
            yt.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": vid_id,
                        },
                    },
                },
            ).execute()
            print(f"  Added {vid_id} to playlist")
        except Exception as e:
            if "duplicate" in str(e).lower() or "already" in str(e).lower():
                print(f"  {vid_id} already in playlist")
            else:
                print(f"  Error adding {vid_id}: {e}")


def main():
    yt = get_yt()

    # 1. Audit all videos
    videos = audit_videos(yt)
    if not videos:
        return

    # 2. Fix each video (visibility, tags, description, category, language)
    print(f"\n{'='*70}")
    print(f"  FIXING ALL VIDEOS")
    print(f"{'='*70}")
    fixed = 0
    main_video_ids = []
    for v in videos:
        if fix_video(yt, v):
            fixed += 1
        # Track main videos (not Shorts) for playlist
        if "#Shorts" not in v["snippet"]["title"] and "#shorts" not in v["snippet"]["title"]:
            main_video_ids.append(v["id"])

    print(f"\n  Fixed {fixed}/{len(videos)} videos")

    # 3. Update channel defaults
    update_channel_defaults(yt)

    # 4. Create playlist and add main videos
    if main_video_ids:
        create_playlist(yt, main_video_ids)

    # 5. Final verification
    print(f"\n{'='*70}")
    print(f"  VERIFYING CHANGES")
    print(f"{'='*70}")
    audit_videos(yt)

    print(f"\n{'='*70}")
    print(f"  MANUAL ACTION ITEMS")
    print(f"{'='*70}")
    print("  1. Upload channel banner (2560x1440) in YouTube Studio > Customization > Branding")
    print("  2. Upload channel avatar/profile picture")
    print("  3. Add watermark (250x250 PNG) in Studio > Customization > Branding")
    print("  4. Set channel trailer for non-subscribers in Studio > Customization > Layout")
    print("  5. Enable end screens on each video in Studio > Content > Edit > End screen")
    print("  6. Enable cards on each video in Studio > Content > Edit > Cards")
    print("  7. Engage with comments within 24h of each upload")
    print("  8. Post consistently (weekly schedule recommended)")


if __name__ == "__main__":
    main()
