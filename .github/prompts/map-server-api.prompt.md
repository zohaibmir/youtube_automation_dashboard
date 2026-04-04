---
name: map-server-api
description: Produce a compact map of the local API surface in server.py, grouped by pipeline, dashboard, channels, studio, branding, and social features.
agent: repo-planner
argument-hint: Optional endpoint group to focus on.
model: GPT-5.4 (copilot)
---
Map the API surface of this repository.

Inputs:
- Focus: ${input:focus:Optional group such as pipeline, social, studio, or dashboard}

Instructions:
- Use [server.py](server.py) as the source of truth.
- Group endpoints by feature area.
- For each relevant endpoint, include method, path, main side effect, and primary downstream module.
- Keep the output compact enough to avoid re-reading the whole file later.