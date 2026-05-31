# MemoryGrad

Passive gradient memory for coding agents.

MemoryGrad watches coding-agent sessions, turns failures and fixes into textual gradients, and proposes reviewed updates for agent memory files:

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `.github/copilot-instructions.md`
- `.memorygrad/memory.md`

Tagline:

> Git commits remember code. MemoryGrad remembers how to work on the code.

## Why This Exists

[SkillOpt](https://arxiv.org/abs/2605.23904) gives the right research framing: treat a natural-language instruction document as trainable external state for a frozen agent, then improve it with rollout evidence, bounded edits, validation gates, and rejected-edit memory. The [SkillOpt repo](https://github.com/microsoft/SkillOpt) is a full benchmark optimizer that trains and evaluates `best_skill.md` artifacts.

MemoryGrad is the everyday coding-work version of that idea. It keeps both global memory and repo memory, uses Codex or Claude Code itself as the read-only optimizer, and proposes small reviewed patches to the memory files agents already read.

Use SkillOpt for benchmark optimization. Use MemoryGrad to keep a real repository's agent memory improving as work happens.

For the paper-style framing, see [PAPER.md](PAPER.md).

## MVP

The MVP targets local coding-agent workflows. It does not need private agent APIs. Instead, it records the durable evidence that is already present during normal work:

- task text
- terminal output or saved session logs
- git status
- working-tree diffs
- staged diffs
- the latest commit patch

It then asks the configured coding agent to act as a read-only optimizer. The optimizer returns bounded add/replace/delete edits with a text gradient, confidence, scope, and evidence.

MemoryGrad is conservative by default. Repo-memory proposals must clear a 90% confidence threshold; global-memory proposals must clear a 97% threshold. The optimizer is instructed to require evidence of both:

- a failure or error
- a later resolution signal, such as passing tests or explicit fixed/resolved output

Low-confidence drafts are written to rejected-edit buffers, not to the prompt files. Repo rejections live in `.memorygrad/rejected.md`; global rejections live in `~/.memorygrad/rejected.md`. Accepted lessons are kept in a compact active block with a default cap of 8 bullets. This keeps agent context reserved for lessons that are specific, reusable, and likely to change future behavior.

Memory scopes:

- global memory: `~/.memorygrad/memory.md`
- repo memory: `<repo>/.memorygrad/memory.md`
- active agent memory: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or `.github/copilot-instructions.md`

Example gradient:

```text
The agent failed because it did not know that API routes in this repo must be registered in app/main.py before the API tests will pass.
```

Example memory:

```text
When adding or changing an API route, register the route/router in app/main.py and run pytest tests/api -q.
```

## Install For Local Development

```bash
git clone https://github.com/frido22/memorygrad.git
cd memorygrad
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

Accepted memory is written to the configured targets, usually:

- `/path/to/repo/AGENTS.md`
- `/path/to/repo/CLAUDE.md`
- `/path/to/repo/.memorygrad/memory.md`

The full accepted history stays in `.memorygrad/memory.md`; the active memory files are rewritten from the latest accepted memory under the configured cap.

## Commands

### `memorygrad start`

Creates global defaults once. This does not need to run inside a repo.

```bash
memorygrad start
memorygrad start --targets agents
memorygrad start --targets core --min-confidence 0.90 --global-min-confidence 0.97 --max-active-memory 8
memorygrad start --optimizer codex
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
memorygrad init --repo /path/to/repo --targets core --min-confidence 0.90 --global-min-confidence 0.97 --max-active-memory 8
```

Target modes:

- `core`: `AGENTS.md` plus `CLAUDE.md` for Codex and Claude Code
- `agents`: only `AGENTS.md`
- `auto`: existing known target files, or `AGENTS.md` if none exist
- `all`: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and `.github/copilot-instructions.md`
- comma-separated aliases or paths, such as `agents,claude,GEMINI.md`

### `memorygrad watch`

Records an episode snapshot and proposes memory when it sees a failure plus a likely fix.

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
memorygrad sync --repo /path/to/repo --targets agents --max-active-memory 5
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

## Optimizer Loop

MemoryGrad now uses the coding agent itself as the optimizer:

- `optimizer=auto` chooses Codex when available, then Claude Code.
- Codex is run through `codex exec` with a read-only sandbox and structured JSON output.
- Claude Code can be used through its non-interactive print mode.
- A custom optimizer can be supplied with `MEMORYGRAD_OPTIMIZER_COMMAND`; it receives the optimizer prompt on stdin and returns JSON.
- The optimizer sees repo memory, global memory, rejected edits, terminal output, git status, diffs, and the latest commit patch.
- MemoryGrad still owns the gates: confidence thresholds, max edit count, duplicate suppression, review, rejected-edit storage, and syncing active memory files.

This keeps deployment cheap: future agent runs read accepted memory from normal project memory files and do not require an extra inference call.
