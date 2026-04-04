---
name: dashboard-api-mapping
description: Use when adding or debugging a dashboard panel, polling behavior, or a button that talks to server.py endpoints. Trigger phrases: dashboard panel, render table, poll API, missing endpoint, front-end not wired.
---

# Dashboard API Mapping

Use this skill to map a dashboard requirement to the exact browser and server changes.

## Relevant files

- [youtube_automation_dashboard.html](youtube_automation_dashboard.html)
- [server.py](server.py)
- [README.md](README.md)

## Workflow

1. Find the nearest existing dashboard panel with similar behavior.
2. Identify the exact API endpoint or add the smallest new endpoint in [server.py](server.py).
3. Add or update the panel markup in [youtube_automation_dashboard.html](youtube_automation_dashboard.html).
4. Add client-side fetch, render, and error handling logic near related helpers.
5. If the feature polls, stop polling when the panel is not active.
6. Smoke test by running `python3 server.py` locally.

## Output expectations

- Clear mapping of panel to endpoint.
- Empty state and error state handling.
- No large-scale dashboard rewrites.