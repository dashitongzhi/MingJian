from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from planagent.services import export as export_module


REPO_ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/tracker.png",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "ftp://127.0.0.1/private",
    ],
)
def test_pdf_export_rejects_external_resource_fetches(url: str) -> None:
    with pytest.raises(ValueError, match="external resources are disabled"):
        export_module.safe_pdf_url_fetcher(url)


def test_pdf_export_rejects_non_image_and_oversized_data_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="image data"):
        export_module.safe_pdf_url_fetcher("data:text/html,<h1>not-an-image</h1>")

    monkeypatch.setattr(export_module, "MAX_PDF_DATA_URI_BYTES", 4)
    with pytest.raises(ValueError, match="size limit"):
        export_module.safe_pdf_url_fetcher("data:image/png;base64,QUJDREU=")


def test_pdf_export_escapes_title_and_uses_restricted_fetcher(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {}

    class FakeHTML:
        def __init__(self, *, string: str, url_fetcher) -> None:
            captured["html"] = string
            captured["url_fetcher"] = url_fetcher

        def write_pdf(self, *, presentational_hints: bool) -> bytes:
            captured["presentational_hints"] = presentational_hints
            return b"%PDF-safe"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))

    service = export_module.ExportService(output_dir=tmp_path)
    result = service.md_to_pdf(
        "# Report\n\nSafe content",
        title='</title><img src="http://169.254.169.254/">',
    )

    assert result == b"%PDF-safe"
    url_fetcher = captured["url_fetcher"]
    assert callable(url_fetcher)
    assert captured["presentational_hints"] is False
    with pytest.raises(ValueError, match="external resources are disabled"):
        url_fetcher("http://169.254.169.254/latest/meta-data/")
    rendered = str(captured["html"])
    assert '<img src="http://169.254.169.254/">' not in rendered
    assert "&lt;/title&gt;&lt;img" in rendered


def test_pdf_export_rejects_oversized_markdown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    service = export_module.ExportService(output_dir=tmp_path)
    monkeypatch.setattr(export_module, "MAX_PDF_MARKDOWN_CHARS", 4)
    with pytest.raises(ValueError, match="Markdown exceeds the size limit"):
        service.md_to_pdf("12345")


def test_pdf_export_rejects_more_than_sixteen_normalized_inline_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "weasyprint",
        SimpleNamespace(HTML=lambda **_: pytest.fail("renderer should not be called")),
    )
    markdown = "\n".join('<img src="data&#58;image/png;base64,QQ==">' for _ in range(17))
    service = export_module.ExportService(output_dir=tmp_path)

    with pytest.raises(ValueError, match="too many inline resources"):
        service.md_to_pdf(markdown)


def test_pdf_export_does_not_count_data_scheme_in_report_prose(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    class FakeHTML:
        def __init__(self, **_kwargs) -> None:
            pass

        def write_pdf(self, *, presentational_hints: bool) -> bytes:
            assert presentational_hints is False
            return b"%PDF-prose"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))
    service = export_module.ExportService(output_dir=tmp_path)

    prose = "\n".join(f"The `data:` scheme is discussed in paragraph {i}." for i in range(17))
    assert service.md_to_pdf(prose) == b"%PDF-prose"


@pytest.mark.parametrize(
    "css",
    [
        r'background-image:url("d\61 ta:image/png;base64,QQ==")',
        'background-image:u/**/rl("data:image/png;base64,QQ==")',
        r'background-image:u\72 l("data:image/png;base64,QQ==")',
        'background-image:u\\\nrl("data:image/png;base64,QQ==")',
    ],
)
def test_pdf_export_rejects_css_resource_escape_normalization(
    css: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "weasyprint",
        SimpleNamespace(HTML=lambda **_: pytest.fail("renderer should not be called")),
    )
    service = export_module.ExportService(output_dir=tmp_path)
    markdown = f"# Report\n\n<span style='{css}'>x</span>"

    with pytest.raises(ValueError, match="CSS resource syntax is disabled"):
        service.md_to_pdf(markdown)


def test_pdf_export_limits_resources_after_html_normalization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(export_module, "MAX_PDF_INLINE_RESOURCES", 1)
    monkeypatch.setattr(export_module, "safe_pdf_url_fetcher", lambda *_args, **_kwargs: {})

    class FakeHTML:
        def __init__(self, *, string: str, url_fetcher) -> None:
            self.url_fetcher = url_fetcher

        def write_pdf(self, *, presentational_hints: bool) -> bytes:
            assert presentational_hints is False
            self.url_fetcher("data:image/png;base64,QQ==")
            self.url_fetcher("data:image/png;base64,Qg==")
            return b"renderer should not reach this point"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))
    service = export_module.ExportService(output_dir=tmp_path)

    with pytest.raises(ValueError, match="too many inline resources"):
        service.md_to_pdf('<img src="data&#58;image/png;base64,QQ==">')


def test_pr_auto_review_does_not_interpolate_untrusted_step_outputs() -> None:
    workflow = (REPO_ROOT / ".github/workflows/pr-auto-review.yml").read_text(encoding="utf-8")

    assert "${{ steps.pr-info.outputs" not in workflow
    assert "actions: write" not in workflow


def test_codex_review_preserves_retry_artifacts_and_failure_comment() -> None:
    workflow = (REPO_ROOT / ".github/workflows/codex-pr-review.yml").read_text(encoding="utf-8")

    assert "continue-on-error: true" in workflow
    assert re.search(r"uses: actions/upload-artifact@[0-9a-f]{40} # v4", workflow)
    assert "if: always()" in workflow
    assert "Codex review is temporarily unavailable" in workflow
    assert "Retry this workflow or continue the review locally" in workflow
    assert "id: publish" in workflow
    assert 'core.setOutput("review_succeeded"' in workflow
    assert "if: steps.publish.outputs.review_succeeded != 'true'" in workflow


def test_external_workflow_actions_are_pinned_to_full_commit_shas() -> None:
    uses_pattern = re.compile(r"^\s*uses:\s+([^@\s]+)@([^\s#]+)", re.MULTILINE)

    for workflow_path in sorted((REPO_ROOT / ".github/workflows").glob("*.yml")):
        workflow = workflow_path.read_text(encoding="utf-8")
        for action, ref in uses_pattern.findall(workflow):
            assert re.fullmatch(r"[0-9a-f]{40}", ref), (
                f"{workflow_path.name}: {action} must be pinned to a full commit SHA"
            )


def test_codex_pull_request_target_isolates_untrusted_review_input() -> None:
    workflow = (REPO_ROOT / ".github/workflows/codex-pr-review.yml").read_text(encoding="utf-8")

    assert "pull_request_target:" in workflow
    assert "actions/checkout@" not in workflow
    assert 'allow-users: "*"' not in workflow
    assert 'permission-profile: ":read-only"' in workflow
    assert "safety-strategy: drop-sudo" in workflow
    assert "permissions: {}" in workflow
    assert "pull-requests: read" in workflow
    assert "pull-requests: write" in workflow


def test_ci_does_not_ignore_frontend_lint_failures() -> None:
    workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "npm run lint || true" not in workflow


def test_default_install_declares_pdf_runtime_dependency() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert any(dependency.startswith("weasyprint") for dependency in project["dependencies"])
    assert '".[all]"' not in dockerfile
