from __future__ import annotations

from pathlib import Path


def test_backend_ci_runs_the_complete_backend_suite() -> None:
    """The default backend CI job must exercise every collected backend test."""
    workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "run: python -m pytest -q" in workflow


def test_frontend_ci_runs_tests() -> None:
    """The frontend job must exercise the browser-facing authentication and route contracts."""
    workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "run: npm test" in workflow
