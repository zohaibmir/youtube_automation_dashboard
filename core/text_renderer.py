"""core/text_renderer.py — Shared font discovery, text wrapping, and caption rendering.

Eliminates duplication between video_builder.py and shorts_builder.py.
Both builders import from here instead of maintaining their own copies.
"""

import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── Font discovery (no ImageMagick needed) ────────────────────────────────────
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",          # macOS
    "/System/Library/Fonts/Arial.ttf",              # macOS
    "/Library/Fonts/Arial Unicode.ttf",             # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux/Docker
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def get_font(size: int = 55) -> ImageFont.FreeTypeFont:
    """Find the first available system font at the given size."""
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        w = draw.textbbox((0, 0), candidate, font=font)[2]
        if w > max_width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_caption_overlay(
    caption: str,
    width: int,
    height: int,
    font_size: int = 55,
    stroke_width: int = 3,
    y_position: float = 0.82,
    margin: int = 220,
) -> np.ndarray:
    """Pre-render caption text as a transparent RGBA overlay.

    Returns a numpy array (H, W, 4) suitable for ImageClip(transparent=True).
    Rendered ONCE per clip — eliminates per-frame PIL text draw bottleneck.

    Args:
        caption: Text to render.
        width: Frame width in pixels.
        height: Frame height in pixels.
        font_size: Font size in points.
        stroke_width: Outline stroke thickness.
        y_position: Vertical center as fraction of height (0.0=top, 1.0=bottom).
        margin: Horizontal margin subtracted from width for wrapping.
    """
    font = get_font(font_size)
    lines = wrap_text(caption, font, max_width=width - margin)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    line_height = font_size + 12
    total_height = len(lines) * line_height
    y = int(height * y_position) - total_height // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        sw = stroke_width
        for dx in range(-sw, sw + 1):
            for dy in range(-sw, sw + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 220))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height

    return np.array(img)


def draw_caption_on_frame(
    frame: np.ndarray,
    caption: str,
    width: int,
    height: int,
    font_size: int = 55,
    stroke_width: int = 3,
    y_position: float = 0.82,
) -> np.ndarray:
    """Draw white+stroke caption text directly on a numpy video frame.

    Used for one-off rendering (intro/outro). For segment captions,
    prefer render_caption_overlay() + CompositeVideoClip instead.
    """
    font = get_font(font_size)
    lines = wrap_text(caption, font, max_width=width - 220)

    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)

    line_height = font_size + 12
    total_height = len(lines) * line_height
    y = int(height * y_position) - total_height // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        sw = stroke_width
        for dx in range(-sw, sw + 1):
            for dy in range(-sw, sw + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height

    return np.array(img)


def slugify(text: str, max_len: int = 60) -> str:
    """Convert a title to a safe filename slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:max_len].strip("-") or "video"
