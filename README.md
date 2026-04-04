# YouTube Automation Dashboard

A self-hosted, AI-powered YouTube content factory. Write a topic (or let trending filters find one), generate a full script with Claude, create audio via ElevenLabs (gTTS fallback), pull stock video clips from Pexels, assemble a shortform video with MoviePy, and upload directly to YouTube — all from a single browser dashboard.

---

## Features

- **Trending discovery** — filter by niche (Finance, Tech, Lifestyle, Global, Politics, Custom search)
- **Script Writer** — Claude Sonnet generates structured scripts; write your own too
- **SEO tab** — AI-generated titles, descriptions and tags per video
- **Thumbnail Designer** — drag-and-drop canvas thumbnail builder with font/colour controls
- **Production Queue** — pre-stage script + SEO + thumbnail before hitting Run
- **Pipeline** — end-to-end: script → TTS → visuals → video → upload; all steps skippable if pre-supplied
- **Video clips** — fetches Pexels MP4 clips per segment (captions drawn per-frame, fully animated)
- **Dashboard Settings** — all `.env` keys editable in-browser; auto-saves to server
- **SQLite analytics** — every video, cost estimate and error logged locally
- **Docker support** — single `docker compose up` deployment

---

## Architecture

```
youtube_automation_dashboard.html  ← Single-file SPA (9 panels)
server.py                          ← HTTP API (port 8080)
├── pipeline.py                    ← Orchestrator
│   ├── content_generator.py       ← Claude script generation
│   ├── audio_generator.py         ← ElevenLabs / gTTS TTS
│   ├── visual_fetcher.py          ← Pexels images & video clips
│   ├── video_builder.py           ← MoviePy assembly + PIL captions
│   ├── thumbnail.py               ← Auto thumbnail generator
│   ├── youtube_uploader.py        ← YouTube Data API v3
│   └── database.py                ← SQLite cost & video log
config.py                          ← All settings from .env
scheduler.py                       ← Cron-style auto-publish
main.py                            ← CLI entry point
```

---

## Quick Start (local)

```bash
# 1. Clone & create virtualenv
git clone <repo-url> && cd youtube_automation
python3 -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env — fill in API keys (see below)

# 4. Run server
python3 server.py
# → Open http://localhost:8080/youtube_automation_dashboard.html
```

### Test the pipeline from CLI

```bash
python3 main.py "Your video topic here"
```

---

## Docker

```bash
cp .env.example .env   # fill in your keys
docker compose up --build
# → http://localhost:8080/youtube_automation_dashboard.html
```

Volumes: `./data`, `./audio`, `./images`, `./output` are bind-mounted so generated files persist.

---

## API Keys

