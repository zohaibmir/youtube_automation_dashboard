"""audio_generator.py — Text-to-speech conversion.

Provider priority (controlled by TTS_PROVIDER env var):
  1. elevenlabs — paid, highest quality
  2. edge       — FREE Microsoft Edge Neural TTS, studio-quality (default)
  3. gtts       — FREE Google TTS, robotic but always works
"""

import asyncio
import logging
from pathlib import Path

from config import (
    AUDIO_DIR, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID,
    GTTS_SPEECH_RATE, TTS_PROVIDER, EDGE_TTS_VOICE,
)
from voice_config import get_voice_settings

logger = logging.getLogger(__name__)

_ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Language hint for gTTS fallback
_GTTS_LANG = {
    "hindi": "hi",
    "urdu": "ur",
    "hinglish": "hi",
    "english": "en",
}


# ── Edge-TTS (free, high quality) ────────────────────────────────────────────

def _edge_tts_segment(text: str, path: str, voice: str = EDGE_TTS_VOICE) -> None:
    """Generate audio using Microsoft Edge Neural TTS (free, no API key).

    Retries once on transient 503 errors from the WebSocket endpoint.
    """
    import time as _time
    import edge_tts

    async def _generate():
        for attempt in range(2):
            try:
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(path)
                return
            except Exception as e:
                if attempt == 0 and "503" in str(e):
                    logger.warning("Edge-TTS 503 — retrying in 3s…")
                    _time.sleep(3)
                    continue
                raise

    # edge-tts is async — run in a new event loop if needed
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pool.submit(lambda: asyncio.run(_generate())).result()
    else:
        asyncio.run(_generate())


# ── gTTS (free, basic quality) ───────────────────────────────────────────────

def _gtts_segment(text: str, path: str, lang_hint: str = "hi") -> None:
    """Generate audio using free Google TTS as fallback, with optional speed adjustment."""
    import subprocess
    from gtts import gTTS
    tts = gTTS(text=text, lang=lang_hint, slow=False)
    tts.timeout = 15  # prevent indefinite hang on Google's TTS endpoint

    if abs(GTTS_SPEECH_RATE - 1.0) < 0.01:
        tts.save(path)
        return

    tmp_path = path + ".raw.mp3"
    tts.save(tmp_path)
    try:
        rate = max(0.5, min(2.0, GTTS_SPEECH_RATE))
        subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_path, "-filter:a", f"atempo={rate}", "-vn", path],
            capture_output=True, check=True
        )
        logger.debug("gTTS speed adjusted ×%.2f → %s", rate, path)
    except (subprocess.CalledProcessError, FileNotFoundError):
        import shutil
        shutil.move(tmp_path, path)
        logger.warning("ffmpeg unavailable for speed adjustment — using raw gTTS speed")
        return
    finally:
        import os as _os
        if _os.path.exists(tmp_path):
            _os.remove(tmp_path)


# ── Main entry point ─────────────────────────────────────────────────────────

def generate_audio_segments(
    segments: list[dict],
    out_dir: str = AUDIO_DIR,
) -> list[str]:
    """Convert the narration text of each segment to an MP3 file.

    Uses the provider set in TTS_PROVIDER (.env):
      - "elevenlabs" → ElevenLabs API (falls back to edge on quota error)
      - "edge"       → Microsoft Edge Neural TTS (free, default)
      - "gtts"       → Google TTS (free, basic)

    Returns:
        Ordered list of file paths matching the input segment order.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    provider = (TTS_PROVIDER or "edge").lower().strip()

    # Detect channel language for gTTS
    try:
        from config import CHANNEL_LANGUAGE
        gtts_lang = _GTTS_LANG.get((CHANNEL_LANGUAGE or "hinglish").lower(), "hi")
    except Exception:
        gtts_lang = "hi"

    # Prepare ElevenLabs client if needed
    el_available = False
    client = None
    voice_settings = None
    if provider == "elevenlabs" and ELEVENLABS_API_KEY:
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            voice_settings = get_voice_settings()
            el_available = True
        except Exception:
            logger.warning("ElevenLabs unavailable — falling back to edge-tts")
            provider = "edge"

    el_fallback = False  # once True, skip ElevenLabs for remaining segments
    paths: list[str] = []

    for i, segment in enumerate(segments):
        narration = segment.get("narration", "")
        if not narration:
            logger.warning("Segment %d has no narration — skipping", i)
            continue

        path = f"{out_dir}/seg_{i:03d}.mp3"

        # ── ElevenLabs ────────────────────────────────────────────
        if provider == "elevenlabs" and el_available and not el_fallback:
            try:
                logger.info("Generating audio (ElevenLabs) for segment %d/%d", i + 1, len(segments))
                from elevenlabs.core.api_error import ApiError
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
                        "ElevenLabs quota/auth error — switching to edge-tts "
                        "for remaining %d segments. Detail: %s",
                        len(segments) - i, detail
                    )
                    el_fallback = True
                else:
                    raise
            except Exception as e:
                logger.warning("ElevenLabs error: %s — switching to edge-tts", e)
                el_fallback = True

        # ── Edge-TTS (default / fallback from ElevenLabs) ────────
        if provider in ("elevenlabs", "edge"):
            try:
                logger.info("Generating audio (Edge-TTS %s) for segment %d/%d",
                            EDGE_TTS_VOICE, i + 1, len(segments))
                _edge_tts_segment(narration, path, voice=EDGE_TTS_VOICE)
                paths.append(path)
                continue
            except Exception as e:
                logger.warning("Edge-TTS failed: %s — falling back to gTTS", e)

        # ── gTTS (last resort) ───────────────────────────────────
        logger.info("Generating audio (gTTS fallback) for segment %d/%d", i + 1, len(segments))
        _gtts_segment(narration, path, lang_hint=gtts_lang)
        paths.append(path)

    logger.info("Audio generation complete (%s): %d files written to %s",
                provider, len(paths), out_dir)
    return paths
