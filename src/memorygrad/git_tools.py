from __future__ import annotations

import subprocess
from pathlib import Path


def discover_repo(path: Path) -> Path:
    """Return the git root for path when possible, otherwise the resolved path."""

    resolved = path.expanduser().resolve()
    result = _run_git(resolved, ["rev-parse", "--show-toplevel"])
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return resolved


def collect_git_snapshot(repo: Path) -> dict[str, str]:
    return {
        "head": _git_text(repo, ["rev-parse", "--short", "HEAD"]),
        "branch": _git_text(repo, ["branch", "--show-current"]),
        "status": _git_text(repo, ["status", "--short"]),
        "working_tree_diff": _git_text(repo, ["diff", "--no-ext-diff", "--", "."]),
        "staged_diff": _git_text(repo, ["diff", "--cached", "--no-ext-diff", "--", "."]),
        "latest_commit": _git_text(repo, ["log", "-1", "--pretty=format:%h %s"]),
        "latest_commit_diff": _git_text(repo, ["show", "--format=", "--no-ext-diff", "HEAD", "--", "."]),
    }


def _git_text(repo: Path, args: list[str]) -> str:
    result = _run_git(repo, args)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
