"""video_builder.py — MoviePy video assembly.

Single responsibility: combine image/video clips, audio, and captions
into a final MP4 file. Nothing else.
"""

import logging
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)

from config import OUTPUT_DIR

logger = logging.getLogger(__name__)

_FPS = 24
_VIDEO_WIDTH = 1920
_VIDEO_HEIGHT = 1080
_CAPTION_FONT_SIZE = 55
_CAPTION_STROKE_WIDTH = 3


def _slugify(text: str) -> str:
    """Convert a title to a safe filename slug (max 60 chars)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-") or "video"

# ── Font discovery (no ImageMagick needed) ────────────────────────────────────
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",          # macOS
    "/System/Library/Fonts/Arial.ttf",              # macOS
    "/Library/Fonts/Arial Unicode.ttf",             # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux/Docker
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _get_font(size: int = _CAPTION_FONT_SIZE) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
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


def _draw_caption(frame: np.ndarray, caption: str) -> np.ndarray:
    """Draw white+stroke caption text on a numpy video frame using PIL."""
    font = _get_font(_CAPTION_FONT_SIZE)
    lines = _wrap_text(caption, font, max_width=1700)

    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)

    line_height = _CAPTION_FONT_SIZE + 12
    total_height = len(lines) * line_height
    y = int(_VIDEO_HEIGHT * 0.82) - total_height // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (_VIDEO_WIDTH - text_w) // 2
        # Stroke (shadow outline)
        sw = _CAPTION_STROKE_WIDTH
        for dx in range(-sw, sw + 1):
            for dy in range(-sw, sw + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        # Main text
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height

    return np.array(img)


def build_video(
    segments: list[dict],
    audio_files: list[str],
    visual_files: list[str],
    output_path: str | None = None,
    title: str | None = None,
) -> str:
    """Assemble per-segment visual (image or video clip) + audio + caption into MP4.

    Args:
        segments:      List of segment dicts (may contain a "caption" key).
        audio_files:   Ordered list of MP3 paths (one per segment).
        visual_files:  Ordered list of image (.jpg) or video (.mp4) paths.
        output_path:   Destination MP4 path. Auto-generated from title if None.
        title:         Used to generate a human-readable filename.

    Returns:
        Path to the written MP4 file.
    """
    if output_path is None:
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        slug = _slugify(title) if title else "video"
        output_path = f"{OUTPUT_DIR}/{slug}.mp4"

    clips = []
    for i, (segment, audio_path, visual_path) in enumerate(
        zip(segments, audio_files, visual_files)
    ):
        logger.info("Building clip %d/%d", i + 1, len(segments))
        audio = AudioFileClip(audio_path)
        duration = audio.duration

        ext = Path(visual_path).suffix.lower()

        if ext == ".mp4":
            # ── Video clip ────────────────────────────────────────────────────
            raw = VideoFileClip(visual_path, audio=False)
            if raw.duration < duration:
                # Loop if clip is shorter than audio
                loops = int(duration / raw.duration) + 1
                from moviepy.editor import concatenate_videoclips as _cat
                raw = _cat([raw] * loops)
            base = (
                raw.subclip(0, duration)
                   .resize(height=_VIDEO_HEIGHT)
                   .crop(
                       x_center=_VIDEO_WIDTH / 2,
                       y_center=_VIDEO_HEIGHT / 2,
                       width=_VIDEO_WIDTH,
                       height=_VIDEO_HEIGHT,
                   )
            )
        else:
            # ── Static image ──────────────────────────────────────────────────
            base = (
                ImageClip(visual_path)
                .set_duration(duration)
                .resize(height=_VIDEO_HEIGHT)
                .crop(
                    x_center=_VIDEO_WIDTH / 2,
                    y_center=_VIDEO_HEIGHT / 2,
                    width=_VIDEO_WIDTH,
                    height=_VIDEO_HEIGHT,
                )
            )

        caption = segment.get("caption", "")
        if caption:
            def _make_captioner(cap):
                def _add(frame):
                    return _draw_caption(frame, cap)
                return _add
            clip = base.fl_image(_make_captioner(caption))
        else:
            clip = base

        clips.append(clip.set_audio(audio))

    logger.info("Concatenating %d clips", len(clips))
    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(
        output_path,
        fps=_FPS,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        logger=None,
    )
    logger.info("Video written to %s", output_path)
    return output_path
