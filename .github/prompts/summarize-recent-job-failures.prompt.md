---
name: summarize-recent-job-failures
description: Summarize recent failed or stale jobs with likely root causes and next debugging steps.
agent: repo-planner
argument-hint: Number of failures to inspect.
model: GPT-5.4 (copilot)
---
Summarize recent pipeline failures.

Inputs:
- Limit: ${input:limit:Number of failures to inspect, default 10}

Instructions:
- Use failure-focused MCP summaries first.
- Group failures by recurring error patterns.
- Identify likely root causes and impacted stage.
- Return actionable next checks and minimal fixes.
