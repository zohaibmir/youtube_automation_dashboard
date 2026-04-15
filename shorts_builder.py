"""shorts_builder.py — YouTube Shorts vertical video builder.

Single responsibility: take existing pipeline segments/audio/visuals
and produce 1–3 vertical (1080×1920) clips under 60 seconds.
"""

import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image
from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)

from config import BG_MUSIC_PATH, BG_MUSIC_VOLUME_DB, FFMPEG_THREADS, OUTPUT_DIR
from core.text_renderer import render_caption_overlay, slugify as _slugify

logger = logging.getLogger(__name__)

_FPS = 24          # 24 is plenty for Shorts (saves ~20% encode time vs 30)
_WIDTH = 1080
_HEIGHT = 1920
_THREADS = FFMPEG_THREADS
_MAX_DURATION = 59  # YT Shorts limit
_CAPTION_FONT_SIZE = 60
_CAPTION_STROKE = 3

# ── Caption overlay (delegates to shared renderer) ────────────────────────────

def _render_caption_overlay(caption: str) -> np.ndarray:
    """Pre-render caption as transparent RGBA overlay for Shorts format."""
    return render_caption_overlay(
        caption, _WIDTH, _HEIGHT,
        font_size=_CAPTION_FONT_SIZE,
        stroke_width=_CAPTION_STROKE,
        y_position=0.72,
        margin=80,
    )


# ── Segment selection ─────────────────────────────────────────────────────────

def _pick_short_segments(
    segments: list[dict],
    audio_files: list[str],
    visual_files: list[str],
    short_index: int,
) -> list[tuple]:
    """Select 2–4 segments for one Short, staying under 59 seconds.

    Strategy:
      - Short 0 (hook reel): hook + first 2–3 body segments
      - Short 1 (mid reel):  middle body segments
      - Short 2 (finale):    last 2–3 body segments (exclude outro)
    """
    body = []
    for i, seg in enumerate(segments):
        stype = seg.get("type", "segment").lower()
        if stype == "outro":
            continue
        body.append((seg, audio_files[i], visual_files[i]))

    if not body:
        return []

    n = len(body)
    if short_index == 0:
        # Hook + first few
        candidates = body[: min(4, n)]
    elif short_index == 1:
        mid = n // 2
        candidates = body[max(0, mid - 2) : mid + 2]
    else:
        candidates = body[max(0, n - 4) :]

    # Trim to fit under _MAX_DURATION
    picked = []
    total = 0.0
    for seg, aud, vis in candidates:
        dur = AudioFileClip(aud).duration
        if total + dur > _MAX_DURATION:
            break
        picked.append((seg, aud, vis))
        total += dur

    return picked


# ── Build one Short ───────────────────────────────────────────────────────────

def _build_one_short(
    selected: list[tuple],
    output_path: str,
    music_path: str | None = None,
) -> str:
    """Render a single Short from selected (segment, audio, visual) tuples."""
    clips = []

    for seg, audio_path, visual_path in selected:
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        ext = Path(visual_path).suffix.lower()

        if ext == ".mp4":
            raw = VideoFileClip(visual_path, audio=False)
            if raw.duration < duration:
                loops = int(duration / raw.duration) + 1
                raw = concatenate_videoclips([raw] * loops)
            # Crop to vertical: prioritise centre of the frame
            base = (
                raw.subclip(0, duration)
                .resize(width=_WIDTH)
            )
            bh = base.size[1]
            if bh < _HEIGHT:
                base = raw.subclip(0, duration).resize(height=_HEIGHT)
            base = base.crop(
                x_center=base.size[0] / 2,
                y_center=base.size[1] / 2,
                width=_WIDTH,
                height=_HEIGHT,
            )
        else:
            base = (
                ImageClip(visual_path)
                .set_duration(duration)
                .resize(height=_HEIGHT)
            )
            bw = base.size[0]
            if bw < _WIDTH:
                base = (
                    ImageClip(visual_path)
                    .set_duration(duration)
                    .resize(width=_WIDTH)
                )
            base = base.crop(
                x_center=base.size[0] / 2,
                y_center=base.size[1] / 2,
                width=_WIDTH,
                height=_HEIGHT,
            )

        caption = seg.get("caption", "")
        if caption:
            overlay = _render_caption_overlay(caption)
            caption_clip = (
                ImageClip(overlay, ismask=False, transparent=True)
                .set_duration(duration)
            )
            clip = CompositeVideoClip([base, caption_clip])
        else:
            clip = base

        clips.append(clip.set_audio(audio))

    if not clips:
        raise ValueError("No clips to assemble for Short")

    final = concatenate_videoclips(clips, method="compose")

    # Background music (quieter for Shorts)
    if music_path and Path(music_path).is_file():
        music = AudioFileClip(music_path)
        if music.duration < final.duration:
            loops = int(final.duration / music.duration) + 1
            from moviepy.editor import concatenate_audioclips
            music = concatenate_audioclips([music] * loops)
        music = music.subclip(0, final.duration)
        music = music.volumex(10 ** ((BG_MUSIC_VOLUME_DB - 3) / 20.0))  # 3 dB quieter
        music = music.audio_fadein(1.0).audio_fadeout(2.0)
        if final.audio:
            final = final.set_audio(CompositeAudioClip([final.audio, music]))
        else:
            final = final.set_audio(music)

    # Import HW encoder settings from video_builder (detected once at startup)
    from video_builder import _HW_CODEC, _HW_PARAMS
    logger.info("Encoding Short with %s (threads=%d)", _HW_CODEC, _THREADS)
    # Use temp_audiofile to avoid real-time audio piping (which spawns threads)
    temp_audiofile = f"{output_path}.temp_audio.m4a"
    final.write_videofile(
        output_path,
        fps=_FPS,
        codec=_HW_CODEC,
        audio_codec="aac",
        threads=_THREADS,
        ffmpeg_params=_HW_PARAMS,
        temp_audiofile=temp_audiofile,
        remove_temp=True,
        write_logfile=False,
        logger=None,
    )
    logger.info("Short written to %s (%.1fs)", output_path, final.duration)
    return output_path


# ── Public API ────────────────────────────────────────────────────────────────

def build_shorts(
    segments: list[dict],
    audio_files: list[str],
    visual_files: list[str],
    title: str | None = None,
    count: int = 2,
    music_path: str | None = None,
) -> list[str]:
    """Generate 1–3 YouTube Shorts from existing pipeline assets.

    Args:
        segments:     Full list of segment dicts from the long-form video.
        audio_files:  Ordered MP3 paths (one per segment).
        visual_files: Ordered image/video paths (one per segment).
        title:        Video title (used to name output files).
        count:        Number of Shorts to produce (1–3).
        music_path:   Optional background music path.

    Returns:
        List of output MP4 file paths.
    """
    count = max(1, min(3, count))
    slug = _slugify(title) if title else "short"
    out_dir = f"{OUTPUT_DIR}/shorts"
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    if music_path is None:
        music_path = BG_MUSIC_PATH if BG_MUSIC_PATH else None

    paths = []
    for idx in range(count):
        selected = _pick_short_segments(segments, audio_files, visual_files, idx)
        if not selected:
            logger.warning("Not enough content for Short #%d — skipping", idx + 1)
            continue
        out_path = f"{out_dir}/{slug}-short-{idx + 1}.mp4"
        try:
            path = _build_one_short(selected, out_path, music_path)
            paths.append(path)
        except Exception as e:
            logger.error("Failed to build Short #%d: %s", idx + 1, e)

    logger.info("Shorts pipeline complete: %d of %d built", len(paths), count)
    return paths
