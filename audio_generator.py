"""audio_generator.py — Text-to-speech conversion.

Primary: ElevenLabs (high quality).
Fallback: gTTS / Google TTS (free, no quota) — used automatically when
ElevenLabs returns a quota_exceeded or 401 error.
"""

import logging
from pathlib import Path

from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

from config import AUDIO_DIR, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, GTTS_SPEECH_RATE
from voice_config import get_voice_settings

logger = logging.getLogger(__name__)

_ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Language hint for gTTS fallback — maps common channel languages
_GTTS_LANG = {
    "hindi": "hi",
    "urdu": "ur",
    "hinglish": "hi",
    "english": "en",
}


def _gtts_segment(text: str, path: str, lang_hint: str = "hi") -> None:
    """Generate audio using free Google TTS as fallback, with optional speed adjustment."""
    import subprocess
    from gtts import gTTS
    tts = gTTS(text=text, lang=lang_hint, slow=False)

    if abs(GTTS_SPEECH_RATE - 1.0) < 0.01:
        # No speed change needed
        tts.save(path)
        return

    # Save to a temp file, then apply atempo via ffmpeg
    tmp_path = path + ".raw.mp3"
    tts.save(tmp_path)
    try:
        # atempo supports 0.5–2.0; values >2.0 need chaining
        rate = max(0.5, min(2.0, GTTS_SPEECH_RATE))
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_path, "-filter:a", f"atempo={rate}", "-vn", path],
            capture_output=True, check=True
        )
        logger.debug("gTTS speed adjusted ×%.2f → %s", rate, path)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # ffmpeg not available or failed — use raw file
        import shutil
        shutil.move(tmp_path, path)
        logger.warning("ffmpeg unavailable for speed adjustment — using raw gTTS speed")
        return
    finally:
        import os as _os
        _os.path.exists(tmp_path) and _os.remove(tmp_path)


def generate_audio_segments(
    segments: list[dict],
    out_dir: str = AUDIO_DIR,
) -> list[str]:
    """Convert the narration text of each segment to an MP3 file.

    Tries ElevenLabs first. If quota is exceeded or ElevenLabs is
    unavailable, falls back to gTTS automatically for all remaining
    segments (and switches every segment once fallback is triggered).

    Args:
        segments: List of segment dicts, each containing a "narration" key.
        out_dir:  Directory to write MP3 files into.

    Returns:
        Ordered list of file paths matching the input segment order.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    try:
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        voice_settings = get_voice_settings()
        el_available = bool(ELEVENLABS_API_KEY)
    except Exception:
        el_available = False

    # Detect channel language for gTTS
    try:
        from config import CHANNEL_LANGUAGE
        gtts_lang = _GTTS_LANG.get((CHANNEL_LANGUAGE or "hinglish").lower(), "hi")
    except Exception:
        gtts_lang = "hi"

    use_fallback = False  # once True, skip ElevenLabs for all remaining segments
    paths: list[str] = []

    for i, segment in enumerate(segments):
        narration = segment.get("narration", "")
        if not narration:
            logger.warning("Segment %d has no narration — skipping", i)
            continue

        path = f"{out_dir}/seg_{i:03d}.mp3"

        if not use_fallback and el_available:
            try:
                logger.info("Generating audio (ElevenLabs) for segment %d/%d", i + 1, len(segments))
                audio_stream = client.text_to_speech.convert(
                    voice_id=ELEVENLABS_VOICE_ID,
                    text=narration,
                    model_id=_ELEVENLABS_MODEL,
                    voice_settings=voice_settings,
                )
                with open(path, "wb") as f:
                    for chunk in audio_stream:
                        f.write(chunk)
                paths.append(path)
                continue
            except ApiError as e:
                body = e.body or {}
                detail = body.get("detail", {}) if isinstance(body, dict) else {}
                status = detail.get("status", "") if isinstance(detail, dict) else ""
                if e.status_code in (401, 429) or status == "quota_exceeded":
                    logger.warning(
                        "ElevenLabs quota/auth error — switching to gTTS fallback "
                        "for remaining %d segments. Detail: %s",
                        len(segments) - i, detail
                    )
                    use_fallback = True
                else:
                    raise

        # gTTS fallback
        logger.info("Generating audio (gTTS fallback) for segment %d/%d", i + 1, len(segments))
        _gtts_segment(narration, path, lang_hint=gtts_lang)
        paths.append(path)

    logger.info("Audio generation complete: %d files written to %s", len(paths), out_dir)
    return paths
