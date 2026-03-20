from __future__ import annotations

from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from planagent.config import Settings
from planagent.domain.api import OpenAIStatusResponse, OpenAITestResponse


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def resolve_openclaw_model_selector(selector: str) -> str:
    normalized = selector.strip()
    for prefix in ("openai/", "openai-codex/"):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :]
    return normalized


class ExtractedClaimPayload(BaseModel):
    statement: str
    confidence: float = Field(ge=0.0, le=1.0)
    kind: Literal["signal", "event", "trend", "unclassified"] = "unclassified"
    rationale: str


class EvidenceExtractionPayload(BaseModel):
    summary: str
    claims: list[ExtractedClaimPayload] = Field(default_factory=list)


class ReportNarrativePayload(BaseModel):
    executive_summary: str
    strategy_recommendations: list[str] = Field(default_factory=list)
    why_this_happened: str


class OpenAIService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.last_error: str | None = None
        self.client: AsyncOpenAI | None = None
        if settings.openai_enabled:
            self.client = AsyncOpenAI(
                api_key=settings.resolved_openai_api_key,
                base_url=settings.openai_base_url or None,
                timeout=settings.openai_timeout_seconds,
            )

    @property
    def enabled(self) -> bool:
        return self.client is not None

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()

    def status(self) -> OpenAIStatusResponse:
        return OpenAIStatusResponse(
            configured=self.enabled,
            primary_model=self.settings.openai_primary_model,
            resolved_primary_model=resolve_openclaw_model_selector(self.settings.openai_primary_model),
            extraction_model=self.settings.resolved_openai_extraction_model,
            report_model=self.settings.resolved_openai_report_model,
            resolved_extraction_model=resolve_openclaw_model_selector(
                self.settings.resolved_openai_extraction_model
            ),
            resolved_report_model=resolve_openclaw_model_selector(
                self.settings.resolved_openai_report_model
            ),
            base_url=self.settings.openai_base_url,
            last_error=self.last_error,
        )

    async def extract_evidence(
        self,
        title: str,
        body_text: str,
    ) -> EvidenceExtractionPayload | None:
        if self.client is None:
            return None

        prompt = (
            "Extract a concise evidence summary and up to 5 factual claims from the source below. "
            "Each claim must be grounded in the supplied text only. "
            "Classify each claim as signal, event, trend, or unclassified.\n\n"
            f"Title: {_normalize_text(title)}\n\n"
            f"Body:\n{_normalize_text(body_text)[:5000]}"
        )
        try:
            response = await self.client.responses.parse(
                model=resolve_openclaw_model_selector(self.settings.resolved_openai_extraction_model),
                instructions=(
                    "You are a precise evidence extraction system for an analyst workflow. "
                    "Only return grounded claims. Keep summaries compact and factual."
                ),
                input=prompt,
                text_format=EvidenceExtractionPayload,
                max_output_tokens=1200,
                verbosity="low",
            )
            self.last_error = None
            return response.output_parsed
        except Exception as exc:
            self.last_error = f"evidence_extraction_failed: {exc}"
            return None

    async def enhance_company_report(
        self,
        company_name: str,
        evidence_statements: list[str],
        actions: list[str],
        leading_indicators: list[dict[str, float]],
        matched_rules: list[str],
    ) -> ReportNarrativePayload | None:
        if self.client is None:
            return None

        prompt = (
            f"Company: {company_name}\n"
            f"Evidence statements: {evidence_statements[:5]}\n"
            f"Actions taken: {actions[:10]}\n"
            f"Leading indicators: {leading_indicators}\n"
            f"Matched rules: {matched_rules[:10]}\n"
            "Return a concise executive summary, a short explanation of why the result happened, "
            "and up to 4 practical recommendations."
        )
        try:
            response = await self.client.responses.parse(
                model=resolve_openclaw_model_selector(self.settings.resolved_openai_report_model),
                instructions=(
                    "You write evidence-grounded operational summaries. "
                    "Do not invent data that is not present in the prompt."
                ),
                input=prompt,
                text_format=ReportNarrativePayload,
                max_output_tokens=900,
                verbosity="low",
            )
            self.last_error = None
            return response.output_parsed
        except Exception as exc:
            self.last_error = f"report_enhancement_failed: {exc}"
            return None

    async def test_connection(
        self,
        model: str | None = None,
        prompt: str = "Reply with exactly: OK",
        max_output_tokens: int = 32,
    ) -> OpenAITestResponse:
        selected_model = model or self.settings.openai_primary_model
        resolved_model = resolve_openclaw_model_selector(selected_model)

        if self.client is None:
            return OpenAITestResponse(
                ok=False,
                configured=False,
                model=selected_model,
                resolved_model=resolved_model,
                last_error="OpenAI API key is not configured.",
            )

        try:
            response = await self.client.responses.create(
                model=resolved_model,
                input=prompt,
                max_output_tokens=max_output_tokens,
            )
            self.last_error = None
            output_text = getattr(response, "output_text", None)
            return OpenAITestResponse(
                ok=True,
                configured=True,
                model=selected_model,
                resolved_model=resolved_model,
                response_id=response.id,
                output_text=output_text,
            )
        except Exception as exc:
            self.last_error = f"connectivity_test_failed: {exc}"
            return OpenAITestResponse(
                ok=False,
                configured=True,
                model=selected_model,
                resolved_model=resolved_model,
                last_error=self.last_error,
            )
