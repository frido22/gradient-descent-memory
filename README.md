# MemoryGrad

Self improving memory for Codex and Claude Code.

MemoryGrad watches coding-agent sessions, turns failures and fixes into textual gradients, and proposes reviewed updates for repo memory files:

- `AGENTS.md`
- `CLAUDE.md`
- `.memorygrad/skills.md`

Tagline:

> Git commits remember code. MemoryGrad remembers how to work on the code.

## Why This Exists

[SkillOpt](https://arxiv.org/abs/2605.23904) gives the right research framing: treat a natural-language skill document as trainable external state for a frozen agent, then improve it with rollout evidence, bounded edits, validation gates, and rejected-edit memory. The [SkillOpt repo](https://github.com/microsoft/SkillOpt) is a full benchmark optimizer that trains and evaluates `best_skill.md` artifacts.

MemoryGrad is the repo-local product version of that idea for everyday coding work. It does not try to run a benchmark suite first. It watches normal Codex and Claude Code sessions, extracts only high-signal lessons from failures plus fixes, and proposes small reviewed patches to the memory files agents already read.

Use SkillOpt to train benchmarked skills. Use MemoryGrad to keep a real repository's agent memory improving as work happens.

For the paper-style framing, see [PAPER.md](PAPER.md).

## MVP

The MVP targets local Codex and Claude Code workflows. It does not need agent-specific private APIs. Instead, it records the durable evidence that is already present during normal work:

- task text
- terminal output or saved session logs
- git status
- working-tree diffs
- staged diffs
- the latest commit summary

It then generates a small "text gradient" and a proposed repo skill.

MemoryGrad is conservative by default. It only saves proposals that clear an 80% confidence threshold, and proposals need evidence of both:

- a failure or error
- a later resolution signal, such as passing tests or explicit fixed/resolved output

Low-confidence drafts are skipped instead of being written into repo memory. This keeps `AGENTS.md` and `CLAUDE.md` reserved for lessons that are specific, reusable, and likely to change future agent behavior.

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

The default confidence gate is high:

```bash
memorygrad watch --repo /path/to/repo --terminal-log session.log --once --min-confidence 0.80
```

### `memorygrad review`

Shows pending proposals and lets you accept or reject them.

```bash
memorygrad review --repo /path/to/repo
memorygrad review --repo /path/to/repo --accept-all
memorygrad review --repo /path/to/repo --accept mg_abc123
memorygrad review --repo /path/to/repo --reject mg_abc123
```

`review --accept-all` also respects the 80% threshold. Use `--force` only when you deliberately want to accept a lower-confidence proposal:

```bash
memorygrad review --repo /path/to/repo --accept-all --force
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

- API-route failures generate route-registration skills only when failures, passing/fixed signals, route errors, and `app/main.py` registration evidence line up.
- Generic test failures are drafted at lower confidence and are not saved by default; they are useful for diagnostics, not automatic memory.
- Duplicate skills are skipped by normalizing accepted and pending skill text.

The next useful step is adding an LLM-backed proposer behind the same review flow.
