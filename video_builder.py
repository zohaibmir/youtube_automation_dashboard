"""video_builder.py — MoviePy video assembly.

Single responsibility: combine image/video clips, audio, and captions
into a final MP4 file. Supports Ken Burns zoom, crossfade transitions,
background music mixing, and branded intro/outro sequences.
"""

import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)

from config import (
    BG_MUSIC_VOLUME_DB,
    CHANNEL_NAME,
    CROSSFADE_DURATION,
    INTRO_DURATION,
    KEN_BURNS_ZOOM,
    OUTPUT_DIR,
    OUTRO_CTA_TEXT,
    OUTRO_DURATION,
)
from core.text_renderer import (
    draw_caption_on_frame as _draw_caption_impl,
    get_font as _get_font,
    render_caption_overlay as _render_caption_overlay_impl,
    slugify as _slugify,
    wrap_text as _wrap_text,
)

logger = logging.getLogger(__name__)

_FPS = 24
_VIDEO_WIDTH = 1920
_VIDEO_HEIGHT = 1080
_THREADS = os.cpu_count() or 4


def _resolve_channel_name() -> str:
    """Get channel display name: CHANNEL_NAME config → default channel in channels.json → fallback."""
    if CHANNEL_NAME:
        return CHANNEL_NAME
    try:
        import json
        channels_path = os.path.join(os.path.dirname(__file__), "tokens", "channels.json")
        with open(channels_path) as f:
            channels = json.load(f)
        for slug, cfg in channels.items():
            if cfg.get("is_default"):
                return cfg.get("name", slug)
        # No default — return first channel name
        if channels:
            first = next(iter(channels.values()))
            return first.get("name", "")
    except Exception:
        pass
    return ""


# ── Encoder detection ─────────────────────────────────────────────────────────

def _detect_hw_encoder() -> tuple[str, list[str]]:
    """Return (codec, ffmpeg_params) using the fastest available encoder.

    Priority: libx264 ultrafast (Python per-frame is the bottleneck,
    not the encoder — so use fastest preset with quality-preserving CRF).
    """
    return "libx264", ["-preset", "ultrafast", "-crf", "18"]


_HW_CODEC, _HW_PARAMS = _detect_hw_encoder()
logger.info("Video encoder: %s %s", _HW_CODEC, _HW_PARAMS)
_CAPTION_FONT_SIZE = 55
_CAPTION_STROKE_WIDTH = 3


def _draw_caption(frame: np.ndarray, caption: str) -> np.ndarray:
    """Draw white+stroke caption text on a video frame (intro/outro only)."""
    return _draw_caption_impl(frame, caption, _VIDEO_WIDTH, _VIDEO_HEIGHT,
                              _CAPTION_FONT_SIZE, _CAPTION_STROKE_WIDTH)


def _render_caption_overlay(caption: str, width: int = _VIDEO_WIDTH,
                            height: int = _VIDEO_HEIGHT) -> np.ndarray:
    """Pre-render caption as RGBA overlay (once per clip)."""
    return _render_caption_overlay_impl(caption, width, height,
                                        _CAPTION_FONT_SIZE, _CAPTION_STROKE_WIDTH)


# ── Ken Burns zoom ────────────────────────────────────────────────────────────

