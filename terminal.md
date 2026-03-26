# YouTube Automation — Terminal Commands

A simple guide to run everything from the terminal. Copy-paste these commands.

> **Before anything:** always open Terminal, go to the project folder, and activate the environment:
> ```bash
> cd /private/var/www/youtube_automation
> source .venv/bin/activate
> ```

---

## 1. Start the Dashboard

This starts the web dashboard so you can open it in your browser at `http://localhost:8080`

```bash
python3 server.py
```

To run it in the **background** (so you can keep using the terminal):

```bash
python3 server.py &
```

To **restart** it (stop old one, start fresh):

```bash
pkill -f "server.py"; sleep 1 && python3 server.py &
```

To **check if it's running**:

```bash
curl -s http://localhost:8080/api/env | python3 -m json.tool
```

---

## 2. Create a Video (Full Pipeline)

### Option A: Quick — one topic, default YouTube channel

```bash
python3 main.py "Who Built the Pyramids? The Real Story"
```

### Option B: Choose which YouTube channel to upload to

```bash
python3 _run_pipeline.py --channel main-channel
```

> **Note:** Edit the `TOPIC` inside `_run_pipeline.py` to change the video topic.

### Option C: From the Dashboard (easiest)

1. Open `http://localhost:8080` in your browser
2. Go to **Script** tab → type topic → click **Full Script**
3. Optionally write guidance in the **AI guidance** box
4. Click **+ Queue** → go to **Queue** tab → click **Run**

---

## 3. Auto-Scheduler (Publish Videos on a Schedule)

Runs automatically based on your `VIDEOS_PER_WEEK` setting.

```bash
# Use default YouTube channel
python3 scheduler.py

# Use a specific channel
python3 scheduler.py --channel main-channel
```

---

## 4. YouTube Channels

### See all your connected channels

```bash
python3 -c "
from youtube_uploader import list_channels
for ch in list_channels():
    star = '⭐' if ch['is_default'] else '  '
    print(f'{star} {ch[\"slug\"]:20s}  {ch[\"name\"]}')
"
```

Example output:
```
⭐ default               Truth that never shared
   main-channel          zohaib mir
```

### Change the default channel

```bash
# Set "main-channel" as default
python3 -c "from youtube_uploader import set_default_channel; set_default_channel('main-channel')"

# Set "default" back
python3 -c "from youtube_uploader import set_default_channel; set_default_channel('default')"
```

---

## 5. Preview a Video (Without Uploading)

Builds the video locally so you can watch it first, no upload.

```bash
python3 -c "
from pipeline import run_preview
import logging
logging.basicConfig(level=logging.INFO)
video, thumb, content, vid_id = run_preview('Your Topic Here', progress_cb=lambda m: print('>>',m))
print('Video:', video)
print('Title:', content.get('title'))
"
```

The video file will be saved in the `output/` folder.

---

## 6. Check Everything Works (Smoke Test)

Run this to make sure all modules are installed correctly:

```bash
python3 smoke_test.py
```

You should see all checkmarks (✓). If any show ✗, something is broken.

---

## 7. Check Your Settings

### See video settings (zoom, music, crossfade)

```bash
python3 -c "
from config import KEN_BURNS_ZOOM, CROSSFADE_DURATION, BG_MUSIC_VOLUME_DB, BG_MUSIC_PATH
print('Zoom effect:', KEN_BURNS_ZOOM)
print('Crossfade:', CROSSFADE_DURATION, 'sec')
print('Music volume:', BG_MUSIC_VOLUME_DB, 'dB')
print('Music file:', BG_MUSIC_PATH or 'None')
"
```

### Check if API keys are loaded

```bash
python3 -c "
from config import ANTHROPIC_API_KEY, PEXELS_API_KEY
print('Claude AI:', 'OK' if ANTHROPIC_API_KEY else 'MISSING!')
print('Pexels:', 'OK' if PEXELS_API_KEY else 'MISSING!')
"
```

---

## 8. Database & Queue

### How many videos have been made?

```bash
python3 -c "
from database import init_db, get_channel_stats
init_db()
print(get_channel_stats())
"
```

### How many topics are waiting in the queue?

```bash
python3 -c "
from database import init_db; init_db()
from topic_queue import pending_count
print('Topics waiting:', pending_count())
"
```

---

## 9. First-Time Setup

Only do this once when setting up on a new machine:

```bash
# Step 1: Create virtual environment
python3 -m venv .venv

# Step 2: Activate it
source .venv/bin/activate

# Step 3: Install all packages
pip install -r requirements.txt

# Step 4: Install ffmpeg (needed for video)
brew install ffmpeg
```

Then copy `.env.example` to `.env` and fill in your API keys.

---

## 10. Save Your Work (Git)

### Save all changes

```bash
git add -A
git commit -m "describe what you changed"
```

### Push to GitHub

```bash
git push origin main
```

### See what changed

```bash
git status
git log --oneline -5
```
