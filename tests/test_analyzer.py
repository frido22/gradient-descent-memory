from __future__ import annotations

from memorygrad.analyzer import analyze_episode, extract_changed_files, extract_failed_tests


def test_route_registration_proposal_from_api_failure_and_diff() -> None:
    episode = {
        "terminal_output": """
FAILED tests/api/test_health.py::test_healthz - assert 404 == 200
=========================== 1 failed in 0.23s ===========================
=========================== 1 passed in 0.19s ===========================
""",
        "git": {
            "status": " M app/main.py\n M app/routes/health.py\n M tests/api/test_health.py",
            "working_tree_diff": """
diff --git a/app/main.py b/app/main.py
+from app.routes.health import router as health_router
+app.include_router(health_router)
diff --git a/app/routes/health.py b/app/routes/health.py
+@router.get("/healthz")
""",
        },
    }

    proposals = analyze_episode(episode)

    assert proposals
    assert proposals[0].id.startswith("mg_")
    assert "registered in app/main.py" in proposals[0].text_gradient
    assert "pytest tests/api -q" in proposals[0].skill


def test_generic_test_proposal_uses_failed_test_target() -> None:
    episode = {
        "terminal_output": "FAILED tests/core/test_parser.py::test_parse - AssertionError",
        "git": {
            "status": " M memorygrad/parser.py",
            "working_tree_diff": "diff --git a/memorygrad/parser.py b/memorygrad/parser.py\n+value = parse(raw)",
        },
    }

    proposals = analyze_episode(episode)

    assert proposals
    assert "memorygrad/parser.py" in proposals[0].skill
    assert "pytest tests/core -q" in proposals[0].skill


def test_existing_skills_are_deduplicated() -> None:
    episode = {
        "terminal_output": "FAILED tests/core/test_parser.py::test_parse - AssertionError",
        "git": {"status": " M memorygrad/parser.py", "working_tree_diff": ""},
    }
    first = analyze_episode(episode)

    duplicate = analyze_episode(episode, existing_skills=[first[0].skill])

    assert duplicate == []


def test_extract_helpers() -> None:
    assert extract_failed_tests("FAILED tests/api/test_health.py::test_healthz") == [
        "tests/api/test_health.py::test_healthz"
    ]
    assert extract_changed_files(" M app/main.py", "diff --git a/a.py b/b.py") == ["app/main.py", "b.py"]
