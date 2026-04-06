"""audio_generator.py — Text-to-speech conversion.

Provider priority (controlled by TTS_PROVIDER env var):
  1. elevenlabs — paid, highest quality
  2. edge       — FREE Microsoft Edge Neural TTS, studio-quality (default)
  3. gtts       — FREE Google TTS, robotic but always works

Uses the strategy pattern via core.tts_providers for clean extensibility.
"""

import logging
from pathlib import Path

from config import (
    AUDIO_DIR, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID,
    GTTS_SPEECH_RATE, TTS_PROVIDER, EDGE_TTS_VOICE,
)
from core.tts_providers import ITTSProvider, create_tts_provider, EdgeTTSProvider
from voice_config import get_voice_settings

logger = logging.getLogger(__name__)


def _get_dashboard_edge_voice() -> str | None:
    """Read selected Edge TTS voice from dashboard settings (database)."""
    try:
        from database import get_settings
        settings = get_settings()
        if isinstance(settings, dict) and 'config' in settings:
            config = settings.get('config', {})
            if isinstance(config, dict):
                voice = config.get('edgeVoice')
                if voice:
                    logger.debug("Using Edge TTS voice from dashboard: %s", voice)
                    return voice
    except Exception as e:
        logger.debug("Could not read voice from dashboard settings: %s", e)
    return None



def _build_provider(edge_voice: str | None = None,
                   channel_slug: str | None = None,
                   language: str = "english") -> ITTSProvider:
    """Build the configured TTS provider using 3-tier voice hierarchy.
    
    Priority:
    1. edge_voice (video-level override)
    2. channel voice (channel-level setting)
    3. global voice (dashboard/env setting)
    4. language default
    
    Args:
        edge_voice: Video-level voice override
        channel_slug: YouTube channel slug (for channel-level voice lookup)
        language: Language code for default voice selection
    """
    try:
        from config import CHANNEL_LANGUAGE
        lang = CHANNEL_LANGUAGE or language or "english"
    except Exception:
        lang = language or "english"

    # Use the resolve_voice function for 3-tier hierarchy
    from voice_config import resolve_voice
    voice = resolve_voice(
        language=lang,
        channel_slug=channel_slug,
        video_voice_id=edge_voice
    )

    return create_tts_provider(
        TTS_PROVIDER or "edge",
        edge_voice=voice,
        elevenlabs_api_key=ELEVENLABS_API_KEY,
        elevenlabs_voice_id=ELEVENLABS_VOICE_ID,
        elevenlabs_voice_settings=get_voice_settings(),
        channel_language=lang,
        speech_rate=GTTS_SPEECH_RATE,
    )


def _build_fallback_provider(edge_voice: str | None = None,
                            channel_slug: str | None = None,
                            language: str = "english") -> ITTSProvider:
    """Build the Edge-TTS fallback provider using 3-tier voice hierarchy.
    
    Args:
        edge_voice: Video-level voice override
        channel_slug: YouTube channel slug
        language: Language code for default voice selection
    """
    from voice_config import resolve_voice
    voice = resolve_voice(
        language=language or "english",
        channel_slug=channel_slug,
        video_voice_id=edge_voice
    )
    return EdgeTTSProvider(voice=voice)


# ── Main entry point ─────────────────────────────────────────────────────────

def generate_audio_segments(
    segments: list[dict],
    out_dir: str = AUDIO_DIR,
    edge_voice: str | None = None,
    channel_slug: str | None = None,
    language: str = "english",
) -> list[str]:
    """Convert the narration text of each segment to an MP3 file.

    Uses the provider set in TTS_PROVIDER (.env) with 3-tier voice hierarchy:
    
    Priority:
    1. edge_voice (video-level override)
    2. channel voice (from channels table)
    3. global voice (dashboard settings or EDGE_TTS_VOICE env var)
    4. language default
    
    Falls back to Edge TTS on ElevenLabs quota error.

    Args:
        segments: List of segment dicts with 'narration' key
        out_dir: Output directory for MP3 files
        edge_voice: Video-level voice override (highest priority)
        channel_slug: YouTube channel slug for channel-level voice lookup
        language: Language code (english, hindi, urdu, hinglish) for defaults

    Returns:
        Ordered list of file paths matching the input segment order.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    provider = _build_provider(edge_voice=edge_voice, channel_slug=channel_slug, language=language)
    fallback = _build_fallback_provider(edge_voice=edge_voice, channel_slug=channel_slug, language=language)
    use_fallback = False

    paths: list[str] = []

    for i, segment in enumerate(segments):
        narration = segment.get("narration", "")
        if not narration:
            logger.warning("Segment %d has no narration — skipping", i)
            continue

        path = f"{out_dir}/seg_{i:03d}.mp3"
        active = fallback if use_fallback else provider

        try:
            logger.info("Generating audio (%s) for segment %d/%d",
                        active.name, i + 1, len(segments))
            active.generate(narration, path)
            paths.append(path)
        except Exception as e:
            # ElevenLabs quota/auth errors → switch to fallback for remaining
            err_str = str(e)
            if "quota" in err_str.lower() or "401" in err_str or "429" in err_str:
                logger.warning(
                    "%s quota/auth error — switching to %s for remaining %d segments: %s",
                    active.name, fallback.name, len(segments) - i, e,
                )
                use_fallback = True
                try:
                    fallback.generate(narration, path)
                    paths.append(path)
                except Exception as fe:
                    logger.error("Fallback also failed for segment %d: %s", i, fe)
            else:
                # Try fallback once for transient errors
                logger.warning("%s error: %s — trying fallback", active.name, e)
                try:
                    fallback.generate(narration, path)
                    paths.append(path)
                except Exception as fe:
                    logger.error("Both providers failed for segment %d: %s", i, fe)

    logger.info("Audio generation complete (%s): %d files written to %s",
                provider.name, len(paths), out_dir)
    return paths