def _apply_ken_burns(clip, duration: float, zoom_pct: float = 0.05, is_static: bool = False):
    """Return a clip with subtle slow-zoom (Ken Burns) effect.

    For static images (is_static=True): pre-caches the upscaled frame once
    instead of re-decoding it every frame — major performance win.
    """
    if zoom_pct <= 0:
        return clip

    w, h = _VIDEO_WIDTH, _VIDEO_HEIGHT
    upscale = 1 + zoom_pct
    bw, bh = int(w * upscale), int(h * upscale)

    if is_static:
        # Pre-render the upscaled frame ONCE (static image doesn't change)
        raw_frame = clip.get_frame(0)
        cached_big = np.array(
            Image.fromarray(raw_frame).resize((bw, bh), Image.BILINEAR)
        )

        def _zoom_static(t):
            progress = t / max(duration, 0.1)
            scale = 1.0 + zoom_pct * progress
            cw = int(w / scale * upscale)
            ch = int(h / scale * upscale)
            x1 = (bw - cw) // 2
            y1 = (bh - ch) // 2
            crop = cached_big[y1:y1 + ch, x1:x1 + cw]
            return np.array(Image.fromarray(crop).resize((w, h), Image.BILINEAR))

        from moviepy.editor import VideoClip
        return VideoClip(_zoom_static, duration=duration)
    else:
        # Video clip — must decode each frame
        big = clip.resize((bw, bh))

        def _zoom_frame(get_frame, t):
            progress = t / max(duration, 0.1)
            scale = 1.0 + zoom_pct * progress
            cw = int(w / scale * upscale)
            ch = int(h / scale * upscale)
            x1 = (bw - cw) // 2
            y1 = (bh - ch) // 2
            frame = get_frame(t)[y1:y1 + ch, x1:x1 + cw]
            return np.array(Image.fromarray(frame).resize((w, h), Image.BILINEAR))

        return big.fl(_zoom_frame, apply_to=["mask"]).set_duration(duration)


# ── Intro / Outro ─────────────────────────────────────────────────────────────

