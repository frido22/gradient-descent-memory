# MemoryGrad

Passive gradient memory for coding agents.

MemoryGrad watches coding-agent sessions, turns failures and fixes into textual gradients, and proposes reviewed updates for agent memory files:

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `.github/copilot-instructions.md`
- `.memorygrad/skills.md`

Tagline:

> Git commits remember code. MemoryGrad remembers how to work on the code.

## Why This Exists

[SkillOpt](https://arxiv.org/abs/2605.23904) gives the right research framing: treat a natural-language skill document as trainable external state for a frozen agent, then improve it with rollout evidence, bounded edits, validation gates, and rejected-edit memory. The [SkillOpt repo](https://github.com/microsoft/SkillOpt) is a full benchmark optimizer that trains and evaluates `best_skill.md` artifacts.

MemoryGrad is the repo-local product version of that idea for everyday coding work. It does not try to run a benchmark suite first. It watches normal Codex and Claude Code sessions, extracts only high-signal lessons from failures plus fixes, and proposes small reviewed patches to the memory files agents already read.

Use SkillOpt to train benchmarked skills. Use MemoryGrad to keep a real repository's agent memory improving as work happens.

For the paper-style framing, see [PAPER.md](PAPER.md).

## MVP

The MVP targets local coding-agent workflows. It does not need agent-specific private APIs. Instead, it records the durable evidence that is already present during normal work:

- task text
- terminal output or saved session logs
- git status
- working-tree diffs
- staged diffs
- the latest commit summary

It then generates a small "text gradient" and a proposed repo skill.

MemoryGrad is conservative by default. It only saves proposals that clear a 90% confidence threshold, and proposals need evidence of both:

- a failure or error
- a later resolution signal, such as passing tests or explicit fixed/resolved output

Low-confidence drafts are written to `.memorygrad/rejected.md`, not to the prompt files. Accepted lessons are kept in a compact active block with a default cap of 8 bullets. This keeps agent context reserved for lessons that are specific, reusable, and likely to change future behavior.

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

One-time setup from anywhere:

```bash
memorygrad start
```

Then, after a coding-agent session, run this inside the repo:

```bash
memorygrad learn "Add /healthz" --log session.log
memorygrad review
```

That is the normal path. `learn` auto-initializes `.memorygrad/` in the repo the first time it ingests a session.

For a non-interactive demo:

```bash
memorygrad learn "Add /healthz" --repo /path/to/repo --log /path/to/session.log --accept-all
```

Accepted skills are written to the configured targets, usually:

- `/path/to/repo/AGENTS.md`
- `/path/to/repo/CLAUDE.md`
- `/path/to/repo/.memorygrad/skills.md`

The full accepted history stays in `.memorygrad/skills.md`; the active memory files are rewritten from the latest accepted skills under the configured cap.

## Commands

### `memorygrad start`

Creates global defaults once. This does not need to run inside a repo.

```bash
memorygrad start
memorygrad start --targets agents
memorygrad start --targets core --min-confidence 0.90 --max-active-skills 8
```

Global start defaults to `auto`, which uses existing known memory files when present and otherwise starts with `AGENTS.md` only.

### `memorygrad learn`

The easy ingest command. It auto-initializes the current repo from the global defaults.

```bash
memorygrad learn "Add /version" --log session.log
memorygrad learn "Add /version" --log session.log --review
memorygrad learn "Add /version" --log session.log --accept-all
```

### `memorygrad init`

Advanced per-repo setup. Most users can use `memorygrad start` globally and skip this.

```bash
memorygrad init --repo /path/to/repo
memorygrad init --repo /path/to/repo --targets core --min-confidence 0.90 --max-active-skills 8
```

Target modes:

- `core`: `AGENTS.md` plus `CLAUDE.md` for Codex and Claude Code
- `agents`: only `AGENTS.md`
- `auto`: existing known target files, or `AGENTS.md` if none exist
- `all`: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and `.github/copilot-instructions.md`
- comma-separated aliases or paths, such as `agents,claude,GEMINI.md`

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
memorygrad watch --repo /path/to/repo --terminal-log session.log --once --min-confidence 0.90
```

### `memorygrad review`

Shows pending proposals and lets you accept or reject them.

```bash
memorygrad review --repo /path/to/repo
memorygrad review --repo /path/to/repo --accept-all
memorygrad review --repo /path/to/repo --accept mg_abc123
memorygrad review --repo /path/to/repo --reject mg_abc123
```

`review --accept-all` also respects the 90% threshold. Use `--force` only when you deliberately want to accept a lower-confidence proposal:

```bash
memorygrad review --repo /path/to/repo --accept-all --force
```

### `memorygrad sync`

Rewrites configured target files from accepted proposals. Use this after changing targets or the active memory cap.

```bash
memorygrad sync --repo /path/to/repo
memorygrad sync --repo /path/to/repo --targets agents --max-active-skills 5
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
- Rejected edits are retained outside prompt context in `.memorygrad/rejected.md`.
- Accepted prompt context is bounded by `max_active_skills`.

The next useful step is adding an LLM-backed proposer behind the same review flow.
