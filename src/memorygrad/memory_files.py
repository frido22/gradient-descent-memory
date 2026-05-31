from __future__ import annotations

import re
from pathlib import Path


BLOCK_TITLE = "## MemoryGrad Lessons"
BLOCK_START = "<!-- memorygrad:start -->"
BLOCK_END = "<!-- memorygrad:end -->"


def append_memory_to_files(
    repo: Path,
    *,
    memory: str,
    text_gradient: str,
    proposal_id: str,
    accepted_at: str,
    accepted_proposals: list[dict[str, object]],
    target_paths: list[str],
    max_active_memory: int,
) -> None:
    append_memory_to_ledger(
        repo,
        memory=memory,
        text_gradient=text_gradient,
        proposal_id=proposal_id,
        accepted_at=accepted_at,
    )
    sync_memory_targets(
        repo,
        accepted_proposals=accepted_proposals,
        target_paths=target_paths,
        max_active_memory=max_active_memory,
    )


def append_memory_to_ledger(
    repo: Path,
    *,
    memory: str,
    text_gradient: str,
    proposal_id: str,
    accepted_at: str,
) -> None:
    path = repo / ".memorygrad" / "memory.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = path.read_text(encoding="utf-8") if path.exists() else "# MemoryGrad Memory\n"
    entry = (
        f"\n- {memory}\n"
        f"  - Gradient: {text_gradient}\n"
        f"  - Proposal: {proposal_id}\n"
        f"  - Accepted: {accepted_at}\n"
    )
    if f"  - Proposal: {proposal_id}\n" not in ledger:
        ledger = ledger.rstrip() + "\n" + entry
    path.write_text(ledger.rstrip() + "\n", encoding="utf-8")


def append_rejection_to_buffer(
    repo: Path,
    *,
    proposal_id: str,
    memory: str,
    reason: str,
    rejected_at: str,
) -> None:
    path = repo / ".memorygrad" / "rejected.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = path.read_text(encoding="utf-8") if path.exists() else "# MemoryGrad Rejected Edits\n"
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
    if not active_memory:
        return []
    written: list[Path] = []
    for target in target_paths:
        path = repo / target
        path.parent.mkdir(parents=True, exist_ok=True)
        content = path.read_text(encoding="utf-8") if path.exists() else _default_content(target)
        updated = sync_memory_block(content, active_memory)
        path.write_text(updated, encoding="utf-8")
        written.append(path)
    return written


def sync_memory_block(content: str, memories: list[str]) -> str:
    block = _format_memory_block(memories)

    if BLOCK_START not in content or BLOCK_END not in content:
        return content.rstrip() + block

    before, rest = content.split(BLOCK_END, 1)
    block_prefix = before.rsplit(BLOCK_START, 1)[0].rstrip()
    return f"{block_prefix}{block}{rest.lstrip()}"


def append_memory_to_content(content: str, memory: str) -> str:
    return sync_memory_block(content, [memory])


def _active_memory_texts(proposals: list[dict[str, object]], max_active_memory: int) -> list[str]:
    ordered = sorted(proposals, key=_proposal_sort_key, reverse=True)
    selected: list[str] = []
    seen: set[str] = set()
    for proposal in ordered:
        memory = proposal_memory(proposal)
        normalized = _normalize(memory)
        if not memory or normalized in seen:
            continue
        seen.add(normalized)
        selected.append(memory)
        if len(selected) >= max_active_memory:
            break
    return list(reversed(selected))


def proposal_memory(proposal: dict[str, object]) -> str:
    return str(proposal.get("memory") or proposal.get("skill") or "").strip()


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


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())