| Key | Where to get it |
|-----|-----------------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `ELEVENLABS_API_KEY` | [elevenlabs.io/app/settings](https://elevenlabs.io/app/settings) — optional, gTTS is the free fallback |
| `PEXELS_API_KEY` | [pexels.com/api](https://www.pexels.com/api/) — free |
| YouTube OAuth | See below |

### YouTube OAuth setup

1. [Google Cloud Console](https://console.cloud.google.com) → New project → Enable **YouTube Data API v3**
2. Credentials → OAuth 2.0 Client ID → Desktop app → Download JSON → save as `client_secrets.json`
3. First run: a browser window opens for consent; `token.json` is saved automatically
4. Subsequent runs reuse / auto-refresh `token.json` — no browser popup

Full step-by-step: see **SETTINGS.md**.

---

## Configuration

All settings live in `.env` (copy from `.env.example`). Key options:

```bash
# Channel identity
CHANNEL_NICHE=politics and religion
CHANNEL_LANGUAGE=english
CHANNEL_AUDIENCE=global

# Visuals: "videos" (Pexels MP4 clips) or "images" (Pexels photos)
VISUAL_MODE=videos

# TTS speed multiplier applied via ffmpeg atempo (1.15 = 15% faster)
GTTS_SPEECH_RATE=1.15

# YouTube upload visibility: public | unlisted | private
DEFAULT_VISIBILITY=public
```

You can edit every setting live in the **Settings panel** of the dashboard — changes write back to `.env` and reload instantly.

---

## Dashboard Workflow

```
[Trending]  →  Pick / search a topic
    ↓
[Script Writer]  →  Generate or write script  →  + Queue
    ↓
[SEO]  →  Generate titles / description / tags  →  + Queue
    ↓
[Thumbnail Designer]  →  Design thumbnail  →  + Queue
    ↓
[Queue]  →  ▶ Run  →  Pipeline uses your pre-built assets
    ↓
[Preview]  →  Review video before upload  →  ✓ Upload / ✗ Discard
```

Any step can be skipped — the pipeline falls back to AI generation for anything not pre-supplied.

---

## Project Files

| File | Purpose |
|------|---------|
| `youtube_automation_dashboard.html` | Main dashboard SPA |
| `server.py` | HTTP server + REST API |
| `pipeline.py` | End-to-end pipeline orchestrator |
| `content_generator.py` | Claude script + segment generation |
| `audio_generator.py` | ElevenLabs TTS with gTTS fallback |
| `visual_fetcher.py` | Pexels image & video search |
| `video_builder.py` | MoviePy video assembly + PIL captions |
| `thumbnail.py` | Auto thumbnail generator |
| `youtube_uploader.py` | YouTube Data API v3 uploader |
| `database.py` | SQLite logging (videos, costs, errors) |
| `config.py` | Central config loaded from `.env` |
| `scheduler.py` | Automated scheduling loop |
| `main.py` | CLI pipeline runner |
| `hybrid_mode.py` | Batch / scheduler hybrid runner |
| `thumbnail_designer.html` | Standalone thumbnail designer tool |
| `SETTINGS.md` | Detailed API & OAuth setup guide |
| `FEATURES.md` | Full feature changelog |

---

## Multi-Channel YouTube Upload

The system supports multiple YouTube channels. Each channel has its own OAuth token stored in `tokens/`.

### Dashboard

Open the **YouTube** tab in the dashboard sidebar to manage channels, set a default, and configure upload settings.

### CLI Commands

```bash
# Activate your virtualenv first
source .venv/bin/activate

# List all registered channels
python3 -c "from youtube_uploader import list_channels; import json; print(json.dumps(list_channels(), indent=2))"

# Add a new channel (opens browser for Google OAuth)
python3 -c "from youtube_uploader import add_channel; add_channel('My Channel Name')"

# Set default upload channel (use the slug shown in list_channels)
python3 -c "from youtube_uploader import set_default_channel; set_default_channel('my-channel-name')"

# Remove a channel
python3 -c "from youtube_uploader import remove_channel; remove_channel('my-channel-name')"

# Upload to a specific channel (overrides default)
python3 main.py "Topic here" --channel my-channel-name
```

### How slugs work

When you add a channel named `"My Main Channel"`, the slug is automatically generated as `my-main-channel`. Use this slug in `set_default_channel` and `remove_channel`.

### Token storage

OAuth tokens are stored in `tokens/` (gitignored):

```
tokens/
├── channels.json       ← channel registry (name, slug, channel_id, is_default)
├── default.json        ← token for the default channel
└── my-channel.json     ← token for each additional channel
```

The legacy `token.json` in the project root is automatically migrated to `tokens/default.json` on first run.

---

## Copilot Token Optimization

This repository now includes a Copilot customization layer to reduce repeated context-loading and improve first-pass answer quality.

### Beginner guide

Start with:

- `COPILOT_BEGINNER_GUIDE.md`

### What is included

- Always-on workspace instructions: `.github/copilot-instructions.md`
- File-targeted instructions: `.github/instructions/`
- Custom agents: `.github/agents/`
- Skills: `.github/skills/`
- Prompt files (slash commands): `.github/prompts/`
- Local MCP server: `scripts/repo_mcp_server.py`
- Workspace MCP config: `.vscode/mcp.json`

### Why this saves tokens

- Copilot starts from known architecture (`pipeline.py`, `server.py`, dashboard) instead of rediscovering it each chat.
- Repeated tasks can use short prompts (`/audit-roadmap-feature`, `/map-server-api`) rather than long instructions.
- The MCP server returns compact, structured summaries, which avoids repeatedly reading large files.

### MCP tools now available for compact repo summaries

- `get_repo_overview`
- `get_pipeline_stage_map`
- `get_server_api_surface`
- `get_social_platform_status`
- `get_recent_job_state`
- `get_database_snapshot`
- `get_scheduler_state`
- `get_topic_queue_state`
- `get_recent_artifacts`
- `get_dashboard_panel_map`
- `get_runtime_summary`
- `get_channel_registry_summary`
- `get_recent_job_failures`

### MCP resources now available for quick context attachment

- `repo://overview`
- `repo://roadmap`
- `repo://api-surface`
- `repo://runtime-summary`
- `repo://dashboard-map`
- `repo://job-failures`

### Additional high-repeat prompt commands

- `/audit-scheduler-wiring`
- `/audit-topic-queue-wiring`
- `/review-dashboard-panel-api`
- `/summarize-recent-job-failures`

### Additional skills for recurring diagnostics

- `scheduler-verification`
- `queue-dashboard-wiring`

### Quick start for this setup

1. Open VS Code in this workspace.
2. Trust and start the MCP server defined in `.vscode/mcp.json`.
3. Use a focused agent (`Repo Planner`, `Pipeline Implementer`, `Dashboard Operator`) or a prompt file.
4. For status questions, prefer MCP summary tools over broad file scans.
