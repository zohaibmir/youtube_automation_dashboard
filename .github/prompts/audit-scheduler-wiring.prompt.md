---
name: audit-scheduler-wiring
description: Audit whether the scheduler is correctly configured and wired to the topic queue and pipeline flow.
agent: repo-planner
argument-hint: Optional focus such as cadence, queue refill, or channel selection.
model: GPT-5.4 (copilot)
---
Audit scheduler behavior in this repository.

Inputs:
- Focus: ${input:focus:Optional focus such as cadence, queue refill, or channel selection}

Instructions:
- Start from scheduler summaries in the repo MCP server.
- Confirm cadence and publish timing against scheduler.py.
- Confirm queue refill and dequeue flow through topic_queue.py.
- Return four sections: current wiring, risks, missing pieces, minimum safe fix.
