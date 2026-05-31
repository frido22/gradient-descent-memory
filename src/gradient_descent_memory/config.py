from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CONFIG_VERSION = 1
DEFAULT_MIN_CONFIDENCE = 0.90
DEFAULT_GLOBAL_MIN_CONFIDENCE = 0.97
DEFAULT_MAX_ACTIVE_MEMORY = 8
DEFAULT_MAX_EDITS_PER_EPISODE = 2
DEFAULT_OPTIMIZER = "auto"

AGENT_TARGETS = {
    "agents": "AGENTS.md",
    "codex": "AGENTS.md",
    "claude": "CLAUDE.md",
    "gemini": "GEMINI.md",
    "copilot": ".github/copilot-instructions.md",
}
CORE_TARGETS = ["AGENTS.md", "CLAUDE.md"]
KNOWN_TARGETS = ["AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md"]


def default_config(*, targets: list[str] | None = None) -> dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "min_confidence": DEFAULT_MIN_CONFIDENCE,
        "global_min_confidence": DEFAULT_GLOBAL_MIN_CONFIDENCE,
        "max_active_memory": DEFAULT_MAX_ACTIVE_MEMORY,
        "max_edits_per_episode": DEFAULT_MAX_EDITS_PER_EPISODE,
        "optimizer": DEFAULT_OPTIMIZER,
        "optimizer_command": "",
        "targets": list(CORE_TARGETS if targets is None else targets),
    }


def load_config(repo: Path) -> dict[str, Any]:
    path = _config_path(repo)
    config = default_config()
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            config.update({key: value for key, value in loaded.items() if value is not None})
    return _normalize_config(config)


def load_global_config() -> dict[str, Any]:
    path = global_config_path()
    config = default_config(targets=["AGENTS.md"])
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            config.update({key: value for key, value in loaded.items() if value is not None})
    return _normalize_config(config)


def save_config(repo: Path, config: dict[str, Any]) -> None:
    path = _config_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_normalize_config(config), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def save_global_config(config: dict[str, Any]) -> Path:
    path = global_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_normalize_config(config), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def global_config_path() -> Path:
    root = os.environ.get("GRADIENT_DESCENT_MEMORY_HOME")
    if root:
        return Path(root).expanduser() / "config.json"
    return Path.home() / ".gradient-descent-memory" / "config.json"


def global_home() -> Path:
    return global_config_path().parent


def resolve_targets(repo: Path, value: str | list[str] | None) -> list[str]:
    if value is None:
        return list(CORE_TARGETS)
    if isinstance(value, list):
        tokens = value
    else:
        raw = value.strip()
        if raw == "":
            return list(CORE_TARGETS)
        if raw == "core":
            return list(CORE_TARGETS)
        if raw == "all":
            return list(KNOWN_TARGETS)
        if raw == "auto":
            existing = [target for target in KNOWN_TARGETS if (repo / target).exists()]
            return existing or ["AGENTS.md"]
        if raw == "none":
            return []
        tokens = [item.strip() for item in raw.split(",")]

    targets: list[str] = []
    for token in tokens:
        if not token:
            continue
        targets.append(AGENT_TARGETS.get(token, token))
    return _dedupe(targets)


def _normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = default_config()
    normalized.update(config)
    normalized["version"] = CONFIG_VERSION
    normalized["min_confidence"] = _clamp_float(normalized.get("min_confidence"), DEFAULT_MIN_CONFIDENCE)
    normalized["global_min_confidence"] = _clamp_float(
        normalized.get("global_min_confidence"), DEFAULT_GLOBAL_MIN_CONFIDENCE
    )
    normalized["max_active_memory"] = _positive_int(normalized.get("max_active_memory"), DEFAULT_MAX_ACTIVE_MEMORY)
    normalized["max_edits_per_episode"] = _positive_int(
        normalized.get("max_edits_per_episode"), DEFAULT_MAX_EDITS_PER_EPISODE
    )
    normalized["optimizer"] = str(normalized.get("optimizer") or DEFAULT_OPTIMIZER)
    normalized["optimizer_command"] = str(normalized.get("optimizer_command") or "")
    targets = normalized.get("targets")
    normalized["targets"] = _dedupe(targets if isinstance(targets, list) else CORE_TARGETS)
    return normalized


def _config_path(repo: Path) -> Path:
    return repo / ".gradient-descent-memory" / "config.json"


def _clamp_float(value: object, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(1.0, parsed))


def _positive_int(value: object, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(1, parsed)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
