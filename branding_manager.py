"""branding_manager.py — Generate and upload channel branding assets.

Single responsibility: create banner / avatar / watermark images
and upload them to YouTube via the Data API.
"""

import logging
import math
import os

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_BRANDING_DIR = os.path.join(_BASE_DIR, "branding")
_FONT_DIR = "/System/Library/Fonts/Supplemental"

# ── Brand palette ────────────────────────────────────────────────────────
_DARK_BG = (15, 15, 25)
_ACCENT_RED = (200, 30, 30)
_ACCENT_GOLD = (218, 175, 65)
_WHITE = (255, 255, 255)
_LIGHT_GRAY = (180, 180, 190)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(_FONT_DIR, name)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _center_text(draw, text, font, y, img_w, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (img_w - (bbox[2] - bbox[0])) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _gradient(draw, w, h, top, bot):
    for y in range(h):
        r = y / h
        draw.line([(0, y), (w, y)], fill=tuple(
            int(top[i] + (bot[i] - top[i]) * r) for i in range(3)
        ))


def _globe_grid(draw, cx, cy, radius, color):
    for lat in range(-60, 61, 30):
        lr = math.radians(lat)
        yo = int(radius * math.sin(lr))
        ws = math.cos(lr)
        bx = [cx - int(radius * ws), cy - yo - 2, cx + int(radius * ws), cy - yo + 2]
        if bx[2] > bx[0]:
            draw.ellipse(bx, outline=color, width=2)
    for lon in range(0, 180, 30):
        w = max(5, int(radius * math.sin(math.radians(lon))))
        draw.ellipse([cx - w, cy - radius, cx + w, cy + radius], outline=color, width=2)
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=color, width=3)


def _eye_icon(draw, cx, cy, size, color):
    half = size // 2
    draw.arc([cx - half, cy - half // 2, cx + half, cy + half + half // 2],
             start=200, end=340, fill=color, width=3)
    draw.arc([cx - half, cy - half - half // 2, cx + half, cy + half // 2],
             start=20, end=160, fill=color, width=3)
    ir = size // 5
    draw.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], outline=color, width=2)
    pr = size // 10
    draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=color)


# ── Public API ───────────────────────────────────────────────────────────

def list_assets() -> list[dict]:
    """Return info about existing branding files."""
    os.makedirs(_BRANDING_DIR, exist_ok=True)
    assets = []
    for name, label, dims in [
        ("channel_banner.png", "Banner", "2560×1440"),
        ("channel_avatar.png", "Avatar", "800×800"),
        ("watermark.png", "Watermark", "250×250"),
    ]:
        path = os.path.join(_BRANDING_DIR, name)
        exists = os.path.isfile(path)
        assets.append({
            "name": name,
            "label": label,
            "dimensions": dims,
            "exists": exists,
            "size_kb": round(os.path.getsize(path) / 1024, 1) if exists else 0,
            "url": f"/branding/{name}" if exists else None,
        })
    return assets


def generate_assets(
    channel_name: str = "TRUTH THAT NEVER SHARED",
    tagline: str = "Geopolitics  •  Hidden History  •  Global Crisis Analysis",
) -> dict:
    """Generate all three branding images. Returns paths dict."""
    os.makedirs(_BRANDING_DIR, exist_ok=True)
    parts = channel_name.upper().split(maxsplit=2) if len(channel_name.split()) >= 3 else [channel_name.upper(), ""]
    line1 = " ".join(parts[:2]) if len(parts) >= 2 else parts[0]
    line2 = " ".join(parts[2:]) if len(parts) > 2 else ""

    # Abbreviation for avatar
    words = channel_name.upper().split()
    abbrev = "".join(w[0] for w in words[:4]) if words else "CH"

    banner_path = _generate_banner(line1, line2, tagline)
    avatar_path = _generate_avatar(abbrev, channel_name.upper())
    watermark_path = _generate_watermark(abbrev)

    return {
        "banner": banner_path,
        "avatar": avatar_path,
        "watermark": watermark_path,
    }


def upload_banner_to_youtube(channel_slug: str | None = None) -> dict:
    """Upload banner to YouTube channel via API."""
    from youtube_uploader import _get_credentials
    from googleapiclient.discovery import build as yt_build
    from googleapiclient.http import MediaFileUpload

    banner_path = os.path.join(_BRANDING_DIR, "channel_banner.png")
    if not os.path.isfile(banner_path):
        return {"ok": False, "error": "Banner file not found. Generate it first."}

    try:
        creds = _get_credentials(channel_slug)
        yt = yt_build("youtube", "v3", credentials=creds)

        media = MediaFileUpload(banner_path, mimetype="image/png", resumable=True)
        resp = yt.channelBanners().insert(media_body=media).execute()
        banner_url = resp["url"]

        # Get channel ID
        ch_resp = yt.channels().list(part="brandingSettings", mine=True).execute()
        if not ch_resp.get("items"):
            return {"ok": False, "error": "No channel found for this account."}

        channel = ch_resp["items"][0]
        if "image" not in channel["brandingSettings"]:
            channel["brandingSettings"]["image"] = {}
        channel["brandingSettings"]["image"]["bannerExternalUrl"] = banner_url

        yt.channels().update(part="brandingSettings", body=channel).execute()
        logger.info("Banner uploaded successfully")
        return {"ok": True}
    except Exception as e:
        logger.error("Banner upload failed: %s", e)
        return {"ok": False, "error": str(e)}


