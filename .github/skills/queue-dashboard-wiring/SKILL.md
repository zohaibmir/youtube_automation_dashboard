---
name: queue-dashboard-wiring
description: Use when validating or fixing how topic queue state appears in dashboard panels and API responses. Trigger phrases: queue not visible, dashboard queue mismatch, queue API wiring, queue panel stale.
---

# Queue Dashboard Wiring

Use this skill when queue state in the dashboard does not match backend reality.

## Relevant files

- [topic_queue.py](topic_queue.py)
- [server.py](server.py)
- [youtube_automation_dashboard.html](youtube_automation_dashboard.html)

## Workflow

1. Pull queue and dashboard map summaries from MCP.
2. Verify queue status transitions in backend code.
3. Verify API endpoint payload shape in server.py.
4. Verify panel render and polling behavior in dashboard script.
5. Apply the smallest fix at the actual mismatch point.
