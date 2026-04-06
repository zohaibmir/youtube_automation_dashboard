# Global YT Command Centre — Settings & Deployment Guide

## Quick Summary

| Option | Cost/month | Videos | Best for |
|--------|-----------|--------|---------|
| **5/week (recommended)** | **$29.50** | 22 | Starting out, low risk |
| **Daily (7/week)** | **$107** | 30 | After channel gains traction |

**Verdict:** Start at 5/week. Upgrade to daily once you hit 500+ avg views per video.

---

## 1. Local Setup (Run on Your Own Computer)

### Requirements
- Python 3.10+
- FFmpeg installed
- 8GB RAM minimum (video rendering is heavy)

### Step-by-step

```bash
# 1. Clone or create project folder
mkdir yt-automation && cd yt-automation

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install FFmpeg
# Ubuntu/Debian:
sudo apt install ffmpeg
# Mac:
brew install ffmpeg
# Windows: download from https://ffmpeg.org/download.html

# 5. Copy your .env file and fill in API keys
cp .env.example .env
nano .env   # or open in any text editor

# 6. Set up YouTube API (one-time)
# Go to: https://console.cloud.google.com
# Create project → Enable "YouTube Data API v3"
# Credentials → OAuth 2.0 → Desktop app
# Download JSON → save as client_secrets.json in project folder

# 7. Run first video manually to test
python main.py "10 paise bachane ki aadat"

# 8. Start the scheduler (runs forever)
python scheduler.py

# Optional: run early morning UTC instead of the default 14:00 UTC
export SCHEDULER_PUBLISH_TIME=03:00
python scheduler.py

# Optional: run twice daily at fixed server times
export SCHEDULER_PUBLISH_TIMES=02:00,14:00
python scheduler.py
```

### Keep it running overnight (Linux/Mac)
```bash
# Using nohup (runs after terminal closes)
nohup python scheduler.py > logs.txt 2>&1 &

# Check logs
tail -f logs.txt

# Stop it
kill $(cat scheduler.pid)
```

### Windows Task Scheduler
1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily, repeat every 1 hour
3. Action: Start program → `python` with argument `scheduler.py`
4. Start in: your project folder path

---

## 2. Cloud Deployment — VPS (Recommended for 24/7)

Best option: **DigitalOcean Droplet** or **Hetzner CX22** — ~$6/month for 4GB RAM

```bash
# On your local machine — upload project
scp -r ./yt-automation user@YOUR_SERVER_IP:/home/user/

# SSH into server
ssh user@YOUR_SERVER_IP

# Install Python + FFmpeg
sudo apt update && sudo apt install python3 python3-pip python3-venv ffmpeg -y

# Set up project
cd /home/user/yt-automation
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Fill in .env
nano .env

# Run as background service using screen
sudo apt install screen -y
screen -S ytbot
python scheduler.py
# Press Ctrl+A then D to detach (keeps running)

# Reconnect later
screen -r ytbot
```

### Set up as a systemd service (auto-restart on crash)
```bash
sudo nano /etc/systemd/system/ytbot.service
```
```ini
[Unit]
Description=YouTube Automation Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/yt-automation
Environment=PATH=/home/ubuntu/yt-automation/venv/bin
ExecStart=/home/ubuntu/yt-automation/venv/bin/python scheduler.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable ytbot
sudo systemctl start ytbot
sudo systemctl status ytbot   # check it's running
```

---

## 3. Cloud Deployment — Railway.app (Easiest, no server management)

Railway has a free tier and a $5/month hobby plan. Good for lighter workloads.

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and create project
railway login
railway init

# Set environment variables (replaces .env)
railway variables set ANTHROPIC_API_KEY=sk-ant-...
railway variables set ELEVENLABS_API_KEY=...
railway variables set PEXELS_API_KEY=...

# Add a Procfile
echo "worker: python scheduler.py" > Procfile

# Deploy
railway up
```

**Note:** Railway doesn't persist files between deploys. Use the `topic_queue.json` stored in Railway's volume or a simple SQLite database.

---

## 4. Docker Setup (Most Portable)

```dockerfile
# Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "scheduler.py"]
```

```bash
# Build and run
docker build -t yt-automation .
docker run -d --env-file .env --name ytbot yt-automation

