# MemoryGrad: Passive Gradient Memory for Coding Agents

## Abstract

Coding agents improve code, but most repositories do not improve the agent instructions that guide future coding sessions. MemoryGrad is a lightweight repo-local system that turns normal coding-agent work into reviewed updates for persistent agent memory. It records coding episodes, extracts high-signal lessons from failures and fixes, and proposes bounded text updates for `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, and `.memorygrad/skills.md`.

The design follows the core insight of SkillOpt: skills are external text state for frozen agents and should be improved with the discipline of an optimizer. MemoryGrad narrows that idea to practical software repositories, where the available evidence is terminal output, git diffs, test results, commits, and human or agent fixes.

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

MemoryGrad adopts the same optimizer mindset but changes the product surface:

- SkillOpt optimizes a skill against benchmark splits.
- MemoryGrad captures everyday coding sessions inside a live repository.
- SkillOpt exports a benchmarked `best_skill.md`.
- MemoryGrad proposes small patches to repo-local agent memory files such as `AGENTS.md`, `CLAUDE.md`, and `.memorygrad/skills.md`.
- SkillOpt is active training.
- MemoryGrad is passive repo memory with human review.

This makes MemoryGrad complementary to SkillOpt rather than a replacement.

## System

MemoryGrad runs as:

```bash
memorygrad init
memorygrad start
memorygrad learn
memorygrad watch
memorygrad review
memorygrad sync
```

A recorded episode contains:

```text
task -> agent actions -> errors -> fix evidence -> tests pass -> commit or diff
```

The easiest path is global-first: `memorygrad start` writes one global default config, and `memorygrad learn` auto-initializes each repository when it ingests an episode. This keeps setup independent from any single repo while preserving repo-local accepted memory.

The MVP records:

- task text
- terminal output or saved session logs
- git status
- working tree diffs
- staged diffs
- latest commit summary

From this evidence it produces a text gradient:

```text
The agent failed because it did not know that API routes in this repo must be registered in app/main.py before the API tests will pass.
```

Then it proposes a bounded skill update:

```text
When adding or changing an API route, register the route/router in app/main.py and run pytest tests/api -q.
```

## Quality Policy

Repo memory should be sparse. Bad memory is worse than no memory because future agents will follow it.

MemoryGrad therefore uses a high default threshold:

- proposals must clear 90% confidence by default
- proposals need failure evidence
- proposals need a later resolution signal, such as passing tests or explicit fixed/resolved output
- low-confidence drafts are rejected into `.memorygrad/rejected.md`, outside agent prompt context
- `review --accept-all` still respects the confidence gate unless `--force` is explicit
- accepted prompt memory is capped to 8 active bullets by default

The goal is not to remember every episode. The goal is to remember only lessons that are specific, reusable, and likely to change future behavior.

## Memory Targets

MemoryGrad treats `AGENTS.md` as the portable baseline for coding agents and supports tool-specific targets for agent runners that read their own project memory files:

- `AGENTS.md` for Codex and general agent instructions
- `CLAUDE.md` for Claude Code
- `GEMINI.md` for Gemini CLI-style workflows
- `.github/copilot-instructions.md` for GitHub Copilot project instructions

The default target set is `core`: `AGENTS.md` plus `CLAUDE.md`. Users can switch to `agents`, `auto`, `all`, or explicit comma-separated paths. The active memory block is rewritten from accepted proposals, so changing targets does not duplicate old entries.

## SkillOpt-Inspired Controls

MemoryGrad implements a small subset of the SkillOpt control loop in a repo-local form:

- rollout evidence: terminal logs, git status, diffs, test output, and commits
- textual gradient: a short failure explanation tied to reusable behavior
- bounded update: one small skill proposal at a time, capped active memory
- validation gate: high confidence plus failure and resolution evidence
- rejected-edit buffer: low-confidence and user-rejected edits retained outside context
- exported skill artifact: the compact memory block read by the next coding agent

## MVP Heuristics

The current deterministic analyzer handles:

- API route registration failures, especially when `tests/api`, 404 output, router diffs, and `app/main.py` evidence line up
- generic failed-test lessons at lower confidence, useful for review but blocked from default automatic acceptance
- duplicate avoidance by normalizing accepted and pending skills

This keeps the first release inspectable and testable. An LLM-backed proposer can later sit behind the same review gate.

## Demo

1. Codex tries to add `/healthz`.
2. Tests fail because the route is not registered.
3. The fix adds registration in `app/main.py`.
4. MemoryGrad sees the failed test, the fix diff, and the later passing test.
5. It proposes one high-confidence lesson.
6. The user accepts it.
7. Future Codex or Claude Code sessions read the lesson from repo memory.

## Positioning

MemoryGrad is not a general prompt optimizer. It is not a replacement for SkillOpt. It is a narrow, practical bridge between coding-agent traces and the project memory files that Codex and Claude Code already use.

The product bet is simple:

> Every accepted coding fix should have the chance to improve the next coding agent run.

## References

- SkillOpt: Executive Strategy for Self-Evolving Agent Skills, arXiv:2605.23904, https://arxiv.org/abs/2605.23904
- microsoft/SkillOpt, https://github.com/microsoft/SkillOpt
