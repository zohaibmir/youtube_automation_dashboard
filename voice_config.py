# ElevenLabs voice IDs for global English content:
# JBFqnCBsd6RMkjVDRZzb  George  - clear English, authoritative (ideal for politics/news)
# TX3LPaxmHKxFdv7VOQHJ  Liam    - young, energetic (good for viral/trending)
# pNInz6obpgDQGcFmaJgB  Adam    - deep, serious (great for religion/geopolitics)
# nPczCjzI2devNBz1zQrb  Brian   - calm, professional (documentary style)
# Custom: upload 30min voice sample to ElevenLabs to clone
#
# Values are read from .env (exported by the HTML dashboard Settings panel).
# Defaults match the slider defaults in the HTML.

from config import VOICE_SIMILARITY, VOICE_STABILITY, VOICE_STYLE


def get_voice_settings() -> dict:
    return {
        "stability": VOICE_STABILITY,
        "similarity_boost": VOICE_SIMILARITY,
        "style": VOICE_STYLE,
        "use_speaker_boost": True,
    }