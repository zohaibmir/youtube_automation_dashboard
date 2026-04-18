"""config.py — Single source of truth for all environment settings.

Every module imports from here. No module should call os.getenv() directly.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _is_hosted_environment() -> bool:
    return bool(
        os.getenv("RENDER")
        or os.getenv("RENDER_SERVICE_ID")
        or os.getenv("RENDER_EXTERNAL_URL")
    )


def _storage_root() -> str:
    configured_root = os.getenv("DATA_ROOT", "").strip()
    if configured_root:
        return configured_root
    if _is_hosted_environment() and os.path.isdir("/data"):
        return "/data"
    return ""


def _resolve_storage_path(env_name: str, default_name: str) -> str:
    configured = os.getenv(env_name, "").strip()
    if configured:
        candidate = configured
    else:
        root = _storage_root()
        candidate = os.path.join(root, default_name) if root else default_name

    if _is_hosted_environment() and (candidate == "/app" or candidate.startswith("/app/")):
        root = _storage_root() or "/tmp"
        suffix = candidate.removeprefix("/app/").strip()
        candidate = os.path.join(root, suffix) if suffix else root

    return os.path.normpath(candidate)

# ── API Keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")
YOUTUBE_CLIENT_SECRETS: str = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")

# ── Channel Settings ──────────────────────────────────────────────────────────
CHANNEL_NAME: str = os.getenv("CHANNEL_NAME", "")  # Display name for intro/outro
CHANNEL_NICHE: str = os.getenv("CHANNEL_NICHE", "politics and religion")
CHANNEL_LANGUAGE: str = os.getenv("CHANNEL_LANGUAGE", "english")
CHANNEL_AUDIENCE: str = os.getenv("CHANNEL_AUDIENCE", "global")
VIDEOS_PER_WEEK: int = int(os.getenv("VIDEOS_PER_WEEK", "5"))
SCHEDULER_PUBLISH_TIME: str = os.getenv("SCHEDULER_PUBLISH_TIME", "14:00")
SCHEDULER_PUBLISH_TIMES: str = os.getenv("SCHEDULER_PUBLISH_TIMES", "")
SCHEDULER_CHANNEL: str | None = os.getenv("SCHEDULER_CHANNEL", "").strip() or None
# Shorts to generate for scheduler / run-next jobs (0-3)
SCHEDULER_SHORTS_COUNT: int = int(os.getenv("SCHEDULER_SHORTS_COUNT", "2"))
# Encoder threads for MoviePy/FFmpeg.
# On Render (shared 0.1 CPU) default to 1 — extra threads cause context-switch overhead.
_default_threads = "1" if _is_hosted_environment() else "4"
FFMPEG_THREADS: int = max(1, int(os.getenv("FFMPEG_THREADS", _default_threads)))
# FFmpeg encoding preset. On Render use ultrafast — YouTube re-encodes on ingest anyway,
# so quality loss is irrelevant and encode time drops ~4×.
_default_preset = "ultrafast" if _is_hosted_environment() else "fast"
FFMPEG_PRESET: str = os.getenv("FFMPEG_PRESET", _default_preset)

# ── File Paths ────────────────────────────────────────────────────────────────
DB_PATH: str = _resolve_storage_path("DB_PATH", "yt_automation.db")
AUDIO_DIR: str = _resolve_storage_path("AUDIO_DIR", "audio")
IMAGES_DIR: str = _resolve_storage_path("IMAGES_DIR", "images")
OUTPUT_DIR: str = _resolve_storage_path("OUTPUT_DIR", "output")

# ── YouTube Publish Settings ─────────────────────────────────────────────────
# Exported by the HTML dashboard → Settings → Export .env file
DEFAULT_VISIBILITY: str = os.getenv("DEFAULT_VISIBILITY", "public")   # public | unlisted | private
YOUTUBE_CATEGORY_ID: str = os.getenv("YOUTUBE_CATEGORY_ID", "25")      # 25=News&Politics

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

# ── Kling AI (animated visuals) ─────────────────────────────────────────────
# Sign up at https://klingai.com/dev → create an API key pair.
# Used when VISUAL_MODE=animated to generate per-segment AI animation clips.
KLING_API_KEY: str = os.getenv("KLING_API_KEY", "")
KLING_API_SECRET: str = os.getenv("KLING_API_SECRET", "")

# ── Visual Mode ───────────────────────────────────────────────────────────────
# images   = static Pexels images (default, fast, free)
# videos   = Pexels MP4 clips (better quality, free)
# animated = Kling AI generated animation per segment (~$0.14/clip, requires KLING_API_KEY)
VISUAL_MODE: str = os.getenv("VISUAL_MODE", "images")  # images | videos | animated

# COMPANION Shorts visual mode override (defaults to VISUAL_MODE if not set)
# This ONLY affects the 2 companion shorts extracted FROM each main video.
# Set SHORTS_VISUAL_MODE=animated to use Kling AI for companion shorts while keeping
# main videos on Pexels. Cost-effective: ~3-4 clips/short vs 8-10/video.
# NOTE: Standalone animated shorts (via /api/shorts/generate-animated) ALWAYS use Kling.
SHORTS_VISUAL_MODE: str = os.getenv("SHORTS_VISUAL_MODE", VISUAL_MODE)

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
# Intro placement: off | start | end
# Default is end so videos begin immediately with content.
INTRO_POSITION: str = os.getenv("INTRO_POSITION", "end").strip().lower()
# Outro duration in seconds with subscribe CTA (0 = no outro)
OUTRO_DURATION: float = float(os.getenv("OUTRO_DURATION", "5"))
# Outro CTA text shown in the end card
OUTRO_CTA_TEXT: str = os.getenv("OUTRO_CTA_TEXT", "LIKE · SUBSCRIBE · SHARE")
# Channel subtitle shown in intro (instead of subscribe nag)
CHANNEL_SUBTITLE: str = os.getenv("CHANNEL_SUBTITLE", "Truth That Never Shared")

# ── Reddit Distribution ──────────────────────────────────────────────────────
# Enable auto-posting to Reddit after each upload
REDDIT_ENABLED: bool = os.getenv("REDDIT_ENABLED", "false").lower() in ("true", "1", "yes")
# Reddit API credentials — set these in .env, NOT via the dashboard
REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME: str = os.getenv("REDDIT_USERNAME", "")
REDDIT_PASSWORD: str = os.getenv("REDDIT_PASSWORD", "")
# Comma-separated list of subreddit names (without r/)
REDDIT_SUBREDDITS: str = os.getenv("REDDIT_SUBREDDITS", "IslamicProphecy,conspiracy,EndTimes,india")
# Optional flair text — matched against available flairs (partial, case-insensitive)
REDDIT_POST_FLAIR: str = os.getenv("REDDIT_POST_FLAIR", "")

# ── YouTube Automation Features ──────────────────────────────────────────────
# Automatically inject chapter timestamps into video description before upload
AUTO_CHAPTERS: bool = os.getenv("AUTO_CHAPTERS", "true").lower() in ("true", "1", "yes")
# Pin a subscribe CTA as the first comment immediately after upload
PIN_FIRST_COMMENT: bool = os.getenv("PIN_FIRST_COMMENT", "true").lower() in ("true", "1", "yes")
# Custom pinned comment text (default generated from channel name if empty)
PINNED_COMMENT_TEXT: str = os.getenv("PINNED_COMMENT_TEXT", "")
# Burn a YouTube-style end screen (subscribe circle + watch-next box) into the last N seconds
AUTO_END_SCREENS: bool = os.getenv("AUTO_END_SCREENS", "true").lower() in ("true", "1", "yes")
# Duration in seconds for the burned-in end screen (replaces outro when enabled)
END_SCREEN_DURATION: float = float(os.getenv("END_SCREEN_DURATION", "20"))

# ── Model & API Constants ─────────────────────────────────────────────────────
CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
YOUTUBE_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