# View logs
docker logs -f ytbot
```

---

## 5. API Keys — Where to Get Them

### Anthropic API Key
1. Go to https://console.anthropic.com
2. Sign up → Settings → API Keys → Create Key
3. Starts with `sk-ant-...`
4. Free $5 credit on signup. Add billing after.
5. **Cost:** ~$0.003 per 1K input tokens, ~$0.015 per 1K output tokens
6. **Per script:** ~$0.05-0.08

### ElevenLabs API Key
1. Go to https://elevenlabs.io → Sign up
2. Profile → API Keys → Generate
3. **Plans:**
   - Free: 10,000 chars/month (2 test videos)
   - Indie $22/month: 100,000 chars (22 videos at 4,500 chars each)
   - Creator $99/month: 500,000 chars (daily posting)
4. **Voice ID:** Use `JBFqnCBsd6RMkjVDRZzb` (George) or browse voices at elevenlabs.io/voice-library

### Pexels API Key
1. Go to https://www.pexels.com/api/
2. Register → Get API Key
3. **Free:** 200 requests/hour, unlimited images
4. No payment required

### YouTube Data API
1. Go to https://console.cloud.google.com
2. Create new project (e.g. "YT Automation")
3. APIs & Services → Enable → search "YouTube Data API v3" → Enable
4. Credentials → Create Credentials → OAuth 2.0 Client ID → Desktop App
5. Download JSON → rename to `client_secrets.json`
6. First run will open browser for channel authorization
7. **Free quota:** 10,000 units/day (1 upload = ~1,600 units → ~6 uploads/day free)

---

## 6. Cost Breakdown — Detailed

### 5 videos/week = ~22 videos/month

| Service | Plan | Videos covered | Monthly cost |
|---------|------|---------------|-------------|
| Anthropic API | Pay-per-use | Unlimited | ~$1.50 |
| ElevenLabs | Indie $22 | 22 videos | $22.00 |
| Pexels | Free | Unlimited | $0 |
| VPS (optional) | Hetzner CX22 | Always on | $4.50 |
| YouTube API | Free quota | 6/day | $0 |
| **Total** | | | **$28.00/mo** |

### 1 video/day = ~30 videos/month

| Service | Plan | Videos covered | Monthly cost |
|---------|------|---------------|-------------|
| Anthropic API | Pay-per-use | Unlimited | ~$2.00 |
| ElevenLabs | Creator $99 | 110 videos | $99.00 |
| Pexels | Free | Unlimited | $0 |
| VPS (required) | Hetzner CX22 | Always on | $4.50 |
| YouTube API | Free quota | 6/day | $0 |
| **Total** | | | **$105.50/mo** |

### Revenue Projections (5 videos/week, $1.5 CPM average)

| Month | Avg views/video | Monthly views | Ad Revenue | Net profit |
|-------|----------------|---------------|-----------|-----------|
| 1 | 150 | 3,300 | $5 | -$23 |
| 2 | 400 | 8,800 | $13 | -$15 |
| 3 | 1,000 | 22,000 | $33 | +$5 |
| 4 | 2,500 | 55,000 | $82 | +$54 |
| 6 | 6,000 | 132,000 | $198 | +$170 |
| 9 | 15,000 | 330,000 | $495 | +$467 |
| 12 | 30,000 | 660,000 | $990 | +$962 |

**US/UK/AU viewers** push CPM to $4-10 — multiply revenue column by 2-4x if English-speaking markets grow.

---

## 7. What to Improve — Roadmap for a Successful Tool

### Priority 1 — Highest impact

| Feature | Why it matters | How to build |
|---------|---------------|-------------|
| **Real YouTube Trends API** | Get actual trending data, not AI guesses | Use YouTube Data API `videos.list` with `chart=mostPopular` and `regionCode=PK` or `IN` |
| **Thumbnail auto-generator** | Thumbnails drive 70% of click decisions | Use Pillow + custom fonts. Add face image via DALL-E |
| **A/B title testing tracker** | Know which titles get more clicks | Log CTR from YouTube Analytics via API |
| **Shorts auto-cut** | Double reach for free | Use MoviePy to cut first 60s + add captions |
| **Background music layer** | More professional, higher retention | Download royalty-free music from Pixabay audio API |

### Priority 2 — Growth features

| Feature | Why it matters |
|---------|---------------|
| **Comment reply automation** | YouTube rewards high engagement; replies boost comments by 40% |
| **End screen generator** | Add subscribe button overlay to every video |
| **Playlist auto-manager** | Group similar videos; algorithm favors channel structure |
| **Community post scheduler** | Post weekly polls/updates; 3x subscriber retention |
| **Multi-channel support** | Run 3 niche channels from same pipeline |

### Priority 3 — Monetization beyond AdSense

| Stream | Implementation |
|--------|---------------|
| **Affiliate link injector** | Auto-add relevant Amazon/app affiliate links to description |
| **Sponsor outreach tracker** | Log and track brand deal conversations |
| **Digital product store link** | Sell a PDF guide or template via Gumroad; add link in every video |
| **Channel membership** | Enable Members tab after 1K subs; offer exclusive content |

### Priority 4 — Quality improvements

| Improvement | Impact |
|------------|--------|
| **B-roll video clips** instead of static images | +20-40% retention |
| **Custom AI voice clone** (ElevenLabs) | Brand identity; sounds like "your" channel |
| **Captions/subtitles file** (.srt auto-generated) | Accessibility + SEO |
| **Multi-language versions** | Same video in Hindi + Urdu = 2x audience |
| **Trend spike detector** | Alert when a topic suddenly goes viral (Google Trends API) |

---

## 8. Channel Strategy for Maximum Growth

### The 3-pillar content mix
- **40% Evergreen** — "How to invest in Pakistan 2025" — searched forever
- **35% Trending** — "Why rupee is falling" — spike of views now
- **25% Viral hooks** — "99% of people don't know this about money" — algorithm bait

### Upload timing (global audience)
- **Best time:** 2:00-4:00 PM UTC (US morning, EU afternoon)
- **Best days:** Tuesday, Wednesday, Thursday
- **Avoid:** Saturday mornings (low engagement)
- **Shorts:** Post 2 hours AFTER main video for cross-boost

### First 90 days checklist
- [ ] Pick ONE niche and stick to it
- [ ] Upload channel art, about page, links
- [ ] Post first 5 videos before going public
- [ ] Enable Community tab as soon as available
- [ ] Reply to EVERY comment in first 30 days
- [ ] Create a playlist for every 5 videos
- [ ] Add end screens and cards to every video
- [ ] Share each video in 2-3 relevant Facebook groups / WhatsApp groups

### When to monetize beyond AdSense
- **500 subs:** Start affiliate links (Amazon Pakistan, Daraz, finance apps)
- **1,000 subs:** Apply for YouTube Partner Program
- **2,000 subs:** Approach small sponsors (finance apps pay $50-200/mention)
- **5,000 subs:** Enable channel memberships
- **10,000 subs:** Launch a digital product (budget planner PDF = $5-15)

---

## 9. Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `moviepy error` | FFmpeg not installed | `sudo apt install ffmpeg` |
| `ElevenLabs 401` | Wrong API key | Check .env, no spaces around `=` |
| `YouTube quota exceeded` | Free quota (10K/day) used up | Wait 24hrs or apply for quota increase |
| `ModuleNotFoundError` | Missing package | `pip install -r requirements.txt` |
| `OAuthError` | client_secrets.json missing | Download from Google Cloud Console |
| Video render slow | Low RAM | Use a VPS with 4GB+ RAM, or reduce resolution |
| Script sounds robotic | ElevenLabs stability too high | Set stability to 0.45-0.50 in voice_config.py |

---

## 10. File Structure

```
yt-automation/
├── main.py                 # Core pipeline
├── scheduler.py            # Automated publishing
├── voice_config.py         # Voice settings
├── .env                    # API keys (never commit to git)
├── client_secrets.json     # YouTube OAuth (never commit)
├── requirements.txt        # Python packages
├── topic_queue.json        # Auto-generated topic queue
├── last_content.json       # Last generated script/metadata
├── audio/                  # Generated MP3 files (auto-created)
├── images/                 # Downloaded stock images (auto-created)
├── thumbnail.jpg           # Generated thumbnail
└── final.mp4               # Rendered video (overwritten each run)
```

**Important:** Add to `.gitignore`:
```
.env
client_secrets.json
audio/
images/
*.mp4
*.jpg
```

---

*Generated by Global YT Command Centre v2.0*

---

## 11. Database — SQLite Setup

The `database.py` file adds a local SQLite database (`yt_automation.db`) that tracks:

- **Videos table** — every video produced, with topic, title, YouTube ID, status, timestamps
- **Performance table** — views, watch time, likes, subscribers gained, CPM, revenue per video
- **API costs table** — every API call logged with service, operation, units used, and cost
- **Topic queue table** — persistent queue stored in DB instead of a JSON file

### Why SQLite (not PostgreSQL or MySQL)

SQLite is the right choice here because the automation runs on a single machine, the data volume is small (hundreds of videos, not millions of rows), it needs zero setup — just a file on disk — and it works perfectly inside Docker without any additional containers. If you ever need multi-machine access or a web dashboard pulling analytics, you can migrate to PostgreSQL with minimal schema changes.

### Integration into main.py

```python
from database import log_video_start, log_video_complete, log_cost, log_performance

