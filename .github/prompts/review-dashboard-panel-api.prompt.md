---
name: review-dashboard-panel-api
description: Review dashboard panel wiring against API endpoints and identify missing or mismatched mappings.
agent: dashboard-operator
argument-hint: Panel name or endpoint group.
model: GPT-5.4 (copilot)
---
Review panel-to-endpoint wiring.

Inputs:
- Panel: ${input:panel:Panel name such as jobs, studio, yt-automation, or settings}

Instructions:
- Start from dashboard panel mapping MCP summaries.
- Verify that each panel action has a matching endpoint in server.py.
- Highlight mismatches, stale wiring, or missing endpoints.
- Suggest the minimum viable fix path.
