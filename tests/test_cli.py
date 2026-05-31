from __future__ import annotations

import subprocess
from pathlib import Path

from memorygrad.cli import main


def test_watch_and_accept_all_writes_agent_memory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    subprocess.run(["git", "init"], cwd=target, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    (target / "app").mkdir()
    (target / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (target / "tests").mkdir()
    (target / "tests" / "api").mkdir()
    log = target / "session.log"
    log.write_text(
        "FAILED tests/api/test_health.py::test_healthz - assert 404 == 200\n"
        "=========================== 1 passed in 0.19s ===========================\n",
        encoding="utf-8",
    )

    (target / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from app.routes.health import router as health_router\n"
        "app = FastAPI()\n"
        "app.include_router(health_router)\n",
        encoding="utf-8",
    )

    assert main(["init", "--repo", str(target)]) == 0
    assert main(["watch", "--repo", str(target), "--task", "Add /healthz", "--terminal-log", str(log), "--once"]) == 0
    assert main(["review", "--repo", str(target), "--accept-all"]) == 0

    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    claude = (target / "CLAUDE.md").read_text(encoding="utf-8")
    skills = (target / ".memorygrad" / "skills.md").read_text(encoding="utf-8")

    assert "When adding or changing an API route" in agents
    assert "When adding or changing an API route" in claude
    assert "registered in app/main.py" in skills


def test_status_on_empty_repo(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "target"
    target.mkdir()

    assert main(["status", "--repo", str(target)]) == 0
    captured = capsys.readouterr()
    assert "Episodes: 0" in captured.out
    assert "Proposals: 0" in captured.out
