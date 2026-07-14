from __future__ import annotations

from pathlib import Path


def test_backend_ci_covers_community_boundary_and_session_contracts() -> None:
    """The default backend CI job must exercise Community edition and session behavior."""
    workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    required_test_files = {
        "tests/test_community_access.py",
        "tests/test_community_feature_boundaries.py",
        "tests/test_strategic_assistant.py",
        "tests/test_new_features.py",
    }

    assert required_test_files.issubset(set(workflow.split()))


def test_frontend_ci_runs_tests() -> None:
    """The frontend job must exercise the browser-facing authentication and route contracts."""
    workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "run: npm test" in workflow
