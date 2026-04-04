# Copilot Beginner Guide For This Project

This file explains what was added to the repository, why it matters, and how it helps you work faster with GitHub Copilot while spending fewer tokens.

## What Changed

We added a repo-specific customization layer for Copilot.

That layer now includes:

- Workspace instructions in `.github/copilot-instructions.md`
- File-specific instructions in `.github/instructions/`
- Custom agents in `.github/agents/`
- Reusable skills in `.github/skills/`
- Reusable prompts in `.github/prompts/`
- A local MCP server in `scripts/repo_mcp_server.py`
- Workspace MCP config in `.vscode/mcp.json`

These changes help Copilot understand this repository as a YouTube automation system instead of treating it like a generic Python project.

## Why This Helps Beginners

Without repo-specific guidance, Copilot has to rediscover the same things again and again:

- which file is the real pipeline entry point
- which file serves the dashboard API
- where social upload logic already exists
- which roadmap items are partially done versus missing
- which commands are safe to run locally

That repeated rediscovery costs tokens and also increases the chance of weak suggestions.

With the new setup, Copilot can start from the correct files and workflows much earlier.

## Token Savings: The Main Idea

Token usage grows when Copilot has to read too many files, re-check the same architecture, or infer project structure from scratch.

The changes reduce that waste in five ways.

### 1. Always-on instructions reduce repeated explanation

The workspace instructions tell Copilot:

- this is a single Python application
- `pipeline.py` is the orchestrator
- `server.py` is the API surface
- `youtube_automation_dashboard.html` is the single-file dashboard
- roadmap checks should start from `ROADMAP.md`

That means you do not have to repeat basic repo context in every chat.

### 2. File-specific instructions reduce broad scans

When editing Python files, Copilot gets Python pipeline guidance.

When editing the dashboard, Copilot gets dashboard-specific guidance.

When auditing roadmap items, Copilot gets roadmap-specific guidance.

This prevents loading unrelated habits for every task.

### 3. Custom agents keep work scoped

Instead of using one general-purpose workflow for everything, you now have focused agents:

- `Repo Planner` for read-only analysis
- `Pipeline Implementer` for pipeline and API changes
- `Dashboard Operator` for dashboard and browser wiring

This reduces wasted turns where Copilot first explores too much and only later realizes which path matters.

### 4. Prompts make common requests shorter

Instead of writing a long custom message every time, you can use prompts such as:

- `/audit-roadmap-feature`
- `/wire-social-shorts`
- `/map-server-api`

That keeps your own prompt short while still giving Copilot structured instructions.

### 5. The MCP server returns small, targeted repo facts

The local MCP server can answer repo-specific questions without forcing Copilot to re-read large files.

Examples:

- repo overview
- pipeline stage map
- grouped API surface
- social platform readiness
- recent job state
- lightweight database snapshot

This is one of the biggest token savers because it converts large-file re-reading into small, structured tool results.

## How These Changes Help In Copilot

Here is the practical impact when using Copilot in this project.

### Better first answer quality

Copilot now has stronger default knowledge about:

- where the real integration points are
- how pipeline work differs from dashboard work
- which files are the source of truth
- how to check feature status without guessing

That usually leads to fewer correction turns.

### Less hallucinated architecture

In a generic repo, Copilot may assume frameworks, patterns, or abstractions that do not exist.

In this repo, the instructions now keep it aligned with the actual architecture:

- single-file dashboard
- local HTTP server
- orchestrator pattern in `pipeline.py`
- provider modules like `social_uploader.py`
- file-based runtime state in `.jobs/`, `runs/`, `tokens/`, and SQLite

### Faster feature audits

If you ask whether something is done, partial, or missing, Copilot now has dedicated roadmap-aware guidance and a repo planner path for that exact job.

### Better tool usage

The custom setup nudges Copilot toward:

- reading only the relevant sections of files
- using the repo MCP server for compact answers
- choosing a focused agent or prompt instead of starting from scratch

## How To Use The New Setup

### Step 1. Start the workspace MCP server in VS Code

Open the MCP server UI in VS Code and trust the workspace server defined in `.vscode/mcp.json`.

Once started, the `youtube-automation` MCP tools become available in chat.

