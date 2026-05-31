# Gradient Descent Memory: Passive Gradient Memory for Coding Agents

## Abstract

Coding agents improve code, but most repositories do not improve the agent instructions that guide future coding sessions. Gradient Descent Memory is a lightweight system that turns normal coding-agent work into reviewed updates for persistent global and repo memory. It records coding episodes, asks the coding agent itself to act as a read-only memory optimizer, and proposes bounded text updates for `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `~/.gradient-descent-memory/memory.md`, and `.gradient-descent-memory/memory.md`.

The design follows the core insight of SkillOpt: skills are external text state for frozen agents and should be improved with the discipline of an optimizer. Gradient Descent Memory narrows that idea to practical software repositories, where the available evidence is terminal output, git diffs, test results, commits, and human or agent fixes.

## Motivation

Git remembers what code changed. It does not remember how the agent should work differently next time.

That missing layer matters in real repositories. Coding agents often repeat repo-specific mistakes:

- adding an API route but forgetting the route registration file
- changing a generated artifact instead of the source template
- running the wrong test subset
- missing a local fixture, migration, or build step
- formatting output in a way the project rejects

These failures are useful training signal, but only if they are converted into compact, durable, reviewed instructions.

## Research Context

SkillOpt frames natural-language skills as trainable external state for frozen agents. Its loop uses scored rollouts, optimizer-proposed add/delete/replace edits, bounded textual learning rates, held-out validation gates, rejected-edit buffers, and exported `best_skill.md` artifacts.

Gradient Descent Memory adopts the same optimizer mindset but changes the product surface:

- SkillOpt optimizes a skill against benchmark splits.
- Gradient Descent Memory captures everyday coding sessions inside live repositories.
- SkillOpt exports a benchmarked `best_skill.md`.
- Gradient Descent Memory proposes small patches to global and repo agent memory files such as `~/.gradient-descent-memory/memory.md`, `AGENTS.md`, `CLAUDE.md`, and `.gradient-descent-memory/memory.md`.
- SkillOpt is active training.
- Gradient Descent Memory is passive repo memory with human review.

This makes Gradient Descent Memory complementary to SkillOpt rather than a replacement.

## System

Gradient Descent Memory runs as:

```bash
gradient-descent-memory init
gradient-descent-memory start
gradient-descent-memory learn
gradient-descent-memory watch
gradient-descent-memory review
gradient-descent-memory sync
```

A recorded episode contains:

```text
task -> agent actions -> errors -> fix evidence -> tests pass -> commit or diff
```

The easiest path is global-first: `gradient-descent-memory start` writes one global default config and global memory store, and `gradient-descent-memory learn` auto-initializes each repository when it ingests an episode. Global memory captures transferable agent behavior; repo memory captures project-specific behavior.

The MVP records:

- task text
- terminal output or saved session logs
- git status
- working tree diffs
- staged diffs
- latest commit patch

From this evidence, the configured optimizer agent produces a text gradient:

```text
The agent failed because it did not know that API routes in this repo must be registered in app/main.py before the API tests will pass.
```

Then it proposes a bounded add/replace/delete memory edit:

```text
When adding or changing an API route, register the route/router in app/main.py and run pytest tests/api -q.
```

## Quality Policy

Repo memory should be sparse. Bad memory is worse than no memory because future agents will follow it.

Gradient Descent Memory therefore uses a high default threshold:

- repo proposals must clear 90% confidence by default
- global proposals must clear 97% confidence by default
- proposals need failure evidence
- proposals need a later resolution signal, such as passing tests or explicit fixed/resolved output
- low-confidence drafts are rejected into repo or global rejected-edit buffers, outside agent prompt context
- `review --accept-all` still respects the confidence gate unless `--force` is explicit
- accepted prompt memory is capped to 8 active bullets by default

The goal is not to remember every episode. The goal is to remember only lessons that are specific, reusable, and likely to change future behavior.

## Memory Targets

Gradient Descent Memory treats `AGENTS.md` as the portable baseline for coding agents and supports tool-specific targets for agent runners that read their own project memory files:

- `AGENTS.md` for Codex and general agent instructions
- `CLAUDE.md` for Claude Code
- `GEMINI.md` for Gemini CLI-style workflows
- `.github/copilot-instructions.md` for GitHub Copilot project instructions

The default target set is `core`: `AGENTS.md` plus `CLAUDE.md`. Users can switch to `agents`, `auto`, `all`, or explicit comma-separated paths. The active memory block is rewritten from accepted proposals, so changing targets does not duplicate old entries.

## SkillOpt-Inspired Controls

Gradient Descent Memory implements a small subset of the SkillOpt control loop for everyday coding work:

- rollout evidence: terminal logs, git status, diffs, test output, and commits
- textual gradient: a short failure explanation tied to reusable behavior
- bounded update: small add/replace/delete memory proposals, capped active memory
- optimizer agent: Codex or Claude Code runs in read-only optimizer mode and returns structured JSON
- validation gate: separate repo and global thresholds plus user review
- rejected-edit buffer: low-confidence and user-rejected edits retained outside context
- exported memory artifact: the compact memory block read by the next coding agent

## Optimizer Implementation

SkillOpt uses a separate optimizer model to edit the skill document. Gradient Descent Memory makes the product tradeoff the user wanted for coding agents: the installed coding agent can optimize its own external memory artifacts.

The default optimizer is `auto`:

- use Codex when `codex` is available
- otherwise use Claude Code when `claude` is available
- otherwise use `GRADIENT_DESCENT_MEMORY_OPTIMIZER_COMMAND`

Gradient Descent Memory still controls persistence. The optimizer can propose edits, but Gradient Descent Memory applies confidence gates, stores rejected edits, requires review unless `--accept-all` is explicit, and syncs only the accepted active memory into prompt files.

## Demo

1. Codex tries to add `/healthz`.
2. Tests fail because the route is not registered.
3. The fix adds registration in `app/main.py`.
4. Gradient Descent Memory sees the failed test, the fix diff, and the later passing test.
5. It proposes one high-confidence lesson.
6. The user accepts it.
7. Future Codex or Claude Code sessions read the lesson from repo memory.

## Positioning

Gradient Descent Memory is not a benchmark optimizer. It is not a replacement for SkillOpt. It is a practical bridge between coding-agent traces and the global plus project memory files that Codex and Claude Code already use.

The product bet is simple:

> Every accepted coding fix should have the chance to improve the next coding agent run.

## References

- SkillOpt: Executive Strategy for Self-Evolving Agent Skills, arXiv:2605.23904, https://arxiv.org/abs/2605.23904
- microsoft/SkillOpt, https://github.com/microsoft/SkillOpt
