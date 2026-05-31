from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from memorygrad.cli import main
from memorygrad.store import MemoryStore, global_memory_store


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


def set_optimizer(monkeypatch, tmp_path: Path, response: dict[str, object], *, require: str = "") -> Path:  # type: ignore[no-untyped-def]
    script = tmp_path / "optimizer.py"
    script.write_text(
        "from __future__ import annotations\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "prompt = sys.stdin.read()\n"
        "prompt_path = os.environ.get('MEMORYGRAD_TEST_PROMPT_PATH')\n"
        "if prompt_path:\n"
        "    open(prompt_path, 'w', encoding='utf-8').write(prompt)\n"
        "required = os.environ.get('MEMORYGRAD_TEST_REQUIRE', '')\n"
        "if required and required not in prompt:\n"
        "    print(json.dumps({'edits': []}))\n"
        "else:\n"
        "    print(os.environ['MEMORYGRAD_TEST_RESPONSE'])\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MEMORYGRAD_OPTIMIZER_COMMAND", f"{sys.executable} {script}")
    monkeypatch.setenv("MEMORYGRAD_TEST_RESPONSE", json.dumps(response))
    if require:
        monkeypatch.setenv("MEMORYGRAD_TEST_REQUIRE", require)
    return script


def route_response(*, confidence: float = 0.91, scope: str = "repo") -> dict[str, object]:
    return {
        "edits": [
            {
                "scope": scope,
                "operation": "add",
                "memory": "When adding or changing an API route, register the route/router in app/main.py and run pytest tests/api -q.",
                "text_gradient": "The agent failed because it missed the repo-specific API route registration point.",
                "confidence": confidence,
                "evidence": ["failed /healthz API test", "app.include_router was added", "tests passed"],
            }
        ]
    }


def parser_response(*, confidence: float = 0.68) -> dict[str, object]:
    return {
        "edits": [
            {
                "scope": "repo",
                "operation": "add",
                "memory": "When making changes touching memorygrad/parser.py, run pytest tests/core -q before committing.",
                "text_gradient": "The agent missed the repo-specific parser test target.",
                "confidence": confidence,
                "evidence": ["tests/core/test_parser.py failed", "parser.py changed", "tests passed"],
            }
        ]
    }


def test_watch_and_accept_all_writes_agent_memory(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    set_optimizer(monkeypatch, tmp_path, route_response())
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
    assert "register the route/router in app/main.py" in memory


def test_global_start_then_learn_initializes_repo(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    set_optimizer(monkeypatch, tmp_path, route_response())
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


def test_learn_uses_latest_commit_patch(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    prompt_path = tmp_path / "prompt.txt"
    monkeypatch.setenv("MEMORYGRAD_TEST_PROMPT_PATH", str(prompt_path))
    set_optimizer(monkeypatch, tmp_path, route_response(), require="include_router")
    target = make_route_repo(tmp_path)
    log = write_route_log(target)
    register_health_route(target)
    git(target, "add", "app/main.py")
    git(target, "commit", "-m", "Register health route")

    assert main(["learn", "Add /healthz", "--repo", str(target), "--log", str(log)]) == 0

    pending = MemoryStore(target).list_proposals(status="pending")
    assert len(pending) == 1
    assert "register the route/router in app/main.py" in str(pending[0]["memory"])
    assert "latest_commit_diff" in prompt_path.read_text(encoding="utf-8")


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


def test_global_memory_acceptance_writes_global_store_and_repo_targets(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    set_optimizer(monkeypatch, tmp_path, route_response(confidence=0.98, scope="global"))
    target = make_route_repo(tmp_path)
    log = write_route_log(target)
    register_health_route(target)

    assert main(["learn", "Add /healthz", "--repo", str(target), "--log", str(log), "--accept-all"]) == 0

    global_store = global_memory_store()
    accepted = global_store.list_accepted_proposals()
    assert len(accepted) == 1
    assert accepted[0]["scope"] == "global"
    assert "When adding or changing an API route" in global_store.memory_path.read_text(encoding="utf-8")
    assert "When adding or changing an API route" in (target / "AGENTS.md").read_text(encoding="utf-8")


def test_accept_all_skips_low_confidence_without_force(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    set_optimizer(monkeypatch, tmp_path, parser_response(confidence=0.68))
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


def test_watch_rejects_low_confidence_by_default(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    set_optimizer(monkeypatch, tmp_path, parser_response(confidence=0.68))
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
    assert "below 90% repo confidence gate" in (target / ".memorygrad" / "rejected.md").read_text(encoding="utf-8")
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


def test_sync_applies_replace_and_delete_memory_edits(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init")

    assert main(["init", "--repo", str(target), "--targets", "agents", "--max-active-memory", "8"]) == 0
    store = MemoryStore(target)
    store.save_proposal(
        {
            "id": "mg_add",
            "scope": "repo",
            "operation": "add",
            "memory": "Run pytest -q.",
            "confidence": 0.95,
            "status": "accepted",
            "created_at": "2026-01-01T00:00:00Z",
            "accepted_at": "2026-01-01T00:00:00Z",
        }
    )
    store.save_proposal(
        {
            "id": "mg_replace",
            "scope": "repo",
            "operation": "replace",
            "target_memory": "Run pytest -q.",
            "memory": "Run pytest tests/api -q for API route changes.",
            "confidence": 0.96,
            "status": "accepted",
            "created_at": "2026-01-02T00:00:00Z",
            "accepted_at": "2026-01-02T00:00:00Z",
        }
    )
    store.save_proposal(
        {
            "id": "mg_delete",
            "scope": "repo",
            "operation": "delete",
            "target_memory": "Run pytest tests/api -q for API route changes.",
            "memory": "Run pytest tests/api -q for API route changes.",
            "confidence": 0.97,
            "status": "accepted",
            "created_at": "2026-01-03T00:00:00Z",
            "accepted_at": "2026-01-03T00:00:00Z",
        }
    )

    assert main(["sync", "--repo", str(target)]) == 0

    assert not (target / "AGENTS.md").exists()
