# ElevenLabs voice IDs for South Asian content:
# JBFqnCBsd6RMkjVDRZzb  George  - clear English, authoritative
# TX3LPaxmHKxFdv7VOQHJ  Liam    - young, energetic
# pNInz6obpgDQGcFmaJgB  Adam    - deep, serious
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