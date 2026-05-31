from __future__ import annotations

from pathlib import Path


BLOCK_TITLE = "## MemoryGrad Lessons"
BLOCK_START = "<!-- memorygrad:start -->"
BLOCK_END = "<!-- memorygrad:end -->"


def append_skill_to_memory_files(
    repo: Path,
    *,
    skill: str,
    text_gradient: str,
    proposal_id: str,
    accepted_at: str,
) -> None:
    for filename in ("AGENTS.md", "CLAUDE.md"):
        path = repo / filename
        content = path.read_text(encoding="utf-8") if path.exists() else f"# {filename}\n"
        updated = append_skill_to_content(content, skill)
        path.write_text(updated, encoding="utf-8")

    skills_path = repo / ".memorygrad" / "skills.md"
    skills_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = skills_path.read_text(encoding="utf-8") if skills_path.exists() else "# MemoryGrad Skills\n"
    entry = (
        f"\n- {skill}\n"
        f"  - Gradient: {text_gradient}\n"
        f"  - Proposal: {proposal_id}\n"
        f"  - Accepted: {accepted_at}\n"
    )
    if f"- {skill}\n" not in ledger:
        ledger = ledger.rstrip() + "\n" + entry
    skills_path.write_text(ledger.rstrip() + "\n", encoding="utf-8")


def append_skill_to_content(content: str, skill: str) -> str:
    bullet = f"- {skill.strip()}"
    if bullet in content:
        return _ensure_trailing_newline(content)

    if BLOCK_START not in content or BLOCK_END not in content:
        block = f"\n\n{BLOCK_TITLE}\n\n{BLOCK_START}\n{bullet}\n{BLOCK_END}\n"
        return content.rstrip() + block

    before, rest = content.split(BLOCK_END, 1)
    before = before.rstrip()
    return f"{before}\n{bullet}\n{BLOCK_END}{rest}"


def _ensure_trailing_newline(content: str) -> str:
    return content if content.endswith("\n") else content + "\n"
