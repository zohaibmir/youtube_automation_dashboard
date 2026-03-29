# YouTube Automation — Features & Roadmap

**Channel target:** Global English audiences (Politics & Religion)  
**Stack:** Python 3.13 · Claude Sonnet · ElevenLabs · Pexels · YouTube Data API v3  
**Dashboard:** Single-file HTML (`youtube_automation_dashboard.html`) served at `http://localhost:8080`

---

## ✅ Implemented Features

### 1. Python Automation Pipeline (9 SRP modules)

| Module | Responsibility |
|---|---|
| `config.py` | All environment variables and constants in one place |
| `content_generator.py` | Claude-powered script generation |
| `audio_generator.py` | ElevenLabs TTS voiceover generation |
| `visual_fetcher.py` | Pexels stock image/video fetching |
| `video_builder.py` | FFmpeg video assembly (audio + visuals + music) |
| `youtube_uploader.py` | OAuth upload + thumbnail + metadata push |
| `pipeline.py` | Orchestrates the full end-to-end run |
| `topic_queue.py` | JSON-backed topic queue with auto-refill |
| `scheduler.py` | Cron-style scheduler (5×/week default, peak IST/PKT time) |
| `database.py` | SQLite: video history, performance, API costs, YPP progress |
| `hybrid_mode.py` | Mode A (faceless AI) / Mode B (Kamil hybrid) logic |
| `thumbnail.py` | Pillow-based thumbnail generation |
| `smoke_test.py` | 15-point import + integration smoke test |

**Key pipeline capabilities:**
- Auto-generates scripts in English (global, conversational, or documentary style)
- ElevenLabs TTS with tunable stability, similarity, style
- Pexels visual fetching per script segment
- FFmpeg multi-track video assembly
- YouTube upload with title, description, tags, thumbnail in one run
- SQLite cost + performance tracking per video
- Auto queue refill via Claude when queue drops below 5 topics
- Scheduled publishing at 14:00 UTC (7:30 PM IST / 7 PM PKT — peak traffic)

---

### 2. HTML Dashboard — Panel-by-Panel

#### Panel 1 — Trending & Viral
- Live web search via Claude (Anthropic web search beta) for real-time trends
- 4 filter modes: Live trends · Viral · Evergreen · News
- 8 topic cards per search with: hook, type badge, CPM range, search volume, competition level, why-now context
- Per-card actions: **→ Script**, **→ SEO**, **+ Queue**
- Viral Audio tracker — searches trending Bollywood/Punjabi/Urdu sounds on YouTube Shorts

#### Panel 2 — Script Writer
- Mode A (Automated/Faceless) and Mode B (Kamil Hybrid) selector — synced with Thumbnail panel
- Full YouTube script (3–8 min)
- YouTube Shorts script (60 sec)
- Hybrid script format: `[KAMIL INTRO]` / `[AI NARRATOR]` sections for Mode B
- Post-generation actions: **→ SEO**, **→ Thumbnail**, **+ Queue with SEO metadata**

#### Panel 3 — SEO Package
- Auto-populated from Script Writer (full script → topic → channel niche, zero copy-paste)
- Auto-populated from Trending cards via `useForSEO()`
- Optional manual override field (collapsed `<details>` element)
- Generates: 3 A/B title options, full description, keyword tags, thumbnail text ideas, upload time + chapters
- Post-generation action bar: **→ Thumbnail** · **+ Queue with SEO**
- Apply to existing YouTube video: push title/description/tags to any video ID via YouTube Data API

#### Panel 4 — Thumbnail Designer
- Live 1280×720 HTML5 canvas at YouTube spec
- 6 templates: Impact · Face Left · Face Right · Split · News · Minimal
- AI text generation (Claude) populates headline from current topic
- Pexels photo background — searches by topic keyword, CORS taint detection
- Face photo upload for Mode B (Kamil on thumbnail)
- Controls: headline lines, badge text, channel name, headline/accent/background colours, text style, font size
- Shot guide for Mode B recording (expression, framing, lighting tips)
- Export: PNG download
- Push thumbnail directly to YouTube video via YouTube Data API
- **Save to Queue → Upload Decision** button carries canvas JPEG into queue item

#### Panel 5 — Video Queue
- Rich expandable cards with:
  - Thumbnail preview (72×41 miniature from canvas)
  - Pipeline status badges: `Script` · `SEO` · `Thumb` (green = complete, grey = missing)
  - Expand to see SEO title, description preview, tags
  - Per-item actions: Edit Script · SEO · Thumbnail · Mark Done · Remove
- **Upload button** — if YouTube connected: prompts for Video ID, applies SEO + pushes thumbnail. If not: shows `python main.py "topic"` CLI command
- Manual topic + date entry
- AI 4-week plan generator (Claude) — mix of 40% evergreen / 35% viral / 25% news
- Export queue to CSV
- Stats: in queue · this week · completed · weeks planned

#### Panel 6 — Performance Tracker
- Log views, watch minutes, likes, comments, subs gained, CPM per video
- YPP progress bars (1,000 subs / 4,000 watch hours)
- Channel totals: total views, revenue, average views

#### Panel 7 — Cost & Revenue
- Per-service usage tracking: Anthropic, ElevenLabs, Pexels, YouTube API
- Monthly budget bars and remaining budget indicators
- Budget overview table with total cost estimate

