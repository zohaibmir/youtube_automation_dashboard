# Voice Selection System - 3-Tier Hierarchy

## Overview

The YouTube automation app now supports flexible voice selection across 4 languages with a 3-tier priority system:

- **Level 1 (Video)**: Per-video voice override (highest priority)
- **Level 2 (Channel)**: Per-channel voice setting
- **Level 3 (Global)**: Dashboard/environment global voice setting

## Supported Languages

All voices use Microsoft Edge TTS (free, studio-quality, no API keys):

### English (4 voices)
- `en-US-ChristopherNeural` - Documentary style, authoritative
- `en-US-BrianNeural` - Professional, calm
- `en-US-GuyNeural` - Deep, serious
- `en-GB-RyanNeural` - British English

### Hindi (2 voices)
- `hi-IN-MadhurNeural` - Male, warm
- `hi-IN-SwaraNeural` - Female

### Urdu (2 voices)
- `ur-PK-AsadNeural` - Male, clear
- `ur-PK-UzmaNeural` - Female

### Hinglish - Hindi + English (2 voices)
- `en-IN-PrabhatNeural` - Male, natural Hinglish
- `en-IN-NeerjaNeural` - Female, natural Hinglish

**Total: 10 recommended voices from 47 available Edge TTS voices**

## How It Works

### 1. Global Voice Setting
Set in Dashboard → Settings → Edge Voice selector.

This applies to all videos UNLESS overridden at channel or video level.

**Current Voice:** [Read from database settings or `EDGE_TTS_VOICE` env var]

### 2. Per-Channel Voice Setting
Each YouTube channel can have its own default voice.

**Usage:** 
- Go to Dashboard → Channels
- Click channel → Voice dropdown
- Select voice → Save

When uploading a video, the channel's voice is used unless a video-level override is set.

### 3. Per-Video Voice Override
Set when creating the video in the Pipeline tab.

**Usage:**
- Pipeline → Generate → [scroll to TTS options]
- Select voice for this video only
- Generate video

Priority: Video voice > Channel voice > Global voice

## Voice Priority Resolution

When generating audio for a video:

```
1. if video_voice_id is set:
     use video_voice_id

2. else if channel_slug has a voice_id:
     use channel.voice_id

3. else if global voice is set:
     use global_voice

4. else:
     use language default (en-US-ChristopherNeural for English)
```

## Implementation Files

- `voice_config.py` - Voice resolution logic and database functions
- `audio_generator.py` - Integrated voice resolution with TTS generation
- `scripts/download_voice_samples.py` - Downloads test samples for all 10 voices
- `scripts/voice_samples/` - Local voice test samples directory

## Testing Voices Locally

All 10 recommended voices are downloadable for testing:

```bash
cd /private/var/www/youtube_automation
ls scripts/voice_samples/
```

Files by language:
- `english_*.mp3` - 4 English voices
- `hindi_*.mp3` - 2 Hindi voices
- `urdu_*.mp3` - 2 Urdu voices
- `hinglish_*.mp3` - 2 Hinglish voices

## Database Schema

The `channels` table now supports:

```
columns:
  - id (integer, primary key)
  - slug (text, unique) — channel identifier
  - name (text) — friendly name
  - is_default (boolean)
  - voice_id (text, nullable) — Edge TTS voice for this channel
  - ...other columns...
```

If `voice_id` is NULL, the channel uses the global voice setting.

## API Endpoints (Future)

```
GET  /api/channels/<slug>/voice     → Get channel's voice
POST /api/channels/<slug>/voice     → Set channel's voice
```

## CLI Usage

### Get channel voice:
```python
from voice_config import get_channel_voice
voice = get_channel_voice("zohaibmir")
print(voice)  # e.g., "en-US-BrianNeural" or None
```

### Set channel voice:
```python
from voice_config import set_channel_voice
set_channel_voice("zohaibmir", "en-US-GuyNeural")
```

### Resolve voice (with hierarchy):
```python
from voice_config import resolve_voice
voice = resolve_voice(
    language="english",
    channel_slug="zohaibmir",
    video_voice_id=None  # None = use channel/global fall-back
)
print(voice)  # Uses 3-tier priority
```

## Known Limitations

1. **Database Migration**: The `voice_id` column needs to be added to existing databases via:
   ```sql
   ALTER TABLE channels ADD COLUMN voice_id TEXT DEFAULT NULL;
   ```

2. **Dashboard UI**: Per-channel voice selection UI not yet wired in (coming soon)

3. **Video-level selection**: Form field on Pipeline tab needs implementation

## Dashboard Integration Status

- ✅ Global voice selector (47 voices available)
- ✅ Voice samples downloadable locally
- ⏳ Per-channel voice selector UI
- ⏳ Per-video voice selector on Pipeline tab
- ⏳ API endpoints for voice management

## Notes

- All voices are free via Microsoft Edge TTS
- No API keys needed
- Sample rate: 24kHz mono (MP3 format)
- Suitable for YouTube narration (both full videos and Shorts)
- Voice quality comparable to professional TTS systems
