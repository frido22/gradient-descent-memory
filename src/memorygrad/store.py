from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analyzer import normalize_memory
from .config import KNOWN_TARGETS, default_config, load_config, save_config


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_episode(
    *,
    repo: Path,
    task: str,
    agent: str,
    terminal_output: str,
    git: dict[str, str],
) -> dict[str, Any]:
    created_at = utc_now()
    return {
        "id": f"ep_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "created_at": created_at,
        "repo": str(repo),
        "task": task,
        "agent": agent,
        "terminal_output": terminal_output,
        "git": git,
    }


class MemoryStore:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.base = self.root / ".memorygrad"
        self.episodes_dir = self.base / "episodes"
        self.proposals_dir = self.base / "proposals"
        self.memory_path = self.base / "memory.md"
        self.legacy_memory_path = self.base / "skills.md"
        self.config_path = self.base / "config.json"

    def init(self, config: dict[str, Any] | None = None) -> None:
        self.episodes_dir.mkdir(parents=True, exist_ok=True)
        self.proposals_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_gitignore()
        if not self.config_path.exists():
            save_config(self.root, config or default_config())
        if not self.memory_path.exists():
            if self.legacy_memory_path.exists():
                content = self.legacy_memory_path.read_text(encoding="utf-8")
                self.memory_path.write_text(content.replace("MemoryGrad Skills", "MemoryGrad Memory"), encoding="utf-8")
            else:
                self.memory_path.write_text("# MemoryGrad Memory\n", encoding="utf-8")

    def load_config(self) -> dict[str, Any]:
        return load_config(self.root)

    def save_episode(self, episode: dict[str, Any]) -> Path:
        path = self.episodes_dir / f"{episode['id']}.json"
        _write_json(path, episode)
        return path

    def list_episodes(self) -> list[dict[str, Any]]:
        return _read_json_dir(self.episodes_dir)

    def save_proposal_if_new(self, proposal: dict[str, Any]) -> bool:
        path = self.proposals_dir / f"{proposal['id']}.json"
        if path.exists():
            return False
        _write_json(path, proposal)
        return True

    def save_proposal(self, proposal: dict[str, Any]) -> Path:
        path = self.proposals_dir / f"{proposal['id']}.json"
        _write_json(path, proposal)
        return path

    def list_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        proposals = _read_json_dir(self.proposals_dir)
        if status is not None:
            proposals = [proposal for proposal in proposals if proposal.get("status") == status]
        return sorted(proposals, key=lambda item: str(item.get("created_at", "")))

    def list_accepted_proposals(self) -> list[dict[str, Any]]:
        return self.list_proposals(status="accepted")

    def load_memory_texts(self) -> list[str]:
        texts: list[str] = []
        target_paths = list(KNOWN_TARGETS)
        for target in self.load_config().get("targets", []):
            if isinstance(target, str) and target not in target_paths:
                target_paths.append(target)

        memory_paths = [self.memory_path]
        if self.legacy_memory_path.exists():
            memory_paths.append(self.legacy_memory_path)

        for path in [self.root / target for target in target_paths] + memory_paths:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("- "):
                    texts.append(stripped[2:].strip())
        return list({normalize_memory(text): text for text in texts}.values())

    def _ensure_gitignore(self) -> None:
        path = self.base / ".gitignore"
        required = [
            "episodes/",
            "proposals/",
            "rejected.md",
            "!config.json",
            "!memory.md",
            "!skills.md",
            "!.gitignore",
        ]
        existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        lines = list(existing)
        for item in required:
            if item not in lines:
                lines.append(item)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _read_json_dir(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for item in sorted(path.glob("*.json")):
        try:
            loaded = json.loads(item.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(loaded, dict):
            items.append(loaded)
    return items


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
