"""audio_generator.py — Text-to-speech conversion.

Provider priority (controlled by TTS_PROVIDER env var):
  1. elevenlabs — paid, highest quality
  2. edge       — FREE Microsoft Edge Neural TTS, studio-quality (default)
  3. gtts       — FREE Google TTS, robotic but always works

Uses the strategy pattern via core.tts_providers for clean extensibility.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    total = len(segments)

    def _gen_one(i: int, segment: dict) -> tuple[int, str | None]:
        """Generate audio for a single segment; fall back to secondary provider on error."""
        narration = segment.get("narration", "")
        if not narration:
            logger.warning("Segment %d has no narration — skipping", i)
            return i, None
        path = f"{out_dir}/seg_{i:03d}.mp3"
        for active in (provider, fallback):
            try:
                logger.info("Generating audio (%s) segment %d/%d", active.name, i + 1, total)
                active.generate(narration, path)
                return i, path
            except Exception as e:
                err_str = str(e)
                if "quota" in err_str.lower() or "401" in err_str or "429" in err_str:
                    logger.warning("%s quota/auth — falling back for segment %d: %s", active.name, i, e)
                else:
                    logger.warning("%s error for segment %d: %s — trying fallback", active.name, i, e)
        logger.error("All providers failed for segment %d", i)
        return i, None

    # Run up to 4 TTS calls in parallel — edge-tts is network I/O so this gives
    # ~3-4× speedup on 11-segment scripts with no extra CPU cost.
    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_gen_one, i, seg): i for i, seg in enumerate(segments)}
        for future in as_completed(futures):
            i, path = future.result()
            if path:
                results[i] = path

    paths = [results[i] for i in range(total) if i in results]
    logger.info("Audio generation complete (%s): %d/%d files written to %s",
                provider.name, len(paths), total, out_dir)
    return paths