def run(topic):
    vid_id = log_video_start(topic, NICHE, LANGUAGE)
    content = generate_content(topic)
    log_cost('anthropic', 'script', 3000, 0.07, vid_id)
    # ... rest of pipeline ...
    yt_id = upload(video, thumb, content)
    log_video_complete(vid_id, content['title'], yt_id, 360)
    return yt_id
```

### Query examples

```bash
# Open the database
sqlite3 data/yt_automation.db

# Channel stats
SELECT * FROM (
    SELECT COUNT(*) as videos, SUM(p.views) as total_views,
           SUM(p.revenue) as revenue, SUM(p.subs_gained) as subs
    FROM videos v LEFT JOIN performance p ON p.video_id = v.id
    WHERE v.status = 'published'
);

# Monthly costs
SELECT service, SUM(cost_usd) as cost FROM api_costs
WHERE strftime('%Y-%m', recorded_at) = '2025-06' GROUP BY service;

# Top performing videos
SELECT v.title, p.views, p.revenue FROM videos v
JOIN performance p ON p.video_id = v.id
ORDER BY p.views DESC LIMIT 10;
```

### Docker volume for database persistence

```yaml
# In docker-compose.yml — the database persists between container restarts
volumes:
  - ./data:/app/data    # yt_automation.db lives here
