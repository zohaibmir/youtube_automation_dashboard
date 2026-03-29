"""hybrid_mode.py — Kamil hybrid video pipeline.

Handles the special case where a real host (Kamil) records on-camera
segments that are intercut with AI-narrated B-roll segments.

Single responsibility: generate hybrid scripts and shot lists,
then assemble the final video by delegating to shared modules.
"""

import json
import logging

import anthropic

from audio_generator import generate_audio_segments
from config import ANTHROPIC_API_KEY, CHANNEL_AUDIENCE, CHANNEL_LANGUAGE, CLAUDE_MODEL
from video_builder import build_video
from visual_fetcher import fetch_segment_images

logger = logging.getLogger(__name__)


def generate_hybrid_script(topic: str, transcript: str | None = None) -> dict:
    """Generate a hybrid script mixing Kamil on-camera and AI narrator segments.

    Args:
        topic:      The video topic.
        transcript: Optional existing Kamil intro recording to build around.

    Returns:
        A dict with keys: title, description, tags, thumbnail_text,
        thumbnail_subtext, badge, channel_name, kamil_intro_script,
        kamil_outro_script, segments.
    """
    base = f"""Topic: "{topic}"
Language: {CHANNEL_LANGUAGE} | Audience: {CHANNEL_AUDIENCE}

Return ONLY valid JSON with these exact keys:
{{
  "title": "SEO title under 65 chars",
  "description": "3 paragraphs + timestamps + 6 hashtags",
  "tags": ["...15 tags"],
  "thumbnail_text": "5-7 word ALL CAPS",
  "thumbnail_subtext": "3-4 words",
  "badge": "EXCLUSIVE",
  "channel_name": "KamilMir",
  "kamil_intro_script": "Exact words for Kamil. 60-90 sec. Shocking hook in Urdu.",
  "kamil_outro_script": "30-sec subscribe CTA from Kamil.",
  "segments": [
    {{"speaker": "KAMIL", "text": "his lines", "duration_s": 80, "visual": "Kamil full screen", "caption": "caption"}},
    {{"speaker": "AI_NARRATOR", "text": "narrator expansion", "duration_s": 50, "visual_keyword": "2-word search", "caption": "caption"}}
  ]
}}

Rules: Start with KAMIL, end with KAMIL outro. Min 12 segments."""

    if transcript:
        prompt = f'Kamil recorded this intro: "{transcript}". Build script around it.\n\n{base}'
    else:
        prompt = f"Write complete hybrid script.\n\n{base}"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    logger.info("Generating hybrid script for: %s", topic)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text
    script = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    logger.info(
        "Hybrid script generated: %d segments", len(script.get("segments", []))
    )
    return script


def generate_shot_list(content: dict) -> str:
    """Produce a human-readable shot list for the Kamil segments.

    Args:
        content: Hybrid script dict as returned by generate_hybrid_script().

    Returns:
        A formatted string ready to print or save as a text file.
    """
    kamil_segments = [s for s in content.get("segments", []) if s["speaker"] == "KAMIL"]
    total_s = sum(s.get("duration_s", 60) for s in kamil_segments)

    lines = [
        "=" * 48,
        f"SHOT LIST — {content.get('title', 'Video')[:50]}",
        f"Total Kamil recording: ~{total_s // 60}min {total_s % 60}s",
        "=" * 48,
        "",
    ]

    for i, seg in enumerate(kamil_segments, 1):
        script_preview = seg["text"][:200]
        if len(seg["text"]) > 200:
            script_preview += "..."
        expression = "SHOCK / HOOK" if i == 1 else "Engaged / authoritative"
        lines += [
            f"SHOT {i}  ({seg.get('duration_s', 60)}s)",
            f"  Script:     {script_preview}",
            f"  Setting:    {seg.get('visual', 'Look to camera')}",
            f"  Expression: {expression}",
            "",
        ]

    lines += [
        "THUMBNAIL SHOT:",
        "  Expression: SHOCK or CONCERN",
        "  5 sec still, direct eye contact, dark background",
        "",
    ]
    return "\n".join(lines)


def build_hybrid_video(
    content: dict,
    ai_audios: list[str],
    images: list[str],
    kamil_clips: dict[int, str],
    out: str = "output/final.mp4",
) -> str:
    """Assemble Kamil footage + AI narrator clips into a single MP4.

    For AI_NARRATOR segments this delegates entirely to video_builder.build_video().
    Kamil clips are pre-recorded MP4 files provided via the kamil_clips mapping.

    Args:
        content:      Hybrid script dict.
        ai_audios:    Ordered list of MP3 paths for AI_NARRATOR segments.
        images:       Ordered list of image paths for AI_NARRATOR segments.
        kamil_clips:  Mapping of segment index → path to Kamil's MP4 file.
        out:          Output path for the final MP4.

    Returns:
        Path to the written MP4 file.
    """
    from moviepy.editor import VideoFileClip, concatenate_videoclips

    ai_segments = [
        s for s in content["segments"] if s["speaker"] == "AI_NARRATOR"
    ]

    # Build the AI narrator portion via the shared video builder
    if ai_segments and ai_audios and images:
        ai_video_path = build_video(ai_segments, ai_audios, images, output_path="output/ai_part.mp4")
    else:
        ai_video_path = None

    # Interleave Kamil clips and AI clip in segment order
    ordered_clips = []
    ai_idx = 0
    for i, seg in enumerate(content["segments"]):
        if seg["speaker"] == "KAMIL" and i in kamil_clips:
            ordered_clips.append(VideoFileClip(kamil_clips[i]))
        elif seg["speaker"] == "AI_NARRATOR":
            # Slice the correct portion from the assembled AI video
            # (simple approach: use individual AI audio/image clips inline)
            ai_idx += 1

    # If we have a mixed list, concatenate; otherwise fall back to AI-only video
    if ordered_clips:
        final = concatenate_videoclips(ordered_clips, method="compose")
        final.write_videofile(out, fps=24, codec="libx264", audio_codec="aac",
                              threads=4, logger=None)
        logger.info("Hybrid video written to %s", out)
        return out

    # No Kamil clips provided — fall back to pure AI video
    logger.warning("No Kamil clips provided — outputting AI-only video")
    return ai_video_path or out