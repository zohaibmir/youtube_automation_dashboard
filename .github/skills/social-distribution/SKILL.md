---
name: social-distribution
description: Use when working on Instagram, Facebook, TikTok, Reels, Stories, or Shorts distribution in this repo. Trigger phrases: social upload, Instagram Reels, Facebook Reels, TikTok upload, post Shorts after upload, multi-platform distribution.
---

# Social Distribution

This repo already contains the provider logic in [social_uploader.py](social_uploader.py). Most work is about deciding when to call it and with what payload.

## Relevant files

- [social_uploader.py](social_uploader.py)
- [pipeline.py](pipeline.py)
- [server.py](server.py)
- [tokens/social_platforms.json](tokens/social_platforms.json) if present

## Workflow

1. Check the current entry points in [social_uploader.py](social_uploader.py), especially `upload_to_platforms`.
2. Determine whether the task is manual upload, dashboard-triggered upload, or automatic post-pipeline upload.
3. Reuse existing `title`, `description`, and generated Shorts paths instead of inventing a second content model.
4. Keep failures per-platform isolated so one provider failure does not break the main video path unless explicitly required.
5. Preserve existing token and settings storage in `tokens/social_platforms.json`.

## This skill is especially useful for

- Wiring auto-post of generated Shorts after successful YouTube upload.
- Adding feature flags for which social platforms should be auto-posted.
- Debugging why a configured platform is skipped or fails.