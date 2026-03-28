from __future__ import annotations

import json
import re
from typing import Literal

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from planagent.config import Settings
from planagent.domain.api import OpenAIStatusResponse, OpenAITestResponse

TargetRole = Literal["primary", "extraction", "x_search", "report"]
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def resolve_openclaw_model_selector(selector: str) -> str:
    normalized = selector.strip().lower().replace(" ", "-")
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


class AnalysisNarrativePayload(BaseModel):
    summary: str
    findings: list[str] = Field(default_factory=list)
    reasoning_steps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class XSearchPostPayload(BaseModel):
    title: str
    url: str
    summary: str
    published_at: str | None = None


class XSearchResultPayload(BaseModel):
    posts: list[XSearchPostPayload] = Field(default_factory=list)


class OpenAIService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.last_error: str | None = None
        self.clients: dict[TargetRole, AsyncOpenAI | None] = {
            "primary": self._build_client(
                settings.resolved_openai_primary_api_key,
                settings.resolved_openai_primary_base_url,
            ),
            "extraction": self._build_client(
                settings.resolved_openai_extraction_api_key,
                settings.resolved_openai_extraction_base_url,
            ),
            "x_search": self._build_client(
                settings.resolved_openai_x_search_api_key,
                settings.resolved_openai_x_search_base_url,
            ),
            "report": self._build_client(
                settings.resolved_openai_report_api_key,
                settings.resolved_openai_report_base_url,
            ),
        }

    def _build_client(self, api_key: str | None, base_url: str | None) -> AsyncOpenAI | None:
        if not api_key:
            return None
        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=self.settings.openai_timeout_seconds,
        )

    @property
    def enabled(self) -> bool:
        return self.clients["primary"] is not None

    def is_configured(self, target: TargetRole) -> bool:
        return self.clients[target] is not None

    async def close(self) -> None:
        seen: set[int] = set()
        for client in self.clients.values():
            if client is None:
                continue
            identity = id(client)
            if identity in seen:
                continue
            seen.add(identity)
            await client.close()

    def status(self) -> OpenAIStatusResponse:
        return OpenAIStatusResponse(
            configured=self.enabled,
            primary_configured=self.clients["primary"] is not None,
            extraction_configured=self.clients["extraction"] is not None,
            x_search_configured=self.clients["x_search"] is not None,
            report_configured=self.clients["report"] is not None,
            primary_model=self.settings.openai_primary_model,
            resolved_primary_model=resolve_openclaw_model_selector(self.settings.openai_primary_model),
            extraction_model=self.settings.resolved_openai_extraction_model,
            x_search_model=self.settings.resolved_openai_x_search_model,
            report_model=self.settings.resolved_openai_report_model,
            primary_base_url=self.settings.resolved_openai_primary_base_url,
            extraction_base_url=self.settings.resolved_openai_extraction_base_url,
            x_search_base_url=self.settings.resolved_openai_x_search_base_url,
            report_base_url=self.settings.resolved_openai_report_base_url,
            resolved_extraction_model=resolve_openclaw_model_selector(
                self.settings.resolved_openai_extraction_model
            ),
            resolved_x_search_model=resolve_openclaw_model_selector(
                self.settings.resolved_openai_x_search_model
            ),
            resolved_report_model=resolve_openclaw_model_selector(
                self.settings.resolved_openai_report_model
            ),
            base_url=self.settings.resolved_openai_primary_base_url,
            last_error=self.last_error,
        )

    async def extract_evidence(
        self,
        title: str,
        body_text: str,
        target: TargetRole = "extraction",
    ) -> EvidenceExtractionPayload | None:
        prompt = (
            "Extract a concise evidence summary and up to 5 factual claims from the source below. "
            "Each claim must be grounded in the supplied text only. "
            "Classify each claim as signal, event, trend, or unclassified.\n\n"
            f"Title: {_normalize_text(title)}\n\n"
            f"Body:\n{_normalize_text(body_text)[:5000]}"
        )
        return await self._parse_structured_output(
            target=target,
            schema=EvidenceExtractionPayload,
            instructions=(
                "You are a precise evidence extraction system for an analyst workflow. "
                "Only return grounded claims. Keep summaries compact and factual."
            ),
            prompt=prompt,
            max_output_tokens=1200,
            error_prefix="evidence_extraction_failed",
        )

    async def enhance_company_report(
        self,
        company_name: str,
        evidence_statements: list[str],
        actions: list[str],
        leading_indicators: list[dict[str, float]],
        matched_rules: list[str],
    ) -> ReportNarrativePayload | None:
        prompt = (
            f"Company: {company_name}\n"
            f"Evidence statements: {evidence_statements[:5]}\n"
            f"Actions taken: {actions[:10]}\n"
            f"Leading indicators: {leading_indicators}\n"
            f"Matched rules: {matched_rules[:10]}\n"
            "Return a concise executive summary, a short explanation of why the result happened, "
            "and up to 4 practical recommendations."
        )
        return await self._parse_structured_output(
            target="report",
            schema=ReportNarrativePayload,
            instructions=(
                "You write evidence-grounded operational summaries. "
                "Do not invent data that is not present in the prompt."
            ),
            prompt=prompt,
            max_output_tokens=900,
            error_prefix="report_enhancement_failed",
        )

    async def test_connection(
        self,
        target: TargetRole = "primary",
        model: str | None = None,
        prompt: str = "Reply with exactly: OK",
        max_output_tokens: int = 32,
    ) -> OpenAITestResponse:
        selected_model = model or self._model_for_target(target)
        resolved_model = resolve_openclaw_model_selector(selected_model)
        client = self.clients[target]
        base_url = self._base_url_for_target(target)

        if client is None:
            return OpenAITestResponse(
                ok=False,
                configured=False,
                target=target,
                model=selected_model,
                resolved_model=resolved_model,
                base_url=base_url,
                last_error=f"{target} API key is not configured.",
            )

        try:
            response = await client.responses.create(
                model=resolved_model,
                input=prompt,
                max_output_tokens=max_output_tokens,
            )
            self.last_error = None
            output_text = getattr(response, "output_text", None)
            return OpenAITestResponse(
                ok=True,
                configured=True,
                target=target,
                model=selected_model,
                resolved_model=resolved_model,
                base_url=base_url,
                api_mode="responses",
                response_id=response.id,
                output_text=output_text,
            )
        except Exception as responses_exc:
            try:
                chat_response = await client.chat.completions.create(
                    model=resolved_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_output_tokens,
                )
                self.last_error = None
                output_text = self._extract_chat_text(chat_response)
                return OpenAITestResponse(
                    ok=True,
                    configured=True,
                    target=target,
                    model=selected_model,
                    resolved_model=resolved_model,
                    base_url=base_url,
                    api_mode="chat.completions",
                    response_id=getattr(chat_response, "id", None),
                    output_text=output_text,
                )
            except Exception as chat_exc:
                try:
                    response_id, output_text = await self._create_chat_completion_raw(
                        target=target,
                        model=resolved_model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_output_tokens,
                    )
                    self.last_error = None
                    return OpenAITestResponse(
                        ok=True,
                        configured=True,
                        target=target,
                        model=selected_model,
                        resolved_model=resolved_model,
                        base_url=base_url,
                        api_mode="chat.completions.raw",
                        response_id=response_id,
                        output_text=output_text,
                    )
                except Exception as raw_exc:
                    self.last_error = (
                        "connectivity_test_failed: "
                        f"responses={responses_exc}; chat.completions={chat_exc}; raw={raw_exc}"
                    )
                    return OpenAITestResponse(
                        ok=False,
                        configured=True,
                        target=target,
                        model=selected_model,
                        resolved_model=resolved_model,
                        base_url=base_url,
                        last_error=self.last_error,
                    )

    async def _parse_structured_output(
        self,
        target: TargetRole,
        schema: type[BaseModel],
        instructions: str,
        prompt: str,
        max_output_tokens: int,
        error_prefix: str,
    ) -> BaseModel | None:
        client = self.clients[target]
        if client is None:
            return None

        model = resolve_openclaw_model_selector(self._model_for_target(target))
        try:
            response = await client.responses.parse(
                model=model,
                instructions=instructions,
                input=prompt,
                text_format=schema,
                max_output_tokens=max_output_tokens,
                verbosity="low",
            )
            self.last_error = None
            return response.output_parsed
        except Exception as responses_exc:
            try:
                chat_response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": instructions},
                        {
                            "role": "user",
                            "content": (
                                f"{prompt}\n\n"
                                "Return valid JSON only. "
                                f"Target schema: {json.dumps(schema.model_json_schema(), ensure_ascii=True)}"
                            ),
                        },
                    ],
                    max_tokens=max_output_tokens,
                    response_format={"type": "json_object"},
                )
                raw_text = self._extract_chat_text(chat_response)
                self.last_error = None
                return schema.model_validate_json(raw_text)
            except Exception as chat_json_exc:
                try:
                    chat_response = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": instructions},
                            {
                                "role": "user",
                                "content": (
                                    f"{prompt}\n\n"
                                    "Return JSON only with keys required by this schema: "
                                    f"{json.dumps(schema.model_json_schema(), ensure_ascii=True)}"
                                ),
                            },
                        ],
                        max_tokens=max_output_tokens,
                    )
                    raw_text = self._extract_chat_text(chat_response)
                    self.last_error = None
                    return schema.model_validate_json(self._extract_json_payload(raw_text))
                except Exception as chat_exc:
                    try:
                        _, raw_text = await self._create_chat_completion_raw(
                            target=target,
                            model=model,
                            messages=[
                                {"role": "system", "content": instructions},
                                {
                                    "role": "user",
                                    "content": (
                                        f"{prompt}\n\n"
                                        "Return JSON only with keys required by this schema: "
                                        f"{json.dumps(schema.model_json_schema(), ensure_ascii=True)}"
                                    ),
                                },
                            ],
                            max_tokens=max_output_tokens,
                            response_format={"type": "json_object"},
                        )
                        self.last_error = None
                        return schema.model_validate_json(self._extract_json_payload(raw_text))
                    except Exception as raw_exc:
                        self.last_error = (
                            f"{error_prefix}: responses={responses_exc}; "
                            f"chat.json={chat_json_exc}; chat.completions={chat_exc}; raw={raw_exc}"
                        )
                        return None

    async def analyze_topic(
        self,
        content: str,
        domain_id: str,
        related_sources: list[dict[str, str]],
    ) -> AnalysisNarrativePayload | None:
        prompt = (
            f"Domain: {domain_id}\n"
            f"User input:\n{_normalize_text(content)[:3000]}\n\n"
            f"Related public sources:\n{json.dumps(related_sources[:8], ensure_ascii=False)}\n\n"
            "Return a concise analysis summary, up to 5 findings, a short reasoning trace with up to 5 steps, "
            "and up to 4 practical recommendations. Keep everything grounded in the provided sources."
        )
        return await self._parse_structured_output(
            target="primary",
            schema=AnalysisNarrativePayload,
            instructions=(
                "You are an evidence-grounded analyst. "
                "Do not reveal hidden chain-of-thought. "
                "Return concise reasoning steps that summarize why the conclusion follows from the evidence."
            ),
            prompt=prompt,
            max_output_tokens=1400,
            error_prefix="analysis_failed",
        )

    async def search_x_posts(
        self,
        query: str,
        limit: int,
    ) -> XSearchResultPayload | None:
        prompt = (
            f"Search X for the query: {query}\n"
            f"Return up to {limit} recent or relevant posts. "
            "For each item, include a short title, canonical URL, concise summary, and published_at if available."
        )
        return await self._parse_structured_output(
            target="x_search",
            schema=XSearchResultPayload,
            instructions=(
                "You can search X directly. "
                "Return only posts you can ground in the X search results. "
                "Prefer canonical x.com URLs."
            ),
            prompt=prompt,
            max_output_tokens=1400,
            error_prefix="x_search_failed",
        )

    def _model_for_target(self, target: TargetRole) -> str:
        if target == "primary":
            return self.settings.openai_primary_model
        if target == "extraction":
            return self.settings.resolved_openai_extraction_model
        if target == "x_search":
            return self.settings.resolved_openai_x_search_model
        return self.settings.resolved_openai_report_model

    def _base_url_for_target(self, target: TargetRole) -> str | None:
        if target == "primary":
            return self.settings.resolved_openai_primary_base_url
        if target == "extraction":
            return self.settings.resolved_openai_extraction_base_url
        if target == "x_search":
            return self.settings.resolved_openai_x_search_base_url
        return self.settings.resolved_openai_report_base_url

    def _extract_chat_text(self, response: object) -> str:
        choices = getattr(response, "choices", [])
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        if message is None:
            return ""
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif hasattr(item, "text"):
                    parts.append(str(item.text))
            return self._sanitize_model_text("".join(parts))
        return self._sanitize_model_text(str(content))

    async def _create_chat_completion_raw(
        self,
        target: TargetRole,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        response_format: dict[str, str] | None = None,
    ) -> tuple[str | None, str]:
        base_url = self._base_url_for_target(target)
        api_key = self._api_key_for_target(target)
        if not base_url or not api_key:
            raise RuntimeError(f"{target} raw chat fallback is not configured.")

        payload: dict[str, object] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.settings.openai_timeout_seconds, follow_redirects=True) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        return self._parse_raw_chat_completion(response.text)

    def _parse_raw_chat_completion(self, body: str) -> tuple[str | None, str]:
        stripped = body.strip()
        if stripped.startswith("data:"):
            response_id: str | None = None
            parts: list[str] = []
            for line in stripped.splitlines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                payload = json.loads(data)
                response_id = response_id or payload.get("id")
                for choice in payload.get("choices", []):
                    delta = choice.get("delta", {})
                    content = delta.get("content")
                    if content:
                        parts.append(str(content))
            return response_id, self._sanitize_model_text("".join(parts))

        payload = json.loads(stripped)
        response_id = payload.get("id")
        choices = payload.get("choices", [])
        if not choices:
            return response_id, ""
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return response_id, self._sanitize_model_text("".join(parts))
        return response_id, self._sanitize_model_text(str(content))

    def _extract_json_payload(self, raw_text: str) -> str:
        sanitized = self._sanitize_model_text(raw_text)
        for opening, closing in (("{", "}"), ("[", "]")):
            start = sanitized.find(opening)
            end = sanitized.rfind(closing)
            if start != -1 and end != -1 and end >= start:
                return sanitized[start : end + 1]
        return sanitized

    def _sanitize_model_text(self, value: str) -> str:
        cleaned = _THINK_BLOCK_RE.sub("", value or "")
        cleaned = cleaned.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    def _api_key_for_target(self, target: TargetRole) -> str | None:
        if target == "primary":
            return self.settings.resolved_openai_primary_api_key
        if target == "extraction":
            return self.settings.resolved_openai_extraction_api_key
        if target == "x_search":
            return self.settings.resolved_openai_x_search_api_key
        return self.settings.resolved_openai_report_api_key
