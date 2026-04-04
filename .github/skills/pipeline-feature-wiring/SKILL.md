---
name: pipeline-feature-wiring
description: Use when wiring a partially implemented roadmap feature into the main pipeline, server flow, or upload sequence. Trigger phrases: wire feature into pipeline, missing integration point, roadmap says code exists but not wired, connect server endpoint to pipeline.
---

# Pipeline Feature Wiring

Use this skill for features that already have implementation code but are missing the final integration point.

## Relevant files

- [pipeline.py](pipeline.py)
- [server.py](server.py)
- [ROADMAP.md](ROADMAP.md)
- The specialist module for the feature, such as [social_uploader.py](social_uploader.py) or [reddit_poster.py](reddit_poster.py)

## Workflow

1. Confirm the feature status in [ROADMAP.md](ROADMAP.md).
2. Read the orchestration path in [pipeline.py](pipeline.py) and identify where the new behavior should run.
3. Read the owning specialist module and verify the public entry point already exists.
4. If UI or API triggers are involved, inspect [server.py](server.py) for the current request path.
5. Implement the smallest change that wires the existing behavior into the main path.
6. Validate imports and run a focused smoke check.

## Common examples in this repo

- Auto-post Shorts to Instagram or TikTok after pipeline completion.
- Convert a manual upload flow already exposed in `server.py` into an automatic pipeline step.
- Promote a dashboard-only capability into the CLI pipeline path.