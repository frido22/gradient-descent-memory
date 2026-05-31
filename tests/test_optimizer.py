from __future__ import annotations

from gradient_descent_memory.optimizer import build_optimizer_prompt, parse_optimizer_response


def test_parse_optimizer_response_validates_bounded_edits() -> None:
    response = """
    {
      "edits": [
        {
          "scope": "repo",
          "operation": "replace",
          "target_memory": "Run pytest -q.",
          "memory": "When changing API routes, run pytest tests/api -q.",
          "text_gradient": "The old memory was too generic for route work.",
          "confidence": 0.93,
          "evidence": ["tests/api failed", "route diff fixed it"]
        }
      ]
    }
    """

    drafts = parse_optimizer_response(response, max_edits=2)

    assert len(drafts) == 1
    assert drafts[0].scope == "repo"
    assert drafts[0].operation == "replace"
    assert drafts[0].target_memory == "Run pytest -q."


def test_optimizer_prompt_contains_global_and_repo_memory() -> None:
    prompt = build_optimizer_prompt(
        episode={"task": "Add /healthz", "agent": "codex", "terminal_output": "FAILED", "git": {"status": " M app/main.py"}},
        repo_memory=["Repo lesson."],
        global_memory=["Global lesson."],
        rejected_memory=["Bad lesson."],
        max_edits=2,
    )

    assert "Existing repo memory" in prompt
    assert "Repo lesson." in prompt
    assert "Existing global memory" in prompt
    assert "Global lesson." in prompt
    assert "Rejected memory edits" in prompt
