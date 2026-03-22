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

# ── Voice Tuning ─────────────────────────────────────────────────────────────
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

# ── Model & API Constants ─────────────────────────────────────────────────────
CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
YOUTUBE_SCOPES: list[str] = ["https://www.googleapis.com/auth/youtube.upload"]
