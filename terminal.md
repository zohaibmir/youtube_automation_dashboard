# Terminal Commands Reference

Quick reference for all CLI operations in the YouTube automation pipeline.

---

## Server

```bash
# Start dashboard server (port 8080)
source .venv/bin/activate && python3 server.py

# Start in background
python3 server.py &

# Kill & restart
pkill -f "server.py" 2>/dev/null; sleep 0.5 && source .venv/bin/activate && python3 server.py &

# Test server is running
curl -s http://localhost:8080/api/env | python3 -m json.tool
```

## Full Pipeline (CLI)

```bash
# Run pipeline with default channel
source .venv/bin/activate && python3 _run_pipeline.py

# Run pipeline → upload to specific channel
python3 _run_pipeline.py --channel main-channel

# Run via main.py (simpler, uses sys.argv topic)
python3 main.py "Your Video Topic Here"
```

## Scheduler

```bash
# Start scheduler (default channel)
python3 scheduler.py

# Start scheduler → specific channel
python3 scheduler.py --channel main-channel

# Or via env var
SCHEDULER_CHANNEL=main-channel python3 scheduler.py
```

## YouTube Channels

```bash
# List all channels
python3 -c "
from youtube_uploader import list_channels
for ch in list_channels():
    d = '⭐' if ch['is_default'] else '  '
    print(f'{d} {ch[\"slug\"]:20s}  {ch[\"name\"]}')
"

# Set default channel
python3 -c "from youtube_uploader import set_default_channel; set_default_channel('default')"

# Check token path for a channel
python3 -c "from youtube_uploader import _get_token_path; print(_get_token_path('main-channel'))"
```

## Smoke Test & Imports

```bash
# Full smoke test (all modules + DB)
python3 smoke_test.py

# Quick import check
python3 -c "
from pipeline import run, run_preview
from content_generator import generate_script, script_text_to_segments
from video_builder import build_video
print('✓ All imports OK')
"
```

## Preview Pipeline (no upload)

```bash
python3 -c "
from pipeline import run_preview
import logging
logging.basicConfig(level=logging.INFO)

video_path, thumb_path, content, vid_id = run_preview(
    'Your Topic Here',
    progress_cb=lambda msg: print(f'>> {msg}')
)
print(f'✅ Video: {video_path}')
print(f'✅ Thumb: {thumb_path}')
print(f'✅ Title: {content.get(\"title\")}')
"
```

## Environment & Config

```bash
# Check key config values
python3 -c "
from config import KEN_BURNS_ZOOM, CROSSFADE_DURATION, BG_MUSIC_VOLUME_DB, BG_MUSIC_PATH
print(f'KEN_BURNS_ZOOM={KEN_BURNS_ZOOM}')
print(f'CROSSFADE={CROSSFADE_DURATION}')
print(f'BG_MUSIC_VOL={BG_MUSIC_VOLUME_DB}')
print(f'BG_MUSIC_PATH={repr(BG_MUSIC_PATH)}')
"

# Verify .env is loaded
python3 -c "from config import ANTHROPIC_API_KEY, PEXELS_API_KEY; print('Keys loaded' if ANTHROPIC_API_KEY else 'MISSING')"
```

## Setup

```bash
# Create venv & install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Install ffmpeg (macOS)
brew install ffmpeg

# Docker
docker-compose up --build
```

## Database

```bash
# Check stats
python3 -c "
from database import init_db, get_channel_stats
init_db()
print(get_channel_stats())
"

# Topic queue count
python3 -c "
from database import init_db; init_db()
from topic_queue import pending_count
print(f'Pending topics: {pending_count()}')
"
```

## Git

```bash
git add -A && git commit -m "feat: description"
git push origin main
```
