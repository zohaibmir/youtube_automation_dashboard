# Voice configuration and management with 3-tier hierarchy:
# Priority: Video level > Channel level > Global level

from config import VOICE_SIMILARITY, VOICE_STABILITY, VOICE_STYLE

# Supported languages and their recommended Edge TTS voices
LANGUAGE_VOICES = {
    "english": {
        "label": "English",
        "recommended": [
            {"id": "en-US-ChristopherNeural", "name": "Christopher (Documentary)"},
            {"id": "en-US-BrianNeural", "name": "Brian (Professional)"},
            {"id": "en-US-GuyNeural", "name": "Guy (Deep voice)"},
            {"id": "en-GB-RyanNeural", "name": "Ryan (British)"},
        ]
    },
    "hindi": {
        "label": "Hindi",
        "recommended": [
            {"id": "hi-IN-MadhurNeural", "name": "Madhur (Male)"},
            {"id": "hi-IN-SwaraNeural", "name": "Swara (Female)"},
        ]
    },
    "urdu": {
        "label": "Urdu",
        "recommended": [
            {"id": "ur-PK-AsadNeural", "name": "Asad (Male)"},
            {"id": "ur-PK-UzmaNeural", "name": "Uzma (Female)"},
        ]
    },
    "hinglish": {
        "label": "Hinglish (Hindi+English)",
        "recommended": [
            {"id": "en-IN-PrabhatNeural", "name": "Prabhat (Male)"},
            {"id": "en-IN-NeerjaNeural", "name": "Neerja (Female)"},
        ]
    },
}


def get_voice_settings() -> dict:
    """Get ElevenLabs voice settings for TTS."""
    return {
        "stability": VOICE_STABILITY,
        "similarity_boost": VOICE_SIMILARITY,
        "style": VOICE_STYLE,
        "use_speaker_boost": True,
    }


def get_channel_voice(channel_slug: str) -> str | None:
    """Get voice ID for a specific YouTube channel.
    
    Args:
        channel_slug: Channel slug (e.g., 'default', 'zohaibmir')
    
    Returns:
        Voice ID (e.g., 'en-US-ChristopherNeural') or None if not set
    """
    try:
        from youtube_uploader import _load_channels
        channels = _load_channels()
        if channel_slug in channels:
            return channels[channel_slug].get("voice_id")
        return None
    except Exception:
        return None


def set_channel_voice(channel_slug: str, voice_id: str) -> bool:
    """Set voice ID for a specific YouTube channel.
    
    Args:
        channel_slug: Channel slug
        voice_id: Edge TTS voice ID
    
    Returns:
        True if successful, False otherwise
    """
    try:
        import json
        import os
        from youtube_uploader import _load_channels, _CHANNELS_FILE
        
        channels = _load_channels()
        if channel_slug not in channels:
            return False
        
        channels[channel_slug]["voice_id"] = voice_id
        
        # Ensure tokens directory exists
        os.makedirs(os.path.dirname(_CHANNELS_FILE), exist_ok=True)
        
        # Write back to channels.json
        with open(_CHANNELS_FILE, 'w') as f:
            json.dump(channels, f, indent=2)
        
        return True
    except Exception as e:
        print(f"Error setting channel voice: {e}")
        return False


def get_global_voice() -> str | None:
    """Get globally configured Edge TTS voice.
    
    Returns:
        Voice ID from dashboard settings, env var EDGE_TTS_VOICE, or None
    """
    # Priority 1: Dashboard settings
    try:
        from database import get_settings
        settings = get_settings()
        if isinstance(settings, dict) and 'config' in settings:
            config = settings.get('config', {})
            if isinstance(config, dict) and config.get('edgeVoice'):
                return config['edgeVoice']
    except Exception:
        pass
    
    # Priority 2: Environment variable
    from config import EDGE_TTS_VOICE
    return EDGE_TTS_VOICE


def resolve_voice(language: str = "english", 
                 channel_slug: str | None = None,
                 video_voice_id: str | None = None) -> str:
    """Resolve voice ID using 3-tier hierarchy.
    
    Priority:
    1. video_voice_id (video-level override)
    2. channel voice (channel-level setting)
    3. global voice (dashboard/env setting)
    4. language default
    
    Args:
        language: Language code (english, hindi, urdu, hinglish)
        channel_slug: YouTube channel slug
        video_voice_id: Video-level voice override
    
    Returns:
        Voice ID to use for TTS generation
    """
    # 1. Video level (highest priority)
    if video_voice_id:
        return video_voice_id
    
    # 2. Channel level
    if channel_slug:
        channel_voice = get_channel_voice(channel_slug)
        if channel_voice:
            return channel_voice
    
    # 3. Global level
    global_voice = get_global_voice()
    if global_voice:
        return global_voice
    
    # 4. Language default
    voices = LANGUAGE_VOICES.get(language.lower(), {}).get("recommended", [])
    if voices:
        return voices[0]["id"]
    
    # Ultimate fallback
    return "en-US-ChristopherNeural"