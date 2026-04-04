---
name: wire-social-shorts
description: Implement automatic Shorts posting to configured social platforms after the main pipeline completes.
agent: pipeline-implementer
argument-hint: Platforms, gating rules, or feature-flag requirements.
tools: ["read_file", "grep_search", "file_search", "apply_patch", "run_in_terminal", "get_errors"]
model: GPT-5.4 (copilot)
---
Implement automatic social distribution of generated Shorts in this repository.

Inputs:
- Constraints: ${input:constraints:Optional platform list, feature flags, or rollout rules}

Requirements:
- Reuse existing logic in [social_uploader.py](social_uploader.py).
- Wire the missing integration point in [pipeline.py](pipeline.py) instead of duplicating upload code elsewhere.
- Keep the main video success path resilient if one social platform fails.
- Update any required config wiring only if the repo already has a settings pattern for it.
- Validate syntax after editing and summarize the exact runtime flow.