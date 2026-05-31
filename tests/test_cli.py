from __future__ import annotations

import json
import subprocess
from pathlib import Path

from memorygrad.cli import main
from memorygrad.store import MemoryStore


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Test User", "-c", "user.email=test@example.com", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def make_route_repo(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init")

    (target / "app").mkdir()
    (target / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (target / "tests" / "api").mkdir(parents=True)
    (target / "tests" / "api" / "test_health.py").write_text("def test_healthz():\n    pass\n", encoding="utf-8")
    git(target, "add", ".")
    git(target, "commit", "-m", "Initial app")
    return target


def write_route_log(target: Path) -> Path:
    log = target / "session.log"
    log.write_text(
        "FAILED tests/api/test_health.py::test_healthz - assert 404 == 200\n"
        "=========================== 1 passed in 0.19s ===========================\n",
        encoding="utf-8",
    )
    return log


def register_health_route(target: Path) -> None:
    (target / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from app.routes.health import router as health_router\n"
        "app = FastAPI()\n"
        "app.include_router(health_router)\n",
        encoding="utf-8",
    )


def test_watch_and_accept_all_writes_agent_memory(tmp_path: Path) -> None:
    target = make_route_repo(tmp_path)
    log = write_route_log(target)
    register_health_route(target)

    assert main(["init", "--repo", str(target)]) == 0
    assert main(["watch", "--repo", str(target), "--task", "Add /healthz", "--terminal-log", str(log), "--once"]) == 0
    assert main(["review", "--repo", str(target), "--accept-all"]) == 0

    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    claude = (target / "CLAUDE.md").read_text(encoding="utf-8")
    memory = (target / ".memorygrad" / "memory.md").read_text(encoding="utf-8")

    assert "When adding or changing an API route" in agents
    assert "When adding or changing an API route" in claude
    assert "registered in app/main.py" in memory


def test_global_start_then_learn_initializes_repo(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MEMORYGRAD_HOME", str(tmp_path / "home"))
    assert main(["start", "--targets", "agents"]) == 0

    target = make_route_repo(tmp_path)
    log = write_route_log(target)
    register_health_route(target)

    assert main(["learn", "Add /healthz", "--repo", str(target), "--log", str(log), "--accept-all"]) == 0

    assert (target / ".memorygrad" / "config.json").exists()
    gitignore = (target / ".memorygrad" / ".gitignore").read_text(encoding="utf-8")
    assert "episodes/" in gitignore
    assert "!memory.md" in gitignore
    assert "When adding or changing an API route" in (target / "AGENTS.md").read_text(encoding="utf-8")
    assert not (target / "CLAUDE.md").exists()


def test_learn_uses_latest_commit_patch(tmp_path: Path) -> None:
    target = make_route_repo(tmp_path)
    log = write_route_log(target)
    register_health_route(target)
    git(target, "add", "app/main.py")
    git(target, "commit", "-m", "Register health route")

    assert main(["learn", "Add /healthz", "--repo", str(target), "--log", str(log)]) == 0

    pending = MemoryStore(target).list_proposals(status="pending")
    assert len(pending) == 1
    assert "register the route/router in app/main.py" in str(pending[0]["memory"])


def test_init_preserves_empty_targets_and_updates_config(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init")

    assert main(["init", "--repo", str(target), "--targets", "none"]) == 0
    config_path = target / ".memorygrad" / "config.json"
    assert json.loads(config_path.read_text(encoding="utf-8"))["targets"] == []

    assert main(["init", "--repo", str(target), "--targets", "all"]) == 0
    assert json.loads(config_path.read_text(encoding="utf-8"))["targets"] == [
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        ".github/copilot-instructions.md",
    ]


def test_learn_reports_missing_log_without_traceback(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init")

    result = main(["learn", "broken log", "--repo", str(target), "--log", str(target / "missing.log")])

    captured = capsys.readouterr()
    assert result == 2
    assert "Could not read terminal log" in captured.err
    assert "Traceback" not in captured.err


def test_accept_all_skips_low_confidence_without_force(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init")

    package = target / "memorygrad"
    package.mkdir()
    (package / "parser.py").write_text("def parse(raw):\n    return raw\n", encoding="utf-8")
    git(target, "add", ".")
    git(target, "commit", "-m", "Initial parser")

    (package / "parser.py").write_text("def parse(raw):\n    return raw.strip()\n", encoding="utf-8")
    log = target / "session.log"
    log.write_text(
        "FAILED tests/core/test_parser.py::test_parse - AssertionError\n"
        "=========================== 1 passed in 0.19s ===========================\n",
        encoding="utf-8",
    )

    assert main(["watch", "--repo", str(target), "--terminal-log", str(log), "--once", "--min-confidence", "0"]) == 0
    assert main(["review", "--repo", str(target), "--accept-all"]) == 0
    assert not (target / "AGENTS.md").exists()

    assert main(["review", "--repo", str(target), "--accept-all", "--force"]) == 0
    assert "When making changes touching memorygrad/parser.py" in (target / "AGENTS.md").read_text(encoding="utf-8")


def test_watch_rejects_low_confidence_by_default(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init")

    package = target / "memorygrad"
    package.mkdir()
    (package / "parser.py").write_text("def parse(raw):\n    return raw\n", encoding="utf-8")
    git(target, "add", ".")
    git(target, "commit", "-m", "Initial parser")

    (package / "parser.py").write_text("def parse(raw):\n    return raw.strip()\n", encoding="utf-8")
    log = target / "session.log"
    log.write_text(
        "FAILED tests/core/test_parser.py::test_parse - AssertionError\n"
        "=========================== 1 passed in 0.19s ===========================\n",
        encoding="utf-8",
    )

    assert main(["watch", "--repo", str(target), "--terminal-log", str(log), "--once"]) == 0

    store = MemoryStore(target)
    assert store.list_proposals(status="pending") == []
    rejected = store.list_proposals(status="rejected_low_confidence")
    assert len(rejected) == 1
    assert "below 90% confidence gate" in (target / ".memorygrad" / "rejected.md").read_text(encoding="utf-8")
    assert not (target / "AGENTS.md").exists()


def test_status_on_empty_repo(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "target"
    target.mkdir()

    assert main(["status", "--repo", str(target)]) == 0
    captured = capsys.readouterr()
    assert "Episodes: 0" in captured.out
    assert "Proposals: 0" in captured.out
    assert not (target / ".memorygrad").exists()


def test_sync_respects_targets_and_active_cap(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init")

    assert main(["init", "--repo", str(target), "--targets", "agents", "--max-active-memory", "1"]) == 0

    store = MemoryStore(target)
    store.save_proposal(
        {
            "id": "mg_first",
            "memory": "First accepted rule.",
            "text_gradient": "First gradient.",
            "confidence": 0.95,
            "status": "accepted",
            "created_at": "2026-01-01T00:00:00Z",
            "accepted_at": "2026-01-01T00:00:00Z",
        }
    )
    store.save_proposal(
        {
            "id": "mg_second",
            "memory": "Second accepted rule.",
            "text_gradient": "Second gradient.",
            "confidence": 0.96,
            "status": "accepted",
            "created_at": "2026-01-02T00:00:00Z",
            "accepted_at": "2026-01-02T00:00:00Z",
        }
    )

    assert main(["sync", "--repo", str(target)]) == 0

    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert "Second accepted rule." in agents
    assert "First accepted rule." not in agents
    assert not (target / "CLAUDE.md").exists()
