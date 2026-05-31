from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass


FAILED_TEST_RE = re.compile(r"(tests/[A-Za-z0-9_./-]+\.py(?:::[A-Za-z0-9_\[\].:-]+)*)")
DIFF_FILE_RE = re.compile(r"^diff --git a/(.*?) b/(.*?)$", re.MULTILINE)
PASS_RE = re.compile(r"(?i)(=+\s*[\d\s,]+passed\b|passed in \d|tests? passed|exit code 0)")
FAIL_RE = re.compile(
    r"(?i)(failed|error|traceback|assertionerror|modulenotfounderror|importerror|not found|404|exit code [1-9])"
)
FIX_RE = re.compile(r"(?i)(fixed|resolved|green|all tests pass|now passes)")


@dataclass(frozen=True)
class ProposalDraft:
    id: str
    text_gradient: str
    memory: str
    confidence: float
    evidence: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "text_gradient": self.text_gradient,
            "memory": self.memory,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


def analyze_episode(episode: dict[str, object], existing_memory: Iterable[str] = ()) -> list[ProposalDraft]:
    """Create proposal drafts from one episode.

    The MVP uses deterministic heuristics so review output is stable and easy to
    test. An LLM proposer can be added later without changing the review/write
    path.
    """

    terminal = str(episode.get("terminal_output") or "")
    git = episode.get("git") if isinstance(episode.get("git"), dict) else {}
    diff = "\n".join(
        str(git.get(key) or "")
        for key in ("working_tree_diff", "staged_diff", "latest_commit_diff")
        if isinstance(git, dict)
    )
    status = str(git.get("status") or "") if isinstance(git, dict) else ""

    if not terminal.strip() and not diff.strip() and not status.strip():
        return []

    existing_normalized = {normalize_memory(memory) for memory in existing_memory}
    candidates = [_route_registration_draft(terminal, diff, status), _generic_test_draft(terminal, diff, status)]
    drafts = [draft for draft in candidates if draft is not None]
    return [draft for draft in drafts if normalize_memory(draft.memory) not in existing_normalized]


def has_failure(text: str) -> bool:
    return bool(FAIL_RE.search(text))


def has_success(text: str) -> bool:
    return bool(PASS_RE.search(text))


def has_resolution_signal(text: str) -> bool:
    return has_success(text) or bool(FIX_RE.search(text))


def extract_failed_tests(text: str) -> list[str]:
    seen: set[str] = set()
    tests: list[str] = []
    for match in FAILED_TEST_RE.finditer(text):
        value = match.group(1).rstrip(":")
        if value not in seen:
            seen.add(value)
            tests.append(value)
    return tests


def extract_changed_files(status: str, diff: str) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()

    for line in status.splitlines():
        if len(line) < 3:
            continue
        path = line[3:].strip() if len(line) > 3 and line[2].isspace() else line[2:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        _append_unique(files, seen, path)

    for match in DIFF_FILE_RE.finditer(diff):
        path = match.group(2).strip()
        _append_unique(files, seen, path)

    return files


def normalize_memory(memory: str) -> str:
    return re.sub(r"\s+", " ", memory.strip().lower())


def proposal_id(memory: str) -> str:
    digest = hashlib.sha1(normalize_memory(memory).encode("utf-8")).hexdigest()
    return f"mg_{digest[:12]}"


def _route_registration_draft(terminal: str, diff: str, status: str) -> ProposalDraft | None:
    combined = "\n".join([terminal, diff, status]).lower()
    changed_files = extract_changed_files(status, diff)
    failed_tests = extract_failed_tests(terminal)

    route_signals = [
        "tests/api" in combined,
        "404" in combined,
        "not found" in combined,
        "include_router" in combined,
        "@app." in combined,
        "apirouter" in combined,
        "app/main.py" in changed_files or "app/main.py" in combined,
    ]
    main_registration_signal = "app/main.py" in changed_files or "app.include_router" in combined or "include_router" in combined
    if (
        not has_failure(terminal)
        or not has_resolution_signal(terminal)
        or not main_registration_signal
        or sum(bool(signal) for signal in route_signals) < 3
    ):
        return None

    memory = "When adding or changing an API route, register the route/router in app/main.py and run pytest tests/api -q."
    evidence = _evidence(
        terminal=terminal,
        changed_files=changed_files,
        failed_tests=failed_tests,
        fallback=["API route signals found in terminal output or git diff."],
    )
    return ProposalDraft(
        id=proposal_id(memory),
        text_gradient=(
            "The agent failed because it did not know that API routes in this repo must be "
            "registered in app/main.py before the API tests will pass."
        ),
        memory=memory,
        confidence=0.9,
        evidence=evidence,
    )


def _generic_test_draft(terminal: str, diff: str, status: str) -> ProposalDraft | None:
    if not has_failure(terminal) or not has_resolution_signal(terminal):
        return None

    changed_files = extract_changed_files(status, diff)
    failed_tests = extract_failed_tests(terminal)
    primary_file = _primary_changed_file(changed_files)
    if not primary_file or not failed_tests:
        return None

    test_target = _test_target(failed_tests)
    area = f"changes touching {primary_file}"
    memory = (
        f"When making {area}, run {test_target} before committing and inspect failures for "
        "repo-specific wiring, fixtures, or registration requirements."
    )
    return ProposalDraft(
        id=proposal_id(memory),
        text_gradient=(
            f"The agent failed because it did not know which repo-specific checks catch regressions for {area}."
        ),
        memory=memory,
        confidence=0.68,
        evidence=_evidence(
            terminal=terminal,
            changed_files=changed_files,
            failed_tests=failed_tests,
            fallback=["A failure was detected near changed files or failed tests."],
        ),
    )


def _test_target(failed_tests: list[str]) -> str:
    if not failed_tests:
        return "pytest -q"

    first = failed_tests[0]
    if first.startswith("tests/api/") or first == "tests/api.py":
        return "pytest tests/api -q"

    parts = first.split("/")
    if len(parts) >= 2:
        return f"pytest {'/'.join(parts[:2])} -q"
    return f"pytest {first} -q"


def _primary_changed_file(changed_files: list[str]) -> str | None:
    for path in changed_files:
        if _is_source_path(path):
            return path
    for path in changed_files:
        if not _is_memory_or_doc_path(path):
            return path
    return None


def _evidence(
    *,
    terminal: str,
    changed_files: list[str],
    failed_tests: list[str],
    fallback: list[str],
) -> list[str]:
    items: list[str] = []
    if failed_tests:
        items.append(f"Failed tests: {', '.join(failed_tests[:3])}")
    if changed_files:
        items.append(f"Changed files: {', '.join(changed_files[:5])}")
    if has_success(terminal):
        items.append("Resolution: terminal output contains a passing test signal.")
    if not items:
        items.extend(fallback)
    return items


def _is_source_path(path: str) -> bool:
    if _is_memory_or_doc_path(path) or path.startswith("tests/"):
        return False
    return path.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java", ".kt", ".swift"))


def _is_memory_or_doc_path(path: str) -> bool:
    return path.startswith(".memorygrad/") or path in {"AGENTS.md", "CLAUDE.md", "README.md"}


def _append_unique(items: list[str], seen: set[str], value: str) -> None:
    if value and value not in seen and value != "/dev/null":
        seen.add(value)
        items.append(value)
