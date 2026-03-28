"""Upload branding assets + set channel trailer via YouTube API.

Uploads: banner, watermark
Sets: unsubscribed trailer (main video wpihxo7K0hE)
Note: Avatar can only be set via YouTube Studio UI (Google Account picture).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = os.path.join(BASE, "tokens", "truth-that-never-shared.json")
BRANDING = os.path.join(BASE, "branding")

creds = Credentials.from_authorized_user_file(TOKEN)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    with open(TOKEN, "w") as f:
        f.write(creds.to_json())
yt = build("youtube", "v3", credentials=creds)

CHANNEL_ID = "UCKCSOyMYHVdA92mXJQ3K3Qw"
MAIN_VIDEO = "wpihxo7K0hE"


# ── 1. Upload Banner ──────────────────────────────────────────────────────
def upload_banner():
    banner_path = os.path.join(BRANDING, "channel_banner.png")
    if not os.path.exists(banner_path):
        print("  Banner file not found, skipping.")
        return

    print("  Uploading banner...")
    # Step 1: Upload the image to get a URL
    media = MediaFileUpload(banner_path, mimetype="image/png", resumable=True)
    resp = yt.channelBanners().insert(media_body=media).execute()
    banner_url = resp["url"]
    print(f"  Banner uploaded, URL obtained.")

    # Step 2: Set the banner on the channel
    channel = yt.channels().list(part="brandingSettings", id=CHANNEL_ID).execute()["items"][0]
    if "image" not in channel["brandingSettings"]:
        channel["brandingSettings"]["image"] = {}
    channel["brandingSettings"]["image"]["bannerExternalUrl"] = banner_url

    yt.channels().update(
        part="brandingSettings",
        body=channel,
    ).execute()
    print("  Banner set on channel!")


# ── 2. Upload Watermark ───────────────────────────────────────────────────
def upload_watermark():
    wm_path = os.path.join(BRANDING, "watermark.png")
    if not os.path.exists(wm_path):
        print("  Watermark file not found, skipping.")
        return

    print("  Uploading watermark...")
    media = MediaFileUpload(wm_path, mimetype="image/png")
    yt.watermarks().set(
        channelId=CHANNEL_ID,
        media_body=media,
        body={
            "timing": {
                "type": "offsetFromEnd",
                "durationMs": "15000",
                "offsetMs": "0",
            },
            "position": {
                "type": "corner",
                "cornerPosition": "topRight",
            },
            "imageUrl": "",
        },
    ).execute()
    print("  Watermark set (entire video, top-right)!")


# ── 3. Set Channel Trailer ────────────────────────────────────────────────
def set_channel_trailer():
    print(f"  Setting channel trailer to {MAIN_VIDEO}...")
    channel = yt.channels().list(
        part="brandingSettings", id=CHANNEL_ID
    ).execute()["items"][0]

    channel["brandingSettings"]["channel"]["unsubscribedTrailer"] = MAIN_VIDEO

    yt.channels().update(
        part="brandingSettings",
        body=channel,
    ).execute()
    print("  Channel trailer set!")


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== Uploading Branding Assets ===\n")

    try:
        upload_banner()
    except Exception as e:
        print(f"  Banner error: {e}")

    try:
        upload_watermark()
    except Exception as e:
        print(f"  Watermark error: {e}")

    try:
        set_channel_trailer()
    except Exception as e:
        print(f"  Trailer error: {e}")

    print("\n=== Done ===")
    print("\nManual steps remaining:")
    print("  - Avatar: Upload branding/channel_avatar.png in YouTube Studio > Customization > Branding > Picture")
    print("  - End screens: YouTube Studio > Content > [video] > Edit > End screen (no API support)")
    print("  - Cards: YouTube Studio > Content > [video] > Edit > Cards (no API support)")
