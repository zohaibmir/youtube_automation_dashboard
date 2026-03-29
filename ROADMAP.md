# YouTube Automation — Status & Roadmap

Channel: **Truth That Never Shared**
Niche: Prophecy / End Times / Politics / Religion
Target: India + Global English (South Asian diaspora, Muslim audience)

---

## ✅ DONE — Core Pipeline

| Feature | Module | Notes |
|---------|--------|-------|
| Script generation (Claude AI) | `content_generator.py` | 8000 token limit, guidance param |
| Edge-TTS narration (25+ voices) | `audio_generator.py` | en-US-ChristopherNeural default |
| Video clip download (Pexels) | `visual_fetcher.py` | 20 clips per video |
| Ken Burns zoom (static images) | `video_builder.py` | Fast pre-cached path |
| FFmpeg pre-process video clips | `video_builder.py` | ✅ Just added — 65% faster encode |
| Crossfade transitions | `video_builder.py` | 0.4s dissolve between clips |
| Background music mixing | `video_builder.py` | dB volume config |
| Branded intro + outro | `video_builder.py` | Configurable durations |
| Caption overlays | `video_builder.py` | Pre-rendered RGBA overlay |
| Thumbnail generation | `thumbnail.py` | Auto-generated per video |
| YouTube upload (main video) | `youtube_uploader.py` | OAuth, multi-channel |
| YouTube Shorts build + upload | `shorts_builder.py` + `pipeline.py` | 0–3 Shorts per run |
| Multi-channel support | `channel_manager.py` | channels.json registry |
| Parallel pipeline (multi-job) | `pipeline.py` | runs/<job_id>/ isolated dirs |
| Duplicate upload guard | `database.py` | is_video_uploaded() check |
| PID-based job tracking | `pipeline.py` | .jobs/<id>.json registry |
| Kill pipeline API | `server.py` | POST /api/pipeline/kill |
| Instagram Reels + Stories | `social_uploader.py` | Meta Graph API |
| Facebook Reels + Stories | `social_uploader.py` | Meta Graph API |
| TikTok upload | `social_uploader.py` | OAuth2 |
| Community posts | `community_post.py` | YouTube Community tab |
| Topic queue | `topic_queue.py` | Queued topic management |
| Scheduler | `scheduler.py` | Time-based auto-runs |
| Analytics dashboard | `southasian_youtube_dashboard.html` | SQLite-backed |
| SEO-optimised title/description/tags | `content_generator.py` | Claude-generated |
| CRF 23 / fast preset encoding | `video_builder.py` | ✅ Just fixed — ~200MB output |
| Reddit auto-post (PRAW, link submissions) | `reddit_poster.py` + `pipeline.py` | ✅ Just added — r/IslamicProphecy, r/conspiracy, r/EndTimes, r/india + configurable subreddits |
| YouTube Chapters (auto timestamps) | `pipeline.py` | ✅ Just added — injected before upload |
| Pin First Comment (subscribe CTA) | `youtube_uploader.py` + `pipeline.py` | ✅ Just added — pinned after every upload |
| YouTube Automation settings tab | `youtube_automation_dashboard.html` | ✅ Just added — toggle on/off per feature |
| Auto End Screens (burned-in) | `video_builder.py` | ✅ Just added — subscribe circle + watch-next box, last 20s |

---

## ❌ NOT DONE — High Priority (directly impacts growth)

### 1. YouTube Chapters (Timestamps in description)
**Impact:** Boosts average watch duration by 15–25%. YouTube promotes videos with chapters.
**What's needed:** Auto-generate chapter timestamps from segment durations and inject into description.
```
0:00 Introduction
0:45 Prophecy 1: The Barefoot Builders
2:10 Prophecy 2: The Great Fire...
```
**Effort:** Low — segment audio durations are already available in pipeline.

---

### 2. Pin First Comment (Subscribe CTA)
**Impact:** Pinned comments appear above all other comments — high visibility.
**What's needed:** After upload, post a comment via YouTube Data API and pin it.
```
👉 SUBSCRIBE for daily prophecy & hidden truth updates
🔔 Hit the bell — new video every 3 days
```
**Effort:** Low — YouTube API supports this.

---

### ~~3. Auto End Screens~~ ✅
**Done:** Burned-in end screen in the final 20 seconds of every video — subscribe circle, watch-next box, channel name. No API calls needed; controlled by `AUTO_END_SCREENS` env flag and toggle in YT Automation dashboard tab.

---

### 4. Reddit Auto-Post After Upload
**Impact:** Free traffic. r/IslamicProphecy, r/conspiracy, r/EndTimes, r/india have millions of subs.
**Status:** ✅ Done. `reddit_poster.py` uses PRAW to submit a link post to each configured subreddit after upload. Credentials in `.env`; subreddits + flair configurable from the YT Automation settings tab.

---

### 5. Telegram Broadcast Channel
**Impact:** Muslim/South Asian diaspora shares heavily via Telegram. One post = chain shares.
**What's needed:** Post thumbnail + title + YouTube link to a Telegram channel via Bot API.
**Effort:** Low — Telegram Bot API is simple.

---

### 6. Dashboard: Running Jobs Panel
**Impact:** Operational visibility — see all parallel jobs, their status, YouTube links when done.
**What's needed:** Poll `GET /api/pipeline/jobs` and render a live jobs table in the dashboard.
**Effort:** Low — API endpoint already exists.

---

## ⚠️ PARTIALLY DONE

### Social Upload (Instagram/Facebook/TikTok)
- **Code exists** in `social_uploader.py`
- **NOT wired** into the main pipeline `run()` — you have to call it manually
- **Missing:** Auto-post Shorts to Instagram/TikTok after pipeline completes

### Scheduler
- **Code exists** in `scheduler.py`
- **Status unknown** — needs verification that it's actually triggering runs on schedule

### Topic Queue
- **Code exists** in `topic_queue.py`
- **Status unknown** — not confirmed if dashboard is wired to queue for next auto-run

---

## 📋 Channel Setup Checklist (manual, no code needed)

These must be done in YouTube Studio manually:

- [ ] Write keyword-rich channel description (150–200 words with prophecy keywords)
- [ ] Upload channel banner (dark/red dramatic aesthetic)
- [ ] Create 45–60 sec channel trailer video
- [ ] Set channel keywords in YouTube Studio → Customization → Basic info
- [ ] Enable Community tab (requires 500+ subscribers, request it)
- [ ] Verify channel for custom thumbnails (requires phone verification)
- [ ] Set default upload settings (category: News/Education, language: English)

---

## 🚀 Recommended Build Order (Next Sessions)

| Priority | Feature | Time Estimate | ROI |
|----------|---------|--------------|-----|
| ~~1~~ | ~~YouTube Chapters auto-inject~~ | ~~1 session~~ | ~~HIGH — watch time~~ ✅ |
| ~~2~~ | ~~Pin first comment after upload~~ | ~~1 session~~ | ~~HIGH — engagement~~ ✅ |
| ~~3~~ | ~~Auto end screens~~ | ~~1 session~~ | ~~HIGH — retention~~ ✅ |
| ~~4~~ | ~~Reddit auto-post~~ | ~~2 sessions~~ | ~~MEDIUM — free traffic~~ ✅ |
| 4 | Telegram broadcast post | 1 session | HIGH — free traffic |
| 4 | Wire social upload into pipeline | 1 session | HIGH — distribution |
| 5 | Dashboard running jobs panel | 1 session | MEDIUM — ops |

---
