"""Generate channel branding assets: banner, avatar, watermark.

Creates professional branding for 'Truth That Never Shared' channel.
All outputs go to branding/ directory.
"""
import os
import math
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "branding")
os.makedirs(OUT_DIR, exist_ok=True)

FONT_DIR = "/System/Library/Fonts/Supplemental"
IMPACT = os.path.join(FONT_DIR, "Impact.ttf")
ARIAL_BLACK = os.path.join(FONT_DIR, "Arial Black.ttf")
DIN_BOLD = os.path.join(FONT_DIR, "DIN Condensed Bold.ttf")
GEORGIA_BOLD = os.path.join(FONT_DIR, "Georgia Bold.ttf")

# Brand colors
DARK_BG = (15, 15, 25)         # Near-black navy
ACCENT_RED = (200, 30, 30)     # Deep red — urgency
ACCENT_GOLD = (218, 175, 65)   # Gold — prestige
WHITE = (255, 255, 255)
LIGHT_GRAY = (180, 180, 190)
MID_GRAY = (60, 60, 75)


def _draw_gradient(draw, w, h, color_top, color_bot):
    """Vertical linear gradient."""
    for y in range(h):
        ratio = y / h
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _draw_globe_grid(draw, cx, cy, radius, color, line_width=2):
    """Draw a stylized globe wireframe (longitude + latitude arcs)."""
    # Latitude lines (horizontal ellipses)
    for lat in range(-60, 61, 30):
        lat_r = math.radians(lat)
        y_off = int(radius * math.sin(lat_r))
        w_scale = math.cos(lat_r)
        bbox = [cx - int(radius * w_scale), cy - y_off - 2,
                cx + int(radius * w_scale), cy - y_off + 2]
        if bbox[2] > bbox[0]:
            draw.ellipse(bbox, outline=color, width=line_width)

    # Longitude lines (vertical ellipses)
    for lon_deg in range(0, 180, 30):
        lon_r = math.radians(lon_deg)
        w = int(radius * math.sin(lon_r))
        if w < 5:
            w = 5
        bbox = [cx - w, cy - radius, cx + w, cy + radius]
        draw.ellipse(bbox, outline=color, width=line_width)

    # Outer circle
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                 outline=color, width=line_width + 1)


