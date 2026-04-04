# YouTube Automation Workspace Instructions

- Prefer targeted context over broad scans. Start from [pipeline.py](pipeline.py), [server.py](server.py), [youtube_automation_dashboard.html](youtube_automation_dashboard.html), and [ROADMAP.md](ROADMAP.md).
- Treat this repo as a single Python application with a single-file HTML dashboard, not as a framework app.
- Preserve the existing architecture: `pipeline.py` orchestrates, specialist modules implement platform-specific behavior, and `server.py` is the local API surface.
- Keep changes minimal and local. Do not introduce large refactors, new frameworks, or multi-file abstractions unless the current code already requires them.
- When changing upload behavior, verify the full flow across `pipeline.py`, `server.py`, `youtube_uploader.py`, `social_uploader.py`, and any dashboard controls that surface the feature.
- When changing dashboard behavior, verify both the HTML panel markup and the API endpoints it depends on in `server.py`.
- Reuse existing environment and token patterns. This repo stores mutable runtime state in `.env`, `tokens/`, `runs/`, `.jobs/`, and SQLite databases.
- For feature work, check [ROADMAP.md](ROADMAP.md) before concluding whether something is done, partial, or intentionally missing.
- Prefer running the local Python server with `source .venv/bin/activate && python3 server.py` for UI work and `source .venv/bin/activate && python3 main.py "topic"` for pipeline work.
- Avoid reading huge files end-to-end if a narrower section or the local MCP server can answer the question.