"""core/tts_providers.py — TTS provider strategy pattern (Open/Closed Principle).

Each provider implements ITTSProvider. New providers can be added
without modifying existing code — just register a new class.

Usage:
    provider = create_tts_provider("edge")
    provider.generate("Hello world", "/tmp/audio.mp3")
"""

import asyncio
import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class ITTSProvider(ABC):
    """Interface for text-to-speech providers."""

    @abstractmethod
    def generate(self, text: str, output_path: str) -> None:
        """Generate audio from text and save to output_path."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""


class EdgeTTSProvider(ITTSProvider):
    """Microsoft Edge Neural TTS — free, high quality."""

    def __init__(self, voice: str = "en-US-ChristopherNeural"):
        self._voice = voice

    @property
    def name(self) -> str:
        return f"Edge-TTS ({self._voice})"

    def generate(self, text: str, output_path: str) -> None:
        import time as _time
        import edge_tts

        async def _gen():
            for attempt in range(2):
                try:
                    comm = edge_tts.Communicate(text, self._voice)
                    await comm.save(output_path)
                    return
                except Exception as e:
                    if attempt == 0 and "503" in str(e):
                        logger.warning("Edge-TTS 503 — retrying in 3s…")
                        _time.sleep(3)
                        continue
                    raise

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(lambda: asyncio.run(_gen())).result()
        else:
            asyncio.run(_gen())


class ElevenLabsProvider(ITTSProvider):
    """ElevenLabs API — paid, highest quality."""

    def __init__(self, api_key: str, voice_id: str, voice_settings=None,
                 model_id: str = "eleven_multilingual_v2"):
        from elevenlabs.client import ElevenLabs
        self._client = ElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._voice_settings = voice_settings
        self._model_id = model_id

    @property
    def name(self) -> str:
        return "ElevenLabs"

    def generate(self, text: str, output_path: str) -> None:
        audio_stream = self._client.text_to_speech.convert(
            voice_id=self._voice_id,
            text=text,
            model_id=self._model_id,
            voice_settings=self._voice_settings,
        )
        with open(output_path, "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)


class GTTSProvider(ITTSProvider):
    """Google TTS — free, basic quality."""

    def __init__(self, lang: str = "hi", speech_rate: float = 1.0):
        self._lang = lang
        self._rate = max(0.5, min(2.0, speech_rate))

    @property
    def name(self) -> str:
        return f"gTTS ({self._lang})"

    def generate(self, text: str, output_path: str) -> None:
        import os
        import shutil
        from gtts import gTTS

        tts = gTTS(text=text, lang=self._lang, slow=False)
        tts.timeout = 15

        if abs(self._rate - 1.0) < 0.01:
            tts.save(output_path)
            return

        tmp = output_path + ".raw.mp3"
        tts.save(tmp)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", tmp, "-filter:a", f"atempo={self._rate}", "-vn", output_path],
                capture_output=True, check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            shutil.move(tmp, output_path)
            logger.warning("ffmpeg unavailable for speed adjustment — raw gTTS speed")
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


# ── Provider factory ──────────────────────────────────────────────────────────

_GTTS_LANG_MAP = {
    "hindi": "hi", "urdu": "ur", "hinglish": "hi", "english": "en",
}


def create_tts_provider(
    provider_name: str,
    *,
    edge_voice: str = "en-US-ChristopherNeural",
    elevenlabs_api_key: str = "",
    elevenlabs_voice_id: str = "",
    elevenlabs_voice_settings=None,
    channel_language: str = "hinglish",
    speech_rate: float = 1.0,
) -> ITTSProvider:
    """Factory: create a TTS provider by name.

    Adding a new provider requires only a new class + entry in this factory.
    Existing code (audio_generator, pipeline) remains unchanged (OCP).
    """
    name = (provider_name or "edge").lower().strip()

    if name == "elevenlabs" and elevenlabs_api_key:
        try:
            return ElevenLabsProvider(
                api_key=elevenlabs_api_key,
                voice_id=elevenlabs_voice_id,
                voice_settings=elevenlabs_voice_settings,
            )
        except Exception:
            logger.warning("ElevenLabs unavailable — falling back to Edge-TTS")
            name = "edge"

    if name in ("elevenlabs", "edge"):
        return EdgeTTSProvider(voice=edge_voice)

    # gTTS as last resort
    lang = _GTTS_LANG_MAP.get(channel_language.lower(), "hi")
    return GTTSProvider(lang=lang, speech_rate=speech_rate)