def _make_intro(channel_name: str, duration: float):
    """Create a branded intro clip: dark background → channel name fades in."""
    if duration <= 0:
        return None

    # Build a PIL frame with channel name centered
    img = Image.new("RGB", (_VIDEO_WIDTH, _VIDEO_HEIGHT), (12, 12, 18))
    draw = ImageDraw.Draw(img)
    font_big = _get_font(72)
    font_sub = _get_font(32)

    # Channel name
    bbox = draw.textbbox((0, 0), channel_name, font=font_big)
    tw = bbox[2] - bbox[0]
    tx = (_VIDEO_WIDTH - tw) // 2
    ty = _VIDEO_HEIGHT // 2 - 50
    draw.text((tx, ty), channel_name, font=font_big, fill=(255, 255, 255))

    # Subtle tagline
    tagline = "▶  " + OUTRO_CTA_TEXT + "  ▶"
    bbox2 = draw.textbbox((0, 0), tagline, font=font_sub)
    tw2 = bbox2[2] - bbox2[0]
    draw.text(
        ((_VIDEO_WIDTH - tw2) // 2, ty + 90),
        tagline, font=font_sub, fill=(124, 109, 250)
    )

    intro = ImageClip(np.array(img)).set_duration(duration)
    # Fade in from black over the first 60% of intro, hold the rest
    intro = intro.crossfadein(duration * 0.6)
    return intro


def _make_outro(channel_name: str, duration: float):
    """Create an outro clip: subscribe CTA → fade to black."""
    if duration <= 0:
        return None

    img = Image.new("RGB", (_VIDEO_WIDTH, _VIDEO_HEIGHT), (12, 12, 18))
    draw = ImageDraw.Draw(img)
    font_big = _get_font(64)
    font_cta = _get_font(40)

    # Thanks text
    thanks = "Thanks for watching!"
    bbox = draw.textbbox((0, 0), thanks, font=font_big)
    tw = bbox[2] - bbox[0]
    draw.text(
        ((_VIDEO_WIDTH - tw) // 2, _VIDEO_HEIGHT // 2 - 70),
        thanks, font=font_big, fill=(255, 255, 255)
    )

    # Subscribe CTA
    cta = OUTRO_CTA_TEXT
    bbox2 = draw.textbbox((0, 0), cta, font=font_cta)
    tw2 = bbox2[2] - bbox2[0]
    draw.text(
        ((_VIDEO_WIDTH - tw2) // 2, _VIDEO_HEIGHT // 2 + 20),
        cta, font=font_cta, fill=(255, 68, 68)
    )

    # Channel name small
    font_sm = _get_font(28)
    bbox3 = draw.textbbox((0, 0), channel_name, font=font_sm)
    tw3 = bbox3[2] - bbox3[0]
    draw.text(
        ((_VIDEO_WIDTH - tw3) // 2, _VIDEO_HEIGHT // 2 + 90),
        channel_name, font=font_sm, fill=(160, 160, 160)
    )

    outro = ImageClip(np.array(img)).set_duration(duration)
    outro = outro.crossfadeout(duration * 0.5)
    return outro


def build_video(
    segments: list[dict],
    audio_files: list[str],
    visual_files: list[str],
    output_path: str | None = None,
    title: str | None = None,
    music_path: str | None = None,
) -> str:
    """Assemble per-segment visual + audio + caption into MP4.

    Production features:
        - Ken Burns slow-zoom on every clip (configurable via KEN_BURNS_ZOOM)
        - Crossfade dissolve between segments (configurable via CROSSFADE_DURATION)
        - Background music mixed under narration (configurable via BG_MUSIC_VOLUME_DB)
        - Branded intro + outro sequences (configurable durations)

    Args:
        segments:      List of segment dicts (may contain a "caption" key).
        audio_files:   Ordered list of MP3 paths (one per segment).
        visual_files:  Ordered list of image (.jpg) or video (.mp4) paths.
        output_path:   Destination MP4 path. Auto-generated from title if None.
        title:         Used to generate a human-readable filename.
        music_path:    Optional path to a background music .mp3 file.

    Returns:
        Path to the written MP4 file.
    """
    if output_path is None:
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        slug = _slugify(title) if title else "video"
        output_path = f"{OUTPUT_DIR}/{slug}.mp4"

    cf = CROSSFADE_DURATION
    channel_name = _resolve_channel_name()

    # ── Intro ─────────────────────────────────────────────────────────────────
    intro_clip = _make_intro(channel_name, INTRO_DURATION)

    # ── Content segments ──────────────────────────────────────────────────────
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
                loops = int(duration / raw.duration) + 1
                raw = concatenate_videoclips([raw] * loops)
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

        # Ken Burns slow-zoom
        is_static = (ext != ".mp4")
        if KEN_BURNS_ZOOM > 0:
            base = _apply_ken_burns(base, duration, KEN_BURNS_ZOOM, is_static=is_static)

        # Caption as pre-rendered overlay (rendered ONCE, not per-frame)
        caption = segment.get("caption", "")
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

    # ── Outro ─────────────────────────────────────────────────────────────────
    outro_clip = _make_outro(channel_name, OUTRO_DURATION)

    # ── Assemble with crossfades ──────────────────────────────────────────────
    all_clips = []
    if intro_clip:
        all_clips.append(intro_clip)
    all_clips.extend(clips)
    if outro_clip:
        all_clips.append(outro_clip)

    logger.info("Concatenating %d clips (crossfade=%.1fs)", len(all_clips), cf)
    if cf > 0 and len(all_clips) > 1:
        # Apply crossfade-in to every clip except the first
        faded = [all_clips[0]]
        for c in all_clips[1:]:
            faded.append(c.crossfadein(cf))
        final = concatenate_videoclips(faded, padding=-cf, method="compose")
    else:
        final = concatenate_videoclips(all_clips, method="compose")

    # ── Mix background music ──────────────────────────────────────────────────
    if music_path and Path(music_path).is_file():
        logger.info("Mixing background music: %s at %d dB", music_path, BG_MUSIC_VOLUME_DB)
        music = AudioFileClip(music_path)
        # Loop music to match video length
        if music.duration < final.duration:
            loops = int(final.duration / music.duration) + 1
            from moviepy.editor import concatenate_audioclips
            music = concatenate_audioclips([music] * loops)
        music = music.subclip(0, final.duration)
        # Convert dB to linear volume multiplier
        music = music.volumex(10 ** (BG_MUSIC_VOLUME_DB / 20.0))
        # Fade music in/out
        music = music.audio_fadein(2.0).audio_fadeout(3.0)
        # Mix with existing narration
        if final.audio:
            final = final.set_audio(CompositeAudioClip([final.audio, music]))
        else:
            final = final.set_audio(music)

    logger.info("Encoding with %s (threads=%d)", _HW_CODEC, _THREADS)
    final.write_videofile(
        output_path,
        fps=_FPS,
        codec=_HW_CODEC,
        audio_codec="aac",
        threads=_THREADS,
        ffmpeg_params=_HW_PARAMS,
        logger=None,
    )
    logger.info("Video written to %s", output_path)
    return output_path