def _center_text(draw, text, font, y, img_width, fill):
    """Draw text centered horizontally."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (img_width - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]  # return text height


def _draw_eye_icon(draw, cx, cy, size, color):
    """Draw a stylized eye (all-seeing eye motif)."""
    # Outer eye shape (two arcs)
    half = size // 2
    draw.arc([cx - half, cy - half // 2, cx + half, cy + half + half // 2],
             start=200, end=340, fill=color, width=3)
    draw.arc([cx - half, cy - half - half // 2, cx + half, cy + half // 2],
             start=20, end=160, fill=color, width=3)
    # Iris
    iris_r = size // 5
    draw.ellipse([cx - iris_r, cy - iris_r, cx + iris_r, cy + iris_r],
                 outline=color, width=2)
    # Pupil
    pupil_r = size // 10
    draw.ellipse([cx - pupil_r, cy - pupil_r, cx + pupil_r, cy + pupil_r],
                 fill=color)


# ═══════════════════════════════════════════════════════════════
#  1. CHANNEL BANNER (2560 x 1440)
# ═══════════════════════════════════════════════════════════════
def generate_banner():
    W, H = 2560, 1440
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # Background gradient
    _draw_gradient(draw, W, H, (10, 10, 20), (25, 15, 30))

    # Subtle grid pattern
    for x in range(0, W, 80):
        draw.line([(x, 0), (x, H)], fill=(30, 30, 45), width=1)
    for y in range(0, H, 80):
        draw.line([(0, y), (W, y)], fill=(30, 30, 45), width=1)

    # Globe in background (right side)
    _draw_globe_grid(draw, W - 500, H // 2, 350, (40, 40, 60), line_width=2)

    # Red accent stripe at top
    draw.rectangle([(0, 0), (W, 8)], fill=ACCENT_RED)

    # ── Safe area: center 1546 x 423 (what shows on all devices) ──
    safe_left = (W - 1546) // 2  # ~507
    safe_top = (H - 423) // 2    # ~508
    safe_right = safe_left + 1546
    safe_bottom = safe_top + 423

    # Gold decorative line above title
    line_y = safe_top + 30
    line_w = 600
    draw.line([(W // 2 - line_w, line_y), (W // 2 + line_w, line_y)],
              fill=ACCENT_GOLD, width=3)

    # Channel name — big Impact
    title_font = ImageFont.truetype(IMPACT, 110)
    title_y = safe_top + 55
    _center_text(draw, "TRUTH THAT", title_font, title_y, W, WHITE)
    _center_text(draw, "NEVER SHARED", title_font, title_y + 115, W, ACCENT_RED)

    # Tagline
    tag_font = ImageFont.truetype(GEORGIA_BOLD, 36)
    tag_y = safe_top + 300
    _center_text(draw, "Geopolitics  •  Hidden History  •  Global Crisis Analysis",
                 tag_font, tag_y, W, ACCENT_GOLD)

    # Gold line below tagline
    line_y2 = tag_y + 55
    draw.line([(W // 2 - line_w, line_y2), (W // 2 + line_w, line_y2)],
              fill=ACCENT_GOLD, width=3)

    # Small schedule text
    sched_font = ImageFont.truetype(DIN_BOLD, 28)
    _center_text(draw, "NEW VIDEOS EVERY WEEK", sched_font,
                 safe_bottom + 40, W, LIGHT_GRAY)

    # Red accent stripe at bottom
    draw.rectangle([(0, H - 8), (W, H)], fill=ACCENT_RED)

    path = os.path.join(OUT_DIR, "channel_banner.png")
    img.save(path, "PNG", optimize=True)
    print(f"  Banner: {path} ({W}x{H})")
    return path


# ═══════════════════════════════════════════════════════════════
#  2. CHANNEL AVATAR (800 x 800)
# ═══════════════════════════════════════════════════════════════
def generate_avatar():
    W = H = 800
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Circular background
    cx, cy = W // 2, H // 2
    r = 390
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=DARK_BG)

    # Gold ring
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 outline=ACCENT_GOLD, width=8)

    # Inner circle
    inner_r = 340
    draw.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
                 outline=(40, 40, 55), width=2)

    # Eye icon at center-top
    _draw_eye_icon(draw, cx, cy - 80, 180, ACCENT_GOLD)

    # "TTNS" text below the eye
    font_big = ImageFont.truetype(IMPACT, 120)
    _center_text(draw, "TTNS", font_big, cy + 50, W, WHITE)

    # Small subtitle
    font_sm = ImageFont.truetype(DIN_BOLD, 32)
    _center_text(draw, "TRUTH THAT NEVER SHARED", font_sm, cy + 185, W, ACCENT_GOLD)

    path = os.path.join(OUT_DIR, "channel_avatar.png")
    img.save(path, "PNG")
    print(f"  Avatar: {path} ({W}x{H})")
    return path


# ═══════════════════════════════════════════════════════════════
#  3. WATERMARK (250 x 250, transparent)
# ═══════════════════════════════════════════════════════════════
def generate_watermark():
    W = H = 250
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = W // 2, H // 2
    r = 115

    # Semi-transparent circle background
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(15, 15, 25, 160))

    # Gold ring
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 outline=(*ACCENT_GOLD, 200), width=4)

    # "TTNS" text
    font = ImageFont.truetype(IMPACT, 64)
    _center_text(draw, "TTNS", font, cy - 35, W, (*WHITE, 220))

    # Subscribe hint
    font_sm = ImageFont.truetype(DIN_BOLD, 18)
    _center_text(draw, "SUBSCRIBE", font_sm, cy + 40, W, (*ACCENT_RED, 200))

    path = os.path.join(OUT_DIR, "watermark.png")
    img.save(path, "PNG")
    print(f"  Watermark: {path} ({W}x{H})")
    return path


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Generating branding assets...\n")
    generate_banner()
    generate_avatar()
    generate_watermark()
    print(f"\nAll assets saved to: {OUT_DIR}/")
    print("\nUpload instructions:")
    print("  Banner:    YouTube Studio > Customization > Branding > Banner image")
    print("  Avatar:    YouTube Studio > Customization > Branding > Picture")
    print("  Watermark: YouTube Studio > Customization > Branding > Video watermark")
