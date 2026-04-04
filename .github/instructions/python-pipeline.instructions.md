---
name: Python Pipeline Conventions
description: Use when editing Python modules in the YouTube automation pipeline, server, scheduler, media flow, uploads, or database code.
applyTo: "**/*.py"
---
# Python Pipeline Conventions

- Keep orchestration in `pipeline.py` and keep provider or platform logic in the specialist module that already owns it.
- Keep synchronous, straightforward control flow unless the file is already async.
- Preserve the repo's logging-first debugging style. Use `logger.info`, `logger.warning`, or `logger.error` instead of adding prints.
- Preserve compatibility with local file-based state: `runs/`, `.jobs/`, `tokens/`, and SQLite are part of the design.
- When adding a feature flag or setting, wire it through existing `.env`-backed config patterns instead of adding ad hoc constants.
- For pipeline changes, verify both the CLI path in `main.py` and the dashboard/API path in `server.py`.
- Prefer root-cause fixes over wrappers. If an upload feature is missing, wire the real integration point instead of adding duplicate code paths.