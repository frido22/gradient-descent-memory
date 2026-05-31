from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from .model import OPERATIONS, SCOPES, ProposalDraft, normalize_memory, proposal_id


OPTIMIZER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "edits": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "scope": {"type": "string", "enum": ["repo", "global"]},
                    "operation": {"type": "string", "enum": ["add", "replace", "delete"]},
                    "memory": {"type": "string"},
                    "target_memory": {"type": "string"},
                    "text_gradient": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
                },
                "required": ["scope", "operation", "memory", "text_gradient", "confidence", "evidence"],
            },
        }
    },
    "required": ["edits"],
}


class OptimizerError(Exception):
    """Raised when the agent optimizer cannot produce usable memory edits."""


def propose_memory_edits(
    *,
    repo: Path,
    episode: dict[str, object],
    repo_memory: list[str],
    global_memory: list[str],
    rejected_memory: list[str],
    max_edits: int,
    optimizer: str,
    optimizer_command: str,
) -> list[ProposalDraft]:
    prompt = build_optimizer_prompt(
        episode=episode,
        repo_memory=repo_memory,
        global_memory=global_memory,
        rejected_memory=rejected_memory,
        max_edits=max_edits,
    )
    raw = run_optimizer(prompt=prompt, repo=repo, optimizer=optimizer, optimizer_command=optimizer_command)
    return parse_optimizer_response(raw, max_edits=max_edits)


def build_optimizer_prompt(
    *,
    episode: dict[str, object],
    repo_memory: list[str],
    global_memory: list[str],
    rejected_memory: list[str],
    max_edits: int,
) -> str:
    payload = {
        "task": episode.get("task", ""),
        "agent": episode.get("agent", ""),
        "terminal_output": _clip(str(episode.get("terminal_output") or ""), 60_000),
        "git": {
            key: _clip(str(value), 45_000)
            for key, value in (episode.get("git") if isinstance(episode.get("git"), dict) else {}).items()
        },
    }
    return textwrap.dedent(
        f"""
        You are the MemoryGrad optimizer running inside a coding agent. Do not edit files or run commands.

        Optimize external memory text for future coding-agent runs, following the SkillOpt-style loop:
        use rollout evidence, propose bounded add/replace/delete edits, keep rejected edits in mind,
        and only propose memory that would likely improve a future run without retraining the model.

        Return JSON only. Propose at most {max_edits} edits.

        Scope rules:
        - scope="repo": repo-specific workflow facts, file paths, commands, registrations, fixtures, build/test conventions.
        - scope="global": agent-general behavior that should transfer across repositories. Use a much stricter bar.

        Operation rules:
        - operation="add": memory is a new concise bullet.
        - operation="replace": target_memory is the old bullet and memory is the replacement.
        - operation="delete": target_memory is the old bullet to remove; memory may repeat it.

        Quality gate:
        - Prefer no edits over weak edits.
        - Each memory must be specific, reusable, and action-oriented.
        - Do not save generic advice like "run tests" unless the evidence identifies the exact repo-specific test or workflow.
        - Keep each memory under 240 characters.
        - Cite concrete evidence from terminal output, diffs, commits, or validation.

        Existing repo memory:
        {_bullets(repo_memory)}

        Existing global memory:
        {_bullets(global_memory)}

        Rejected memory edits to avoid repeating:
        {_bullets(rejected_memory)}

        Episode evidence:
        {json.dumps(payload, indent=2, sort_keys=True)}
        """
    ).strip()


def run_optimizer(*, prompt: str, repo: Path, optimizer: str, optimizer_command: str) -> str:
    command = optimizer_command or os.environ.get("MEMORYGRAD_OPTIMIZER_COMMAND", "")
    if command:
        return _run_custom_command(command, prompt=prompt, repo=repo)

    selected = (os.environ.get("MEMORYGRAD_OPTIMIZER") or optimizer or "auto").strip().lower()
    if selected == "auto":
        if shutil.which("codex"):
            selected = "codex"
        elif shutil.which("claude"):
            selected = "claude"
        else:
            raise OptimizerError(
                "No optimizer agent found. Install Codex/Claude Code or set MEMORYGRAD_OPTIMIZER_COMMAND."
            )

    if selected == "codex":
        return _run_codex(prompt=prompt, repo=repo)
    if selected == "claude":
        return _run_claude(prompt=prompt, repo=repo)
    raise OptimizerError(f"Unknown optimizer {selected!r}; use auto, codex, claude, or MEMORYGRAD_OPTIMIZER_COMMAND.")


