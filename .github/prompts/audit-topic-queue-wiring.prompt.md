---
name: audit-topic-queue-wiring
description: Audit topic queue lifecycle and whether queue state is visible and correctly consumed by scheduler and dashboard flows.
agent: repo-planner
argument-hint: Optional focus such as retries, stuck processing rows, or dashboard visibility.
model: GPT-5.4 (copilot)
---
Audit topic queue lifecycle wiring.

Inputs:
- Focus: ${input:focus:Optional focus such as retries, stuck processing rows, or dashboard visibility}

Instructions:
- Start from topic queue MCP summary and related database status.
- Confirm enqueue, dequeue, done, and failed transitions.
- Confirm where queue state is consumed by scheduler and exposed to the dashboard.
- Return concise findings and the smallest recommended correction.
