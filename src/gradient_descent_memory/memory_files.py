from __future__ import annotations

import re
from pathlib import Path


BLOCK_TITLE = "## Gradient Descent Memory"
BLOCK_START = "<!-- gradient-descent-memory:start -->"
BLOCK_END = "<!-- gradient-descent-memory:end -->"


def append_memory_to_ledger(
    path: Path,
    *,
    memory: str,
    text_gradient: str,
    proposal_id: str,
    accepted_at: str,
    operation: str,
    target_memory: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = path.read_text(encoding="utf-8") if path.exists() else "# Gradient Descent Memory\n"
    entry = (
        f"\n- {memory}\n"
        f"  - Operation: {operation}\n"
        f"  - Target: {target_memory}\n"
        f"  - Gradient: {text_gradient}\n"
        f"  - Proposal: {proposal_id}\n"
        f"  - Accepted: {accepted_at}\n"
    )
    if f"  - Proposal: {proposal_id}\n" not in ledger:
        ledger = ledger.rstrip() + "\n" + entry
    path.write_text(ledger.rstrip() + "\n", encoding="utf-8")


def append_rejection_to_buffer(
    base: Path,
    *,
    proposal_id: str,
    memory: str,
    reason: str,
    rejected_at: str,
) -> None:
    path = base / "rejected.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = path.read_text(encoding="utf-8") if path.exists() else "# Rejected Memory Edits\n"
    if f"  - Proposal: {proposal_id}\n" in content:
        return
    entry = (
        f"\n- {memory}\n"
        f"  - Proposal: {proposal_id}\n"
        f"  - Reason: {reason}\n"
        f"  - Rejected: {rejected_at}\n"
    )
    path.write_text(content.rstrip() + "\n" + entry, encoding="utf-8")


def sync_memory_targets(
    repo: Path,
    *,
    accepted_proposals: list[dict[str, object]],
    target_paths: list[str],
    max_active_memory: int,
) -> list[Path]:
    active_memory = _active_memory_texts(accepted_proposals, max_active_memory)
    written: list[Path] = []
    for target in target_paths:
        path = repo / target
        if not active_memory and not path.exists():
            continue
        content = path.read_text(encoding="utf-8") if path.exists() else _default_content(target)
        updated = sync_memory_block(content, active_memory)
        if updated == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
        written.append(path)
    return written


def sync_memory_block(content: str, memories: list[str]) -> str:
    existing = _split_existing_block(content)
    if not memories:
        if existing is None:
            return content
        prefix, suffix = existing
        return _join_without_block(prefix, suffix)

    block = _format_memory_block(memories)
    if existing is None:
        return content.rstrip() + block

    prefix, suffix = existing
    return _join_with_block(prefix, block, suffix)


def _active_memory_texts(proposals: list[dict[str, object]], max_active_memory: int) -> list[str]:
    ordered = sorted(proposals, key=_proposal_sort_key)
    active: list[str] = []
    seen: set[str] = set()
    for proposal in ordered:
        operation = str(proposal.get("operation") or "add")
        memory = proposal_memory(proposal)
        target_memory = str(proposal.get("target_memory") or "").strip()
        normalized = _normalize(memory)
        target_normalized = _normalize(target_memory)

        if operation in {"replace", "delete"} and target_normalized:
            active = [item for item in active if _normalize(item) != target_normalized]
            seen.discard(target_normalized)
        if operation == "delete":
            continue
        if not memory or normalized in seen:
            continue
        seen.add(normalized)
        active.append(memory)
    return active[-max_active_memory:]


def proposal_memory(proposal: dict[str, object]) -> str:
    return str(proposal.get("memory") or "").strip()


def _format_memory_block(memories: list[str]) -> str:
    lines = ["", "", BLOCK_TITLE, "", BLOCK_START]
    lines.extend(f"- {memory}" for memory in memories)
    lines.append(BLOCK_END)
    lines.append("")
    return "\n".join(lines)


def _proposal_sort_key(proposal: dict[str, object]) -> str:
    return str(proposal.get("accepted_at") or proposal.get("created_at") or "")


def _default_content(target: str) -> str:
    name = Path(target).name
    if name.endswith(".md"):
        return f"# {name}\n"
    return ""


def _split_existing_block(content: str) -> tuple[str, str] | None:
    start = content.find(BLOCK_START)
    if start < 0:
        return None
    end = content.find(BLOCK_END, start)
    if end < 0:
        return None

    section_start = content.rfind(BLOCK_TITLE, 0, start)
    if section_start < 0:
        section_start = start
    section_end = end + len(BLOCK_END)
    return content[:section_start], content[section_end:]


def _join_with_block(prefix: str, block: str, suffix: str) -> str:
    updated = prefix.rstrip() + block if prefix.strip() else block.lstrip()
    if suffix.strip():
        updated = updated.rstrip() + "\n" + suffix.lstrip()
    return updated.rstrip() + "\n"


def _join_without_block(prefix: str, suffix: str) -> str:
    if prefix.strip() and suffix.strip():
        return prefix.rstrip() + "\n" + suffix.lstrip()
    if prefix.strip():
        return prefix.rstrip() + "\n"
    if suffix.strip():
        return suffix.lstrip()
    return ""


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())
