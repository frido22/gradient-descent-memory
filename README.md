# Gradient Descent Memory

Self-improving memory for coding agents.

Gradient Descent Memory watches normal Codex, Claude Code, and other coding-agent work, then turns failures and fixes into reviewed memory edits. It is inspired by [SkillOpt](https://arxiv.org/abs/2605.23904): treat natural-language memory as external trainable state, improve it from rollout evidence, and keep noisy edits out of context.

The CLI is still short:

```bash
memorygrad
```

## What It Does

`memorygrad learn` records one coding episode:

```text
task -> terminal output -> git diffs -> latest commit patch -> tests/fix signal
```

Then it asks the coding agent itself to act as a read-only optimizer. Codex or Claude Code proposes bounded memory edits:

- `add`
- `replace`
- `delete`

Each proposal includes:

- scope: `repo` or `global`
- text gradient: what the agent failed to know
- memory edit: what future agents should remember
- confidence
- evidence

MemoryGrad applies the gates, stores rejected edits, and only syncs accepted memory into agent files.

## Memory Layers

- Global memory: `~/.memorygrad/memory.md`
- Repo memory: `<repo>/.memorygrad/memory.md`
- Active agent files: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`

Defaults are intentionally conservative:

- repo-memory gate: `90%`
- global-memory gate: `97%`
- active memory cap: `8` bullets
- low-confidence edits go to rejected buffers, not prompt context

## Example

Gradient:

```text
The agent failed because it did not know that API routes in this repo must be registered in app/main.py.
```

Accepted memory:

```text
When adding or changing an API route, register the route/router in app/main.py and run pytest tests/api -q.
```

## Install

```bash
git clone https://github.com/frido22/gradient-descent-memory.git
cd gradient-descent-memory
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Use

One-time setup:

```bash
memorygrad start
```

After an agent session:

```bash
memorygrad learn "Add /healthz" --log session.log
memorygrad review
```

Non-interactive demo:

```bash
memorygrad learn "Add /healthz" --log session.log --accept-all
```

Useful options:

```bash
memorygrad start --optimizer codex
memorygrad start --optimizer claude
memorygrad start --targets core --min-confidence 0.90 --global-min-confidence 0.97
memorygrad sync --targets all
memorygrad status
```

For custom optimizers:

```bash
MEMORYGRAD_OPTIMIZER_COMMAND="./my-optimizer" memorygrad learn "Fix parser" --log session.log
```

The custom command receives the optimizer prompt on stdin and must return JSON.

## Why It Matters

Git remembers code changes. Gradient Descent Memory remembers how agents should work on the code.

Accepted memory improves future agent runs without retraining the model and without adding an extra inference call at deployment time.
