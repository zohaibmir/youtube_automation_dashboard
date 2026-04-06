# TODOs - Animated Shorts & Reels

Updated: 2026-04-06

## Completed

- Added Kling AI integration module: `animated_visual_fetcher.py`
- Added env/config support:
  - `KLING_API_KEY`
  - `KLING_API_SECRET`
  - `VISUAL_MODE=animated`
- Wired animated visual mode in `pipeline.py`
- Added backend endpoints in `server.py`:
  - `POST /api/shorts/generate-animated`
  - `GET /api/shorts/status`
  - `GET /api/shorts/list`
  - `POST /api/shorts/distribute`
- Added dedicated shorts-only pipeline endpoint:
  - `POST /api/shorts/pipeline/run`
- Added dashboard navigation item and full Shorts/Reels panel markup
- Repaired Shorts dashboard script wiring in `youtube_automation_dashboard.html`
  - Removed broken duplicate inline script block
  - Kept Shorts/Reels functions in the main dashboard script only once
  - Restored modal shorts count toggle using inline `onchange`
- Added dependency: `PyJWT>=2.8.0`
- Updated `.env.example` with Kling keys
- Added dedicated orchestration module: `shorts_pipeline.py`
  - `run_animated_shorts_pipeline(...)`
  - `distribute_shorts(...)`
- Refactored `server.py` shorts handlers to use `shorts_pipeline.py`
- Syntax-validated modified Python files (`py_compile`)
- Added Kling fields to main Settings panel (`panel-settings`):
  - `key-kling`
  - `key-kling-secret`
- Wired Kling fields through save/load/export flows in dashboard JS
- Extended `/api/settings/sync-env` mapping for Kling + API keys
- Added dedicated feature smoke test: `scripts/smoke_test_shorts.py`
- Ran `scripts/smoke_test_shorts.py` successfully

## Critical Blockers

- None at code-structure level right now.
- Remaining runtime blocker: Kling API returned HTTP 429 (rate limit/quota) during live 2-clip generation attempt.

## Remaining Work

### P0 - Must fix now

- Run browser smoke test for existing pipeline modal controls after script repair
- Run one live animated generation with valid Kling keys

### P1 - Functional verification

- End-to-end local test:
  - Generate animated short
  - Poll status
  - Render clips
  - Distribute to selected platforms
- End-to-end dedicated pipeline test:
  - `POST /api/shorts/pipeline/run`
  - Poll with `GET /api/shorts/status?job_id=...`
  - Validate `results` payload when platforms are selected
- Validate static serving of `/output/shorts_animated/...`
- Confirm `/api/settings` persist/save flow for Kling keys in Settings tab

### P2 - Deployment

- Create feature branch and commit all pending changes
- Deploy to Railway
- Add Railway env vars:
  - `KLING_API_KEY`
  - `KLING_API_SECRET`
  - Optional dashboard auth env vars if needed

## Recommended Architecture (Shorts-only Pipeline)

Current approach piggybacks Shorts generation into the existing full-video stack. For scale and reliability, add a dedicated Shorts pipeline path.

### Suggested design

1. Keep full-video pipeline unchanged (`pipeline.py`)
2. Add shorts-specific orchestrator (`shorts_pipeline.py`) ✅
3. Reuse shared providers/modules:
   - script prompt generation
   - Kling fetcher
   - social uploader
4. Add one API endpoint to launch shorts pipeline jobs and one for status ✅
5. Store job metadata in SQLite (`runs` or separate `shorts_runs` table)

### Why this is better

- Isolates long-form and shorts workflows
- Faster iteration on Shorts without risking full-video stability
- Cleaner cost tracking per format
- Easier future additions (templates, multi-clip batching, auto captions)

## Nice-to-have next

- Optional merge step to combine generated 5s clips into one 15-45s short
- Auto captions for Shorts (SRT burn-in)
- Per-platform caption templates and hashtag presets
- Retry policy for failed Kling clips (with fallback media strategy)
