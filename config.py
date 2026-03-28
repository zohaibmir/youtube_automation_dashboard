"""config.py — Single source of truth for all environment settings.

Every module imports from here. No module should call os.getenv() directly.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")
YOUTUBE_CLIENT_SECRETS: str = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")

# ── Channel Settings ──────────────────────────────────────────────────────────
CHANNEL_NICHE: str = os.getenv("CHANNEL_NICHE", "personal finance")
CHANNEL_LANGUAGE: str = os.getenv("CHANNEL_LANGUAGE", "hinglish")
CHANNEL_AUDIENCE: str = os.getenv("CHANNEL_AUDIENCE", "South Asia and Gulf")
VIDEOS_PER_WEEK: int = int(os.getenv("VIDEOS_PER_WEEK", "5"))

# ── File Paths ────────────────────────────────────────────────────────────────
DB_PATH: str = os.getenv("DB_PATH", "yt_automation.db")
AUDIO_DIR: str = os.getenv("AUDIO_DIR", "audio")
IMAGES_DIR: str = os.getenv("IMAGES_DIR", "images")
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")

# ── YouTube Publish Settings ─────────────────────────────────────────────────
# Exported by the HTML dashboard → Settings → Export .env file
DEFAULT_VISIBILITY: str = os.getenv("DEFAULT_VISIBILITY", "public")   # public | unlisted | private
YOUTUBE_CATEGORY_ID: str = os.getenv("YOUTUBE_CATEGORY_ID", "22")      # 22=People&Blogs

# ── Voice / TTS ──────────────────────────────────────────────────────────────
# TTS provider priority: elevenlabs | edge | gtts
# "edge" uses Microsoft Edge Neural TTS — FREE, no API key, studio-quality voices
TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "edge")
# Edge-TTS voice name (run `edge-tts --list-voices` to browse)
# Popular: hi-IN-MadhurNeural (Hindi male), ur-PK-AsadNeural (Urdu male),
#          hi-IN-SwaraNeural (Hindi female), en-IN-PrabhatNeural (Indian English)
EDGE_TTS_VOICE: str = os.getenv("EDGE_TTS_VOICE", "ur-PK-AsadNeural")
# Match the sliders in the HTML dashboard → Settings → ElevenLabs → Voice tuning
VOICE_STABILITY: float = float(os.getenv("VOICE_STABILITY", "0.48"))
VOICE_SIMILARITY: float = float(os.getenv("VOICE_SIMILARITY", "0.82"))
VOICE_STYLE: float = float(os.getenv("VOICE_STYLE", "0.35"))
# gTTS fallback speed multiplier (0.8=slow, 1.0=normal, 1.25=fast)
# Requires ffmpeg. Set to 1.0 to disable post-processing.
GTTS_SPEECH_RATE: float = float(os.getenv("GTTS_SPEECH_RATE", "1.15"))

# ── Visual Mode ───────────────────────────────────────────────────────────────
# images = static Pexels images (default, fast)
# videos = Pexels video clips (better quality, larger downloads)
VISUAL_MODE: str = os.getenv("VISUAL_MODE", "images")  # images | videos

# ── Video Production ──────────────────────────────────────────────────────────
# Ken Burns slow-zoom percentage per clip (0.0 = disabled, 0.05 = 5% zoom)
KEN_BURNS_ZOOM: float = float(os.getenv("KEN_BURNS_ZOOM", "0.05"))
# Crossfade duration in seconds between segments (0 = hard cut)
CROSSFADE_DURATION: float = float(os.getenv("CROSSFADE_DURATION", "0.4"))
# Background music volume in dB relative to narration (negative = quieter)
BG_MUSIC_VOLUME_DB: float = float(os.getenv("BG_MUSIC_VOLUME_DB", "-8"))
# Path to background music .mp3 file (empty = no music)
BG_MUSIC_PATH: str = os.getenv("BG_MUSIC_PATH", "")
# Branded intro duration in seconds (0 = no intro)
INTRO_DURATION: float = float(os.getenv("INTRO_DURATION", "4"))
# Outro duration in seconds with subscribe CTA (0 = no outro)
OUTRO_DURATION: float = float(os.getenv("OUTRO_DURATION", "5"))

# ── Model & API Constants ─────────────────────────────────────────────────────
CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
YOUTUBE_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