def parse_optimizer_response(raw: str, *, max_edits: int) -> list[ProposalDraft]:
    payload = _loads_json(raw)
    edits = payload.get("edits", [])
    if not isinstance(edits, list):
        raise OptimizerError("Optimizer response must contain an edits array.")

    drafts: list[ProposalDraft] = []
    seen: set[str] = set()
    for item in edits:
        if not isinstance(item, dict):
            continue
        draft = _draft_from_item(item)
        if draft is None:
            continue
        key = "|".join(
            [draft.scope, draft.operation, normalize_memory(draft.memory), normalize_memory(draft.target_memory)]
        )
        if key in seen:
            continue
        seen.add(key)
        drafts.append(draft)
        if len(drafts) >= max_edits:
            break
    return drafts


def _draft_from_item(item: dict[str, object]) -> ProposalDraft | None:
    scope = str(item.get("scope") or "repo").strip().lower()
    operation = str(item.get("operation") or "add").strip().lower()
    memory = _single_line(str(item.get("memory") or ""))
    target_memory = _single_line(str(item.get("target_memory") or ""))
    text_gradient = _single_line(str(item.get("text_gradient") or ""))
    evidence = [_single_line(str(value)) for value in item.get("evidence", []) if str(value).strip()][:5]

    if scope not in SCOPES or operation not in OPERATIONS:
        return None
    if operation in {"add", "replace"} and not memory:
        return None
    if operation in {"replace", "delete"} and not target_memory:
        return None
    if not text_gradient or not evidence:
        return None
    if len(memory) > 300 or len(target_memory) > 300:
        return None
    try:
        confidence = max(0.0, min(1.0, float(item.get("confidence"))))
    except (TypeError, ValueError):
        return None

    if operation == "delete" and not memory:
        memory = target_memory
    return ProposalDraft(
        id=proposal_id(scope, operation, memory, target_memory),
        scope=scope,
        operation=operation,
        memory=memory,
        target_memory=target_memory,
        text_gradient=text_gradient,
        confidence=confidence,
        evidence=evidence,
    )


def _run_custom_command(command: str, *, prompt: str, repo: Path) -> str:
    result = subprocess.run(
        shlex.split(command),
        input=prompt,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=repo,
        check=False,
        timeout=240,
    )
    if result.returncode != 0:
        raise OptimizerError(_command_error("optimizer command", result))
    return result.stdout


def _run_codex(*, prompt: str, repo: Path) -> str:
    codex = shutil.which("codex")
    if not codex:
        raise OptimizerError("Codex CLI is not installed or not on PATH.")

    with tempfile.TemporaryDirectory(prefix="memorygrad-codex-") as temp:
        schema_path = Path(temp) / "schema.json"
        output_path = Path(temp) / "response.json"
        schema_path.write_text(json.dumps(OPTIMIZER_SCHEMA), encoding="utf-8")
        result = subprocess.run(
            [
                codex,
                "exec",
                "-C",
                str(repo),
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ],
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=300,
        )
        if result.returncode != 0:
            raise OptimizerError(_command_error("codex optimizer", result))
        if output_path.exists():
            return output_path.read_text(encoding="utf-8")
        return result.stdout


def _run_claude(*, prompt: str, repo: Path) -> str:
    claude = shutil.which("claude")
    if not claude:
        raise OptimizerError("Claude Code CLI is not installed or not on PATH.")
    result = subprocess.run(
        [
            claude,
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(OPTIMIZER_SCHEMA),
            "--permission-mode",
            "dontAsk",
            "--tools",
            "",
        ],
        input=prompt,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=repo,
        check=False,
        timeout=300,
    )
    if result.returncode != 0:
        raise OptimizerError(_command_error("claude optimizer", result))
    return result.stdout


def _loads_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        raise OptimizerError("Optimizer returned an empty response.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise OptimizerError("Optimizer did not return JSON.") from None
        payload = json.loads(text[start : end + 1])

    if isinstance(payload, dict) and isinstance(payload.get("result"), str):
        return _loads_json(str(payload["result"]))
    if not isinstance(payload, dict):
        raise OptimizerError("Optimizer JSON must be an object.")
    return payload


def _command_error(name: str, result: subprocess.CompletedProcess[str]) -> str:
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    detail = stderr or stdout or f"exit code {result.returncode}"
    return f"{name} failed: {_clip(detail, 1200)}"


def _bullets(items: list[str]) -> str:
    if not items:
        return "- (none)"
    return "\n".join(f"- {item}" for item in items[:20])


def _clip(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def _single_line(value: str) -> str:
    return " ".join(value.split()).strip()