```

**Important:** Always mount `./data` as a volume. Without it the database is lost when the container restarts.

---

## 12. Hosting — Free and Cheap Options

### Option 1: Oracle Cloud Free Tier (Recommended for starting out)

**Cost:** $0/month — genuinely free forever, not a trial.

The ARM Ampere A1 instance gives you 4 OCPU and 24GB RAM. That is far more than a YouTube automation pipeline needs.

```bash
# On Oracle Cloud VM
sudo apt update && sudo apt install docker.io docker-compose -y
sudo usermod -aG docker ubuntu
git clone your-repo
cd yt-automation
cp .env.example .env && nano .env
docker compose up -d
```

Sign up at https://cloud.oracle.com/free — requires a credit card for identity verification but is not charged.

### Option 2: Hetzner CX22 (Best paid value)

**Cost:** €3.79/month — 2 vCPU, 4GB RAM, 40GB SSD.

Best price-to-performance for a persistent scheduler. Located in Europe, which is convenient since you are based there.

```bash
# Deploy with Docker on Hetzner
# 1. Create CX22 droplet with Ubuntu 24.04
# 2. SSH in and run:
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
git clone your-repo && cd yt-automation
docker compose up -d
```

### Option 3: Fly.io (Good free tier)

**Cost:** $0-5/month. 3 shared-CPU-1x VMs free. Persistent volumes for the SQLite database cost ~$0.15/GB/month.

```bash
brew install flyctl        # or: curl -L https://fly.io/install.sh | sh
fly auth login
fly launch                 # auto-detects Dockerfile
fly volumes create data --size 1    # 1GB for database
fly deploy
fly logs                   # view scheduler output
```

### Option 4: Railway.app

**Cost:** $5/month hobby plan. Easiest deployment if you want to avoid SSH.

```bash
npm install -g @railway/cli
railway login
railway init
railway variables set ANTHROPIC_API_KEY=sk-ant-...  # (repeat for all keys)
railway up
```

### Option 5: DigitalOcean

**Cost:** $6/month for 1GB RAM. New accounts get $200 free credit (valid 60 days).
Use the "Docker on Ubuntu" 1-Click App to skip setup.

### For the Dashboard HTML file

The HTML dashboard is a single file with no server dependencies. Host it free on:
- **GitHub Pages** — push the file to a repo, enable Pages in settings
- **Netlify** — drag and drop the HTML file at netlify.com/drop
- **Cloudflare Pages** — free, global CDN, custom domain support

### Hosting comparison table

| Option | Cost | RAM | Best for |
|--------|------|-----|---------|
| Oracle Cloud Free | $0 | 24GB | Permanent free hosting |
| Hetzner CX22 | €3.79 | 4GB | Production, Europe-based |
| Fly.io | $0-5 | 256MB-1GB | Easy deploys, free tier |
| Railway | $5 | 512MB | Non-technical setup |
| DigitalOcean | $6 | 1GB | $200 credit for new users |
| Local (your PC) | $0 | All | Development and testing |

**Bottom line:** Use Oracle Cloud Free Tier to get started. Move to Hetzner CX22 once the channel generates consistent revenue to cover the €3.79/month.

