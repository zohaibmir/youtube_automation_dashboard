"""video_builder.py — MoviePy video assembly.

Single responsibility: combine image/video clips, audio, and captions
into a final MP4 file. Supports Ken Burns zoom, crossfade transitions,
background music mixing, and branded intro/outro sequences.
"""

import logging
import os
import subprocess
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
    AUTO_END_SCREENS,
    BG_MUSIC_VOLUME_DB,
    CHANNEL_NAME,
    CROSSFADE_DURATION,
    END_SCREEN_DURATION,
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

    preset=fast gives ~60% smaller files than ultrafast with negligible
    extra encode time. CRF 23 is libx264's default — still excellent
    quality for YouTube (which re-encodes everything on ingest anyway).
    Targets ~6–8 Mbps for 1080p, matching YouTube's own upload guidelines.
    """
    return "libx264", ["-preset", "fast", "-crf", "23"]


_HW_CODEC, _HW_PARAMS = _detect_hw_encoder()
logger.info("Video encoder: %s %s", _HW_CODEC, _HW_PARAMS)


def _ffmpeg_prepare_video(src_path: str, duration: float) -> str:
    """Pre-process a video clip to target resolution via FFmpeg.

    Uses native FFmpeg scale+crop+loop — avoids per-frame Python PIL
    resize/crop in MoviePy, which is the main encoding bottleneck.
    Returns path to the normalised temp file (or original on failure).
    """
    src = Path(src_path)
    out = src.parent / f"_norm_{src.stem}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return str(out)

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",          # loop source if shorter than duration
        "-i", str(src),
        "-t", str(duration),
        "-vf", (
            f"scale={_VIDEO_WIDTH}:{_VIDEO_HEIGHT}"
            f":force_original_aspect_ratio=increase,"
            f"crop={_VIDEO_WIDTH}:{_VIDEO_HEIGHT}"
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-an",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    if result.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        logger.warning("FFmpeg pre-process failed for %s — using original", src_path)
        return src_path
    return str(out)
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


def _make_end_screen(channel_name: str, duration: float):
    """Create a YouTube-style end screen burned into the last N seconds of the video.

    Renders a static frame with:
      - "Thanks for watching!" header
      - Left: watch-next placeholder box with play icon
      - Right: red subscribe circle + channel name

    No API calls needed — baked directly into the video file.
    """
    if duration <= 0:
        return None

    W, H = _VIDEO_WIDTH, _VIDEO_HEIGHT
    img = Image.new("RGB", (W, H), (8, 8, 12))
    draw = ImageDraw.Draw(img)

    font_hdr = _get_font(60)
    font_med = _get_font(36)
    font_sm  = _get_font(26)
    font_xs  = _get_font(20)

    cx, cy = W // 2, H // 2

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = "Thanks for watching!"
    bb = draw.textbbox((0, 0), hdr, font=font_hdr)
    draw.text(((W - (bb[2] - bb[0])) // 2, 70), hdr, font=font_hdr, fill=(255, 255, 255))

    # Accent line below header
    line_y = 70 + (bb[3] - bb[1]) + 18
    draw.line([(cx - 280, line_y), (cx + 280, line_y)], fill=(124, 109, 250), width=2)

    # ── Left: "Watch Next" placeholder box ────────────────────────────────────
    bx1, by1, bx2, by2 = cx - 490, cy - 130, cx - 30, cy + 130
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=12,
                           fill=(20, 20, 32), outline=(70, 70, 100), width=2)
    # Play triangle
    tri_x = bx1 + 45
    tri_cy = (by1 + by2) // 2
    draw.polygon(
        [(tri_x, tri_cy - 32), (tri_x + 52, tri_cy), (tri_x, tri_cy + 32)],
        fill=(200, 200, 210)
    )
    wn = "Watch Next"
    bb_wn = draw.textbbox((0, 0), wn, font=font_sm)
    mid_bx = (bx1 + bx2) // 2
    draw.text((mid_bx - (bb_wn[2] - bb_wn[0]) // 2, by2 - 55),
              wn, font=font_sm, fill=(180, 180, 200))

    # ── Right: Subscribe circle ────────────────────────────────────────────────
    scx, scy, sr = cx + 295, cy - 20, 115
    draw.ellipse([scx - sr, scy - sr, scx + sr, scy + sr], fill=(200, 20, 20))
    draw.ellipse([scx - sr + 6, scy - sr + 6, scx + sr - 6, scy + sr - 6], fill=(230, 0, 0))
    sub_txt = "SUBSCRIBE"
    bb_sub = draw.textbbox((0, 0), sub_txt, font=font_xs)
    draw.text(
        (scx - (bb_sub[2] - bb_sub[0]) // 2, scy - (bb_sub[3] - bb_sub[1]) // 2),
        sub_txt, font=font_xs, fill=(255, 255, 255)
    )
    # Channel name below circle
    bb_ch = draw.textbbox((0, 0), channel_name, font=font_sm)
    draw.text((scx - (bb_ch[2] - bb_ch[0]) // 2, scy + sr + 18),
              channel_name, font=font_sm, fill=(210, 210, 220))
    # CTA tagline
    cta = OUTRO_CTA_TEXT
    bb_cta = draw.textbbox((0, 0), cta, font=font_xs)
    draw.text((scx - (bb_cta[2] - bb_cta[0]) // 2, scy + sr + 58),
              cta, font=font_xs, fill=(140, 140, 155))

    clip = ImageClip(np.array(img)).set_duration(duration)
    clip = clip.crossfadeout(min(2.5, duration * 0.12))
    return clip


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
            # ── Video clip — FFmpeg normalises to 1920×1080 (no Python per-frame resize)
            try:
                norm_path = _ffmpeg_prepare_video(visual_path, duration)
                raw = VideoFileClip(norm_path, audio=False)
                if raw.duration < duration - 0.05:
                    loops = int(duration / raw.duration) + 1
                    raw = concatenate_videoclips([raw] * loops)
                base = raw.subclip(0, duration)
            except Exception as exc:
                logger.warning(
                    "Corrupted/unreadable visual clip '%s' at segment %d — using fallback color clip: %s",
                    visual_path,
                    i,
                    exc,
                )
                # Keep pipeline alive even if one downloaded stock clip is broken.
                base = ColorClip(size=(_VIDEO_WIDTH, _VIDEO_HEIGHT), color=(18, 22, 30)).set_duration(duration)
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

        # Ken Burns slow-zoom — only on static images (video clips have natural motion;
        # applying it would require per-frame Python PIL resize calls, killing performance)
        is_static = (ext != ".mp4")
        if KEN_BURNS_ZOOM > 0 and is_static:
            base = _apply_ken_burns(base, duration, KEN_BURNS_ZOOM, is_static=True)

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

    # ── Outro / End Screen ─────────────────────────────────────────────────────
    if AUTO_END_SCREENS:
        outro_clip = _make_end_screen(channel_name, END_SCREEN_DURATION)
        logger.info("Using burned-in end screen (%ds)", END_SCREEN_DURATION)
    else:
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