### Step 2. Use the right agent for the job

Use `Repo Planner` when you want:

- a feature audit
- a minimal implementation plan
- confirmation of what is wired and what is not

Use `Pipeline Implementer` when you want:

- changes in `pipeline.py`
- `server.py` endpoint changes
- upload flow or automation wiring

Use `Dashboard Operator` when you want:

- new panels
- API polling
- browser-side fixes
- panel-to-endpoint wiring

### Step 3. Use prompts for repeated tasks

Useful examples:

- `/audit-roadmap-feature feature="Social Upload"`
- `/map-server-api focus="social"`
- `/wire-social-shorts constraints="auto-post TikTok and Instagram only if platform is enabled"`

### Step 4. Ask shorter, more direct questions

Old style:

```text
Please inspect the roadmap, check pipeline.py, server.py, social_uploader.py,
see whether social upload is already wired, and if not find the missing
integration point and explain the smallest safe fix.
```

New style:

```text
/audit-roadmap-feature feature="Social Upload"
```

Or:

```text
Use Repo Planner to audit the social upload wiring.
```

## What Else We Can Do To Save More Tokens

There is still room to improve.

### 1. Add more MCP tools for high-repeat questions

Good candidates in this repo:

- current scheduler state
- topic queue status
- channel registry summary
- social token config summary
- latest output artifacts in `runs/` and `output/`
- dashboard panel to endpoint map

These are excellent MCP targets because they are small, stable summaries of large or messy runtime state.

### 2. Add more prompts for recurring workflows

Good prompt candidates:

- audit scheduler wiring
- audit topic queue wiring
- review dashboard panel against API
- trace upload path for a given feature
- summarize recent job failures

### 3. Add more skills for repeated multi-file tasks

Good skill candidates:

- scheduler verification
- queue-to-dashboard wiring
- YouTube upload and metadata flow
- SQLite analytics debugging

Skills are useful when the task follows the same multi-step path each time.

### 4. Add more resources to the MCP server

Right now the MCP server already exposes useful repo context.

We can expand it with resources such as:

- `repo://pipeline-summary`
- `repo://social-status`
- `repo://dashboard-panels`
- `repo://roadmap-partials`

This helps Copilot attach just the exact summary it needs.

### 5. Add a small runtime summary cache

If needed, we can create a generated status snapshot that summarizes:

- active channels
- enabled social platforms
- latest jobs
- latest outputs
- key feature flags

That would make repeated environment checks even cheaper.

### 6. Add prompt conventions for humans

Even with good customizations, short human prompts help a lot.

Better prompt patterns:

- name the feature
- name the owning file if you know it
- say whether you want audit, plan, implement, or review
- ask for minimum change when you want low risk

Example:

```text
Use Pipeline Implementer. Wire social upload into pipeline.py with minimum change.
```

## Recommended Beginner Workflow

For most work in this repo, this sequence is efficient.

1. Use `Repo Planner` or `/audit-roadmap-feature` first.
2. Confirm what is already implemented.
3. Hand off to `Pipeline Implementer` or `Dashboard Operator` only after the integration point is clear.
4. Use the MCP server when you need repo summaries instead of asking Copilot to reread large files.

This keeps both tokens and mistakes down.

## Example: Why This Matters For Social Upload

Before these changes, a request like this could trigger a broad repo scan:

```text
Can you check whether Instagram and TikTok auto-posting is already wired?
```

Copilot might need to inspect:

- `ROADMAP.md`
- `pipeline.py`
- `server.py`
- `social_uploader.py`
- maybe dashboard files too

Now the workflow can be much tighter:

- use `Repo Planner` or `/audit-roadmap-feature`
- use the MCP server to get pipeline stage map and social wiring state
- inspect only the final integration point before editing

That means fewer tokens and usually a faster answer.

## Bottom Line

The current changes help Copilot by giving it structured repo awareness.

That improves:

- relevance
- accuracy
- speed
- repeatability
- token efficiency

The biggest win is not magic compression. The biggest win is avoiding unnecessary rediscovery.

If we continue building on this setup, the next best investments are more repo-specific MCP tools, more recurring prompts, and a few more narrowly scoped skills for common audit and wiring tasks.