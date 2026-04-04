---
name: audit-roadmap-feature
description: Audit a roadmap feature against the current code and state exactly what is done, partial, missing, and where the integration point lives.
agent: repo-planner
argument-hint: Feature name or roadmap excerpt to audit.
model: GPT-5.4 (copilot)
---
Audit the requested roadmap feature in this repository.

Inputs:
- Feature: ${input:feature:Feature name or roadmap excerpt}

Instructions:
- Start from [ROADMAP.md](ROADMAP.md).
- Read only the files needed to confirm the current implementation status.
- Return four sections: implemented, missing, integration point, recommended minimal change.
- If the roadmap is stale, say so explicitly and identify the code path that proves it.