from __future__ import annotations

import json
import re
from typing import Any, Literal

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from planagent.config import Settings
from planagent.domain.api import OpenAIStatusResponse, OpenAITestResponse
from planagent.services.pipeline import normalize_text

TargetRole = Literal[
    "primary",
    "extraction",
    "x_search",
    "report",
    "debate_advocate",
    "debate_challenger",
    "debate_arbitrator",
]
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


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


class PanelPerspectivePayload(BaseModel):
    stance: Literal["support", "challenge", "monitor"] = "monitor"
    summary: str
    key_points: list[str] = Field(default_factory=list)
    recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)


class ActionDecisionPayload(BaseModel):
    action_id: str
    reasoning: str
    expected_effect: dict[str, float] = Field(default_factory=dict)


class DebateArgumentPayload(BaseModel):
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)
    reasoning: str
    strength: str = "MODERATE"


class DebatePositionPayload(BaseModel):
    position: Literal["SUPPORT", "OPPOSE", "CONDITIONAL"]
    confidence: float = Field(ge=0.0, le=1.0)
    arguments: list[DebateArgumentPayload] = Field(default_factory=list)
    rebuttals: list[dict[str, str]] = Field(default_factory=list)
    concessions: list[dict[str, str]] = Field(default_factory=list)


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
            "debate_advocate": self._build_client(
                settings.resolved_openai_debate_advocate_api_key,
                settings.resolved_openai_debate_advocate_base_url,
            ),
            "debate_challenger": self._build_client(
                settings.resolved_openai_debate_challenger_api_key,
                settings.resolved_openai_debate_challenger_base_url,
            ),
            "debate_arbitrator": self._build_client(
                settings.resolved_openai_debate_arbitrator_api_key,
                settings.resolved_openai_debate_arbitrator_base_url,
            ),
        }
        self.target_diagnostics: dict[TargetRole, dict[str, str | bool | None]] = {
            target: self._default_target_diagnostic(target) for target in self.clients
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
        return bool(self.configured_targets())

    def is_configured(self, target: TargetRole) -> bool:
        return self.clients[target] is not None

    def configured_targets(self) -> list[TargetRole]:
        return [target for target, client in self.clients.items() if client is not None]

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
        configured_targets = self.configured_targets()
        return OpenAIStatusResponse(
            configured=bool(configured_targets),
            primary_configured=self.clients["primary"] is not None,
            extraction_configured=self.clients["extraction"] is not None,
            x_search_configured=self.clients["x_search"] is not None,
            report_configured=self.clients["report"] is not None,
            configured_targets=configured_targets,
            primary_model=self.settings.openai_primary_model,
            resolved_primary_model=resolve_openclaw_model_selector(self.settings.openai_primary_model),
            extraction_model=self.settings.resolved_openai_extraction_model,
            x_search_model=self.settings.resolved_openai_x_search_model,
            report_model=self.settings.resolved_openai_report_model,
            primary_base_url=self._base_url_for_target("primary"),
            extraction_base_url=self._base_url_for_target("extraction"),
            x_search_base_url=self._base_url_for_target("x_search"),
            report_base_url=self._base_url_for_target("report"),
            resolved_extraction_model=resolve_openclaw_model_selector(
                self.settings.resolved_openai_extraction_model
            ),
            resolved_x_search_model=resolve_openclaw_model_selector(
                self.settings.resolved_openai_x_search_model
            ),
            resolved_report_model=resolve_openclaw_model_selector(
                self.settings.resolved_openai_report_model
            ),
            model_sources={
                target: self.settings.openai_model_source(target) for target in self.clients
            },
            api_key_sources={
                target: self.settings.openai_api_key_source(target) for target in self.clients
            },
            base_url_sources={
                target: self.settings.openai_base_url_source(target) for target in self.clients
            },
            target_diagnostics={
                target: dict(values) for target, values in self.target_diagnostics.items()
            },
            base_url=self._base_url_for_target("primary"),
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
            f"Title: {normalize_text(title)}\n\n"
            f"Body:\n{normalize_text(body_text)[:5000]}"
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
        return await self._enhance_report(
            subject_label="Company",
            subject_name=company_name,
            evidence_statements=evidence_statements,
            actions=actions,
            leading_indicators=leading_indicators,
            matched_rules=matched_rules,
            extra_lines=[],
        )

    async def enhance_military_report(
        self,
        force_name: str,
        theater: str,
        evidence_statements: list[str],
        actions: list[str],
        leading_indicators: list[dict[str, float]],
        matched_rules: list[str],
        external_shocks: list[dict[str, str | int | list[str]]],
        scenario_assumptions: list[str] | None = None,
    ) -> ReportNarrativePayload | None:
        extra_lines = [
            f"Theater: {theater}",
            f"External shocks: {external_shocks[:5]}",
        ]
        if scenario_assumptions:
            extra_lines.append(f"Scenario assumptions: {scenario_assumptions[:5]}")

        return await self._enhance_report(
            subject_label="Force",
            subject_name=force_name,
            evidence_statements=evidence_statements,
            actions=actions,
            leading_indicators=leading_indicators,
            matched_rules=matched_rules,
            extra_lines=extra_lines,
        )

    async def _enhance_report(
        self,
        subject_label: str,
        subject_name: str,
        evidence_statements: list[str],
        actions: list[str],
        leading_indicators: list[dict[str, float]],
        matched_rules: list[str],
        extra_lines: list[str],
    ) -> ReportNarrativePayload | None:
        prompt_lines = [
            f"{subject_label}: {subject_name}",
            f"Evidence statements: {evidence_statements[:5]}",
            f"Actions taken: {actions[:10]}",
            f"Leading indicators: {leading_indicators}",
            f"Matched rules: {matched_rules[:10]}",
            *extra_lines,
            (
                "Return a concise executive summary, a short explanation of why the result happened, "
                "and up to 4 practical recommendations."
            ),
        ]
        return await self._parse_structured_output(
            target="report",
            schema=ReportNarrativePayload,
            instructions=(
                "You write evidence-grounded operational summaries. "
                "Do not invent data that is not present in the prompt."
            ),
            prompt="\n".join(prompt_lines),
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
            self._record_target_failure(
                target=target,
                error_prefix="connectivity_test_failed",
                failures=["client not configured"],
                model=resolved_model,
            )
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
            self._record_target_success(
                target=target,
                api_mode="responses",
                model=resolved_model,
                response_id=response.id,
            )
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
                self._record_target_success(
                    target=target,
                    api_mode="chat.completions",
                    model=resolved_model,
                    response_id=getattr(chat_response, "id", None),
                )
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
                    self._record_target_success(
                        target=target,
                        api_mode="chat.completions.raw",
                        model=resolved_model,
                        response_id=response_id,
                    )
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
                    last_error = self._record_target_failure(
                        target=target,
                        error_prefix="connectivity_test_failed",
                        failures=[
                            f"responses={self._sanitize_exception(responses_exc)}",
                            f"chat.completions={self._sanitize_exception(chat_exc)}",
                            f"raw={self._sanitize_exception(raw_exc)}",
                        ],
                        model=resolved_model,
                    )
                    return OpenAITestResponse(
                        ok=False,
                        configured=True,
                        target=target,
                        model=selected_model,
                        resolved_model=resolved_model,
                        base_url=base_url,
                        last_error=last_error,
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
            self._record_target_failure(
                target=target,
                error_prefix=error_prefix,
                failures=["client not configured"],
                model=resolve_openclaw_model_selector(self._model_for_target(target)),
            )
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
            self._record_target_success(target=target, api_mode="responses.parse", model=model)
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
                self._record_target_success(target=target, api_mode="chat.completions.json", model=model)
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
                    self._record_target_success(target=target, api_mode="chat.completions", model=model)
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
                        self._record_target_success(
                            target=target,
                            api_mode="chat.completions.raw",
                            model=model,
                        )
                        return schema.model_validate_json(self._extract_json_payload(raw_text))
                    except Exception as raw_exc:
                        self._record_target_failure(
                            target=target,
                            error_prefix=error_prefix,
                            failures=[
                                f"responses={self._sanitize_exception(responses_exc)}",
                                f"chat.json={self._sanitize_exception(chat_json_exc)}",
                                f"chat.completions={self._sanitize_exception(chat_exc)}",
                                f"raw={self._sanitize_exception(raw_exc)}",
                            ],
                            model=model,
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
            f"User input:\n{normalize_text(content)[:3000]}\n\n"
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

    async def generate_panel_perspective(
        self,
        target: TargetRole,
        label: str,
        topic: str,
        domain_id: str,
        subject_name: str,
        analysis_summary: str,
        findings: list[str],
        report_summary: str,
    ) -> PanelPerspectivePayload | None:
        prompt = (
            f"Role: {label}\n"
            f"Domain: {domain_id}\n"
            f"Subject: {subject_name}\n"
            f"User topic: {topic}\n"
            f"Analysis summary: {analysis_summary}\n"
            f"Key findings: {findings[:5]}\n"
            f"Simulation/report summary: {report_summary[:1200]}\n\n"
            "Return one panel perspective with a stance, a short summary, up to 4 key points, "
            "one recommendation, and a confidence score."
        )
        return await self._parse_structured_output(
            target=target,
            schema=PanelPerspectivePayload,
            instructions=(
                "You are one member of a strategic decision panel. "
                "Stay concise, evidence-grounded, and practical. "
                "Do not invent data that is not present in the prompt."
            ),
            prompt=prompt,
            max_output_tokens=900,
            error_prefix="panel_discussion_failed",
        )

    async def generate_action_decision(
        self,
        domain_id: str,
        state_summary: str,
        available_actions: list[dict[str, str]],
        recent_decisions: list[dict[str, str]],
        evidence: list[str],
        calibration_context: str = "",
        target: TargetRole = "report",
    ) -> ActionDecisionPayload | None:
        actions_text = "\n".join(
            f"- {a['action_id']}: {a.get('description', a['action_id'])}" for a in available_actions
        )
        decisions_text = "\n".join(
            f"- tick {d.get('tick', '?')}: {d.get('action_id', '?')} — {d.get('why', '')[:120]}" for d in recent_decisions
        )
        evidence_text = "\n".join(f"- {e[:200]}" for e in evidence[:5])
        calibration_text = (
            f"Calibration context:\n{calibration_context[:2000]}\n\n"
            if calibration_context
            else ""
        )
        prompt = (
            f"Domain: {domain_id}\n"
            f"{calibration_text}"
            f"Current state:\n{state_summary[:1200]}\n\n"
            f"Available actions:\n{actions_text}\n\n"
            f"Recent decisions:\n{decisions_text or 'None'}\n\n"
            f"Evidence:\n{evidence_text or 'None'}\n\n"
            "Select ONE action from the available actions. "
            "Return the action_id, a short reasoning for why, "
            "and the expected effect on 2-3 key metrics."
        )
        return await self._parse_structured_output(
            target=target,
            schema=ActionDecisionPayload,
            instructions=(
                "You are a strategic decision system for a simulation engine. "
                "Choose the best action given the current state, history, and evidence. "
                "Be concise. Only select from the listed available actions."
            ),
            prompt=prompt,
            max_output_tokens=500,
            error_prefix="action_decision_failed",
        )

    async def generate_debate_position(
        self,
        role: str,
        topic: str,
        trigger_type: str,
        context: str,
        opponent_arguments: list[dict] | None = None,
        own_previous: list[dict] | None = None,
        target: TargetRole | None = None,
    ) -> DebatePositionPayload | None:
        if target is None:
            target = "primary" if role == "advocate" else ("extraction" if role == "challenger" else "report")

        role_instruction = {
            "advocate": "You argue IN FAVOR of the proposition. Present supporting evidence and reasoning.",
            "challenger": "You argue AGAINST the proposition. Find counter-evidence and weaknesses.",
            "arbitrator": "You evaluate both sides fairly based on evidence quality. Deliver a verdict.",
        }.get(role, "You evaluate the proposition objectively.")

        opponent_text = ""
        if opponent_arguments:
            opponent_text = "\nOpponent's previous arguments:\n" + "\n".join(
                f"- {a.get('claim', a.get('counter', str(a)))[:200]}" for a in opponent_arguments[:5]
            )

        own_text = ""
        if own_previous:
            own_text = "\nYour previous arguments:\n" + "\n".join(
                f"- {a.get('claim', str(a))[:200]}" for a in own_previous[:3]
            )

        prompt = (
            f"Role: {role}\n"
            f"Topic: {topic}\n"
            f"Trigger: {trigger_type}\n"
            f"Context:\n{context[:2000]}\n"
            f"{opponent_text}{own_text}\n\n"
            "Return your position (SUPPORT/OPPOSE/CONDITIONAL), confidence (0-1), "
            "up to 3 arguments (each with claim, evidence_ids, reasoning, strength), "
            "optional rebuttals (target_argument_idx, counter), "
            "and optional concessions (argument_idx, reason)."
        )
        return await self._parse_structured_output(
            target=target,
            schema=DebatePositionPayload,
            instructions=role_instruction,
            prompt=prompt,
            max_output_tokens=1000,
            error_prefix="debate_position_failed",
        )

    def _model_for_target(self, target: TargetRole) -> str:
        if target == "primary":
            return self.settings.openai_primary_model
        if target == "extraction":
            return self.settings.resolved_openai_extraction_model
        if target == "x_search":
            return self.settings.resolved_openai_x_search_model
        if target == "debate_advocate":
            return self.settings.resolved_openai_debate_advocate_model
        if target == "debate_challenger":
            return self.settings.resolved_openai_debate_challenger_model
        if target == "debate_arbitrator":
            return self.settings.resolved_openai_debate_arbitrator_model
        return self.settings.resolved_openai_report_model

    def _base_url_for_target(self, target: TargetRole) -> str | None:
        if target == "primary":
            return self.settings.resolved_openai_primary_base_url or None
        if target == "extraction":
            return self.settings.resolved_openai_extraction_base_url or None
        if target == "x_search":
            return self.settings.resolved_openai_x_search_base_url or None
        if target == "debate_advocate":
            return self.settings.resolved_openai_debate_advocate_base_url or None
        if target == "debate_challenger":
            return self.settings.resolved_openai_debate_challenger_base_url or None
        if target == "debate_arbitrator":
            return self.settings.resolved_openai_debate_arbitrator_base_url or None
        return self.settings.resolved_openai_report_base_url or None

    def is_target_configured(self, target: str) -> bool:
        return self.is_configured(target)

    async def generate_json_for_target(
        self, target: str, system_prompt: str, user_content: str, max_tokens: int = 1000,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        client = self.clients.get(target)
        if client is None:
            return None, None
        model = resolve_openclaw_model_selector(self._model_for_target(target))
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
                max_tokens=max_tokens, temperature=0.3, response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            parsed = _extract_json_payload(text)
            return {"model": model, "api_mode": "chat.completions.json"}, parsed if isinstance(parsed, dict) else None
        except Exception:
            return None, None

    def _default_target_diagnostic(self, target: TargetRole) -> dict[str, str | bool | None]:
        return {
            "configured": self.is_configured(target),
            "resolved_model": resolve_openclaw_model_selector(self._model_for_target(target)),
            "base_url": self._base_url_for_target(target),
            "last_ok": None,
            "last_api_mode": None,
            "last_response_id": None,
            "last_error": None,
        }

    def _record_target_success(
        self,
        target: TargetRole,
        api_mode: str,
        model: str,
        response_id: str | None = None,
    ) -> None:
        diagnostic = self.target_diagnostics[target]
        diagnostic.update(
            {
                "configured": self.is_configured(target),
                "resolved_model": model,
                "base_url": self._base_url_for_target(target),
                "last_ok": True,
                "last_api_mode": api_mode,
                "last_response_id": response_id,
                "last_error": None,
            }
        )
        self.last_error = None

    def _record_target_failure(
        self,
        target: TargetRole,
        error_prefix: str,
        failures: list[str],
        model: str,
    ) -> str:
        message = f"{error_prefix}: {'; '.join(item for item in failures if item)}"
        diagnostic = self.target_diagnostics[target]
        diagnostic.update(
            {
                "configured": self.is_configured(target),
                "resolved_model": model,
                "base_url": self._base_url_for_target(target),
                "last_ok": False,
                "last_api_mode": None,
                "last_response_id": None,
                "last_error": message,
            }
        )
        self.last_error = f"{target}: {message}"
        return self.last_error

    def _sanitize_exception(self, exc: Exception) -> str:
        message = " ".join(str(exc).split())
        message = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-***", message)
        return f"{type(exc).__name__}: {message[:240]}" if message else type(exc).__name__

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