def set_channel_trailer(video_id: str, channel_slug: str | None = None) -> dict:
    """Set the channel trailer for unsubscribed visitors."""
    from youtube_uploader import _get_credentials
    from googleapiclient.discovery import build as yt_build

    if not video_id or not video_id.strip():
        return {"ok": False, "error": "Video ID required."}

    try:
        creds = _get_credentials(channel_slug)
        yt = yt_build("youtube", "v3", credentials=creds)

        ch_resp = yt.channels().list(part="brandingSettings", mine=True).execute()
        if not ch_resp.get("items"):
            return {"ok": False, "error": "No channel found."}

        channel = ch_resp["items"][0]
        channel["brandingSettings"]["channel"]["unsubscribedTrailer"] = video_id.strip()
        yt.channels().update(part="brandingSettings", body=channel).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Private generators ───────────────────────────────────────────────────

def _generate_banner(line1: str, line2: str, tagline: str) -> str:
    W, H = 2560, 1440
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    _gradient(draw, W, H, (10, 10, 20), (25, 15, 30))

    for x in range(0, W, 80):
        draw.line([(x, 0), (x, H)], fill=(30, 30, 45), width=1)
    for y in range(0, H, 80):
        draw.line([(0, y), (W, y)], fill=(30, 30, 45), width=1)

    _globe_grid(draw, W - 500, H // 2, 350, (40, 40, 60))
    draw.rectangle([(0, 0), (W, 8)], fill=_ACCENT_RED)

    safe_top = (H - 423) // 2
    safe_bottom = safe_top + 423
    line_w = 600

    draw.line([(W // 2 - line_w, safe_top + 30), (W // 2 + line_w, safe_top + 30)],
              fill=_ACCENT_GOLD, width=3)

    title_font = _font("Impact.ttf", 110)
    _center_text(draw, line1, title_font, safe_top + 55, W, _WHITE)
    if line2:
        _center_text(draw, line2, title_font, safe_top + 170, W, _ACCENT_RED)

    tag_font = _font("Georgia Bold.ttf", 36)
    tag_y = safe_top + 300
    _center_text(draw, tagline, tag_font, tag_y, W, _ACCENT_GOLD)
    draw.line([(W // 2 - line_w, tag_y + 55), (W // 2 + line_w, tag_y + 55)],
              fill=_ACCENT_GOLD, width=3)

    sched_font = _font("DIN Condensed Bold.ttf", 28)
    _center_text(draw, "NEW VIDEOS EVERY WEEK", sched_font, safe_bottom + 40, W, _LIGHT_GRAY)
    draw.rectangle([(0, H - 8), (W, H)], fill=_ACCENT_RED)

    path = os.path.join(_BRANDING_DIR, "channel_banner.png")
    img.save(path, "PNG", optimize=True)
    return path


def _generate_avatar(abbrev: str, full_name: str) -> str:
    W = H = 800
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = W // 2, H // 2

    draw.ellipse([cx - 390, cy - 390, cx + 390, cy + 390], fill=_DARK_BG)
    draw.ellipse([cx - 390, cy - 390, cx + 390, cy + 390], outline=_ACCENT_GOLD, width=8)
    draw.ellipse([cx - 340, cy - 340, cx + 340, cy + 340], outline=(40, 40, 55), width=2)

    _eye_icon(draw, cx, cy - 80, 180, _ACCENT_GOLD)
    _center_text(draw, abbrev[:4], _font("Impact.ttf", 120), cy + 50, W, _WHITE)
    _center_text(draw, full_name[:30], _font("DIN Condensed Bold.ttf", 32), cy + 185, W, _ACCENT_GOLD)

    path = os.path.join(_BRANDING_DIR, "channel_avatar.png")
    img.save(path, "PNG")
    return path


def _generate_watermark(abbrev: str) -> str:
    W = H = 250
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = W // 2, H // 2

    draw.ellipse([cx - 115, cy - 115, cx + 115, cy + 115], fill=(15, 15, 25, 160))
    draw.ellipse([cx - 115, cy - 115, cx + 115, cy + 115], outline=(*_ACCENT_GOLD, 200), width=4)
    _center_text(draw, abbrev[:4], _font("Impact.ttf", 64), cy - 35, W, (*_WHITE, 220))
    _center_text(draw, "SUBSCRIBE", _font("DIN Condensed Bold.ttf", 18), cy + 40, W, (*_ACCENT_RED, 200))

    path = os.path.join(_BRANDING_DIR, "watermark.png")
    img.save(path, "PNG")
    return path
