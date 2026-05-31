# MemoryGrad

Self improving memory for Codex and Claude Code.

MemoryGrad watches coding-agent sessions, turns failures and fixes into textual gradients, and proposes reviewed updates for repo memory files:

- `AGENTS.md`
- `CLAUDE.md`
- `.memorygrad/skills.md`

Tagline:

> Git commits remember code. MemoryGrad remembers how to work on the code.

## MVP

The MVP targets local Codex and Claude Code workflows. It does not need agent-specific private APIs. Instead, it records the durable evidence that is already present during normal work:

- task text
- terminal output or saved session logs
- git status
- working-tree diffs
- staged diffs
- the latest commit summary

It then generates a small "text gradient" and a proposed repo skill.

Example gradient:

```text
The agent failed because it did not know that API routes in this repo must be registered in app/main.py before the API tests will pass.
```

Example skill:

```text
When adding or changing an API route, register the route/router in app/main.py and run pytest tests/api -q.
```

## Install For Local Development

```bash
cd /Users/frido_mac/Projects/memorygrad
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Quick Demo

Inside any target repo:

```bash
memorygrad init
memorygrad watch --task "Add /healthz" --terminal-log /path/to/session.log --once
memorygrad review
```

For a non-interactive demo:

```bash
memorygrad watch --repo /path/to/repo --task "Add /healthz" --terminal-log /path/to/session.log --once
memorygrad review --repo /path/to/repo --accept-all
```

Accepted skills are appended to:

- `/path/to/repo/AGENTS.md`
- `/path/to/repo/CLAUDE.md`
- `/path/to/repo/.memorygrad/skills.md`

## Commands

### `memorygrad init`

Creates the local `.memorygrad` directory and the skills ledger.

```bash
memorygrad init --repo /path/to/repo
```

### `memorygrad watch`

Records an episode snapshot and proposes skills when it sees a failure plus a likely fix.

```bash
memorygrad watch --repo /path/to/repo --task "Add /version" --terminal-log session.log --once
```

Use `--follow` to keep polling:

```bash
memorygrad watch --repo /path/to/repo --task "Improve API" --terminal-log session.log --follow --interval 10
```

### `memorygrad review`

Shows pending proposals and lets you accept or reject them.

```bash
memorygrad review --repo /path/to/repo
memorygrad review --repo /path/to/repo --accept-all
memorygrad review --repo /path/to/repo --accept mg_abc123
memorygrad review --repo /path/to/repo --reject mg_abc123
```

### `memorygrad status`

Shows episode and proposal counts.

```bash
memorygrad status --repo /path/to/repo
```

## Demo Scenario

1. Codex tries to add `/healthz`.
2. Tests fail because the route was not registered.
3. The fix adds route registration in `app/main.py`.
4. MemoryGrad ingests the terminal log and git diff.
5. MemoryGrad proposes:

```text
When adding or changing an API route, register the route/router in app/main.py and run pytest tests/api -q.
```

6. The user accepts it.
7. Future Codex or Claude Code runs read the lesson from `AGENTS.md` or `CLAUDE.md`.

## Current Heuristics

The first implementation is intentionally simple and inspectable:

- API-route failures generate route-registration skills when diffs or errors point at `app/main.py`, routers, 404s, or `tests/api`.
- Test failures generate repo-specific check skills based on failed test paths and changed files.
- Duplicate skills are skipped by normalizing accepted and pending skill text.

The next useful step is adding an LLM-backed proposer behind the same review flow.
