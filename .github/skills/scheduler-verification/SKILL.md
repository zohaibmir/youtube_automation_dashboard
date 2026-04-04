---
name: scheduler-verification
description: Use when verifying scheduler behavior, cadence, queue refill, and scheduled publish readiness. Trigger phrases: scheduler not running, scheduler status, cadence check, schedule wiring, auto-run verification.
---

# Scheduler Verification

Use this skill to verify whether automated publishing is wired and behaving as expected.

## Relevant files

- [scheduler.py](scheduler.py)
- [topic_queue.py](topic_queue.py)
- [pipeline.py](pipeline.py)

## Workflow

1. Read scheduler summary from MCP first.
2. Confirm publish cadence and configured publish time.
3. Confirm queue refill threshold and dequeue behavior.
4. Confirm scheduler invokes pipeline run with the expected channel selection.
5. Report whether the issue is configuration, queue state, or runtime execution.