#### Panel 8 — Pipeline Code
- Inline copy-paste panels for all Python modules
- Dockerfile and docker-compose.yml with volume mounts
- Hosting comparison: Oracle Cloud Free (recommended) · Hetzner · Fly.io · Railway · DigitalOcean

#### Panel 9 — Settings
- API key management: Anthropic, ElevenLabs, Pexels, YouTube
- All keys stored in `localStorage` — never transmitted to any server
- Test buttons for each API connection
- Channel identity: name, handle/watermark, description, CPM, videos/week
- YouTube OAuth: GIS-based browser OAuth (Web Application Client ID)
- Export `.env` file button
- Security banner explaining key storage

---

### 3. Pipeline Breadcrumb Bar
- Appears on all 5 pipeline panels (Trending → Script → SEO → Thumbnail → Queue)
- Completed steps highlighted green, active step in accent purple
- Clickable — jump to any step directly
- Final step "→ YouTube" always visible as target destination

---

### 4. Connectivity & Integrations
- **Anthropic Claude** — scripts, SEO, trends, viral audio (web search beta enabled)
- **ElevenLabs TTS** — voiceover with tunable voice parameters
- **Pexels API** — stock photos for thumbnail backgrounds and video visuals
- **YouTube Data API v3** — upload, metadata update, thumbnail push
- **Google Identity Services (GIS)** — browser-based YouTube OAuth (no backend needed)
- **FFmpeg 8.1** — local video assembly
- **SQLite** — local database for video history, costs, performance
- **Docker** — containerised scheduler + web service (docker-compose.yaml)

---

## 🔮 Enhancement Roadmap

### High Priority

#### AI-Generated Thumbnail Images
- Replace Pexels BG with Stable Diffusion / DALL-E / Ideogram API call
- Generate a photorealistic scene based on the script topic instead of stock photos
- Style presets: dramatic · news · finance · motivational

#### YouTube Analytics Pull
- Use YouTube Analytics API to pull actual views, watch time, CTR, impressions
- Replace manual performance logging with live data sync
- Auto-detect best-performing thumbnail templates based on real CTR data

#### One-Click Full Production
- "Produce this video" button in the Queue panel
- Triggers: script generation → TTS → Pexels visuals → FFmpeg assembly → upload — all from the browser via Python API endpoint
- Progress indicator showing each pipeline stage

#### Voice Preview in Dashboard
- Add a "Preview voice" button that calls ElevenLabs with the first 2 lines of the script
- Lets the user audition the voiceover before committing to full production

---

### Medium Priority

#### A/B Title Testing Tracker
- When multiple title options are pushed to YouTube, track which one is live
- Record CTR per title option over 48 hours and surface the winner

#### Shorts Auto-Reformatter
- Take a long-form script and automatically split into 3–5 Shorts (60 sec each)
- Generates individual thumbnails for each Short with numbered series badges

#### Multi-Channel Support
- Support multiple channel profiles (e.g. Finance channel + Motivation channel)
- Each profile has its own niche, audience, voice ID, queue, and API budget
- Switch channels via dropdown in the nav bar

#### Competitor Benchmarking
- Claude web-search competitor channels by niche
- Show: top video topics, avg views, posting frequency, most-used tags
- "Steal this idea" button sends competitor topic to Script Writer

#### Script Tone Selector
- Add tone presets to Script Writer: Educational · Shocking · Emotional · Motivational · Funny/Sarcastic
- Injects tone instructions into Claude prompt automatically

#### Batch SEO Re-optimiser
- Run all queue items through SEO re-generation after selecting a new niche/audience
- Useful when pivoting channel focus

---

### Infrastructure / DevOps

#### Python API Bridge
- Lightweight FastAPI server exposing `/run`, `/status`, `/queue` endpoints
- Dashboard calls these instead of just showing CLI commands
- Enables true one-click production without leaving the browser

#### Cloud Sync for Queue
- Sync the localStorage queue to a remote JSON (GitHub Gist / Cloudflare KV / Supabase)
- Access the same queue from multiple devices or browsers

#### Webhook Notifications
- Push Discord / Telegram message when a video finishes uploading
- Include thumbnail preview, title, and YouTube link in the notification

#### Scheduled Auto-Run (persistent)
- Docker-based cron: auto-runs `python main.py` for the next item in queue at the configured schedule
- Status visible in the Pipeline Code panel's live log section

#### Cost Anomaly Alerts
- Notify (browser notification or Discord) when monthly spend exceeds 80% of budget
- Per-service breakdown with trend vs. last month

---

### Quality & Content

#### SEO Score Indicator
- After generating SEO, score the title (0–100) on: length, keyword density, click curiosity, seasonality
- Red/amber/green indicator with one-line improvement tip

#### Thumbnail CTR Predictor
- Run the canvas thumbnail through a Claude vision call
- Returns estimated CTR tier (low / medium / high) with reasoning (text legibility, contrast, emotional hook)

#### Auto Caption / SRT Generation
- After TTS is generated, use Whisper API to produce an SRT subtitle file
- Embed captions into video via FFmpeg for accessibility and watch time

#### Topic Deduplication
- Before adding to queue, check if similar topic already exists (fuzzy match by title)
- Warn the user with "Similar topic already in queue: X" prompt

#### Evergreen Refresh Scheduler
- Re-run SEO on evergreen videos every 90 days to stay current with search trends
- Add a "Refresh SEO" action in the Performance Tracker per-video row
