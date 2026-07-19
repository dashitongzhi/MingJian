from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.api import DebateTriggerRequest
from planagent.domain.models import (
    Claim,
    DecisionRecordRecord,
    EvidenceItem,
    ExternalShockRecord,
    GeneratedReport,
    SimulationRun,
)
from planagent.services.openai_client import OpenAIService
from planagent.services.openai_client import DebatePositionPayload
from planagent.services.providers import AnthropicProvider

from .contracts import ClaimRelationContext, DebateStreamEvent, DebateStreamPreparation
from .prompts import build_round_plan
from .prompts import debate_role_instruction
from .roles import DEBATE_ROLE_DISPLAY, registry_role_for_debate

_TOKEN_BUDGET_PER_ROUND = 60000
_WRAP_UP_RATIO = 0.8
_KEEP_RECENT_MESSAGES = 3


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _inject_wrap_up_nudge(messages: list, used: int, budget: int) -> None:
    if used > budget * _WRAP_UP_RATIO:
        messages.append(
            {
                "role": "system",
                "content": (
                    f"[系统] Token预算即将耗尽（已用{used}/{budget}）。"
                    "请立即停止扩展论证，输出最终立场总结。"
                ),
            }
        )


def _trim_old_messages(messages: list, keep: int = _KEEP_RECENT_MESSAGES) -> list:
    if len(messages) <= keep:
        return messages
    trimmed = []
    for msg in messages[:-keep]:
        trimmed.append(
            {
                "round_number": msg.get("round_number", 0),
                "role": msg.get("role", "unknown"),
                "position": msg.get("position", "NEUTRAL"),
                "confidence": msg.get("confidence", 0.0),
                "arguments": [],
                "rebuttals": [],
                "concessions": [],
            }
        )
    trimmed.extend(messages[-keep:])
    return trimmed


class DebateInterruptPort(Protocol):
    async def get_pending_interrupts(
        self,
        session: AsyncSession,
        debate_id: str,
    ) -> list[Any]: ...

    def format_interrupts_for_context(self, interrupts: list[Any]) -> str: ...

    async def mark_interrupts_injected(
        self,
        session: AsyncSession,
        debate_id: str,
        round_number: int,
    ) -> int: ...


class DebatePreparationPort(Protocol):
    async def find_claim_relations(
        self,
        session: AsyncSession,
        claim: Claim,
    ) -> ClaimRelationContext: ...

    async def _run_subject_name(
        self,
        session: AsyncSession,
        run: SimulationRun,
    ) -> str: ...


class LLMDebateAdapter:
    """Execute model-backed debate rounds with provider and heuristic fallback."""

    def __init__(
        self,
        settings: Settings,
        openai_service: OpenAIService | None,
        agent_registry: object | None,
    ) -> None:
        self.settings = settings
        self.openai_service = openai_service
        self.agent_registry = agent_registry

    def is_available(self) -> bool:
        """Return whether any configured model provider can execute debate rounds."""
        if self._anthropic_is_configured():
            return True
        if self.openai_service is None:
            return False
        return any(
            self.openai_service.is_configured(target)
            for target in [
                "debate_advocate",
                "debate_challenger",
                "debate_arbitrator",
                "primary",
                "extraction",
                "report",
            ]
        )

    async def _call_llm(
        self,
        *,
        role: str,
        topic: str,
        trigger_type: str,
        context: str,
        opponent_arguments: list[dict[str, Any]] | None = None,
        own_previous: list[dict[str, Any]] | None = None,
    ) -> DebatePositionPayload | None:
        # ── 优先使用 Agent Registry ──────────────────────────
        registry_cfg = self._get_agent_registry_config(role)
        if registry_cfg and registry_cfg.get("api_key"):
            result = await self._call_registry_llm(
                role=role,
                topic=topic,
                trigger_type=trigger_type,
                context=context,
                opponent_arguments=opponent_arguments,
                own_previous=own_previous,
                cfg=registry_cfg,
            )
            if result is not None:
                return result

        # ── 回退到原有 settings 逻辑 ────────────────────────
        requested_provider = self._debate_provider_for_role(role)
        provider_order = list(dict.fromkeys([requested_provider, "openai"]))
        for provider_name in provider_order:
            if provider_name == "anthropic":
                result = await self._call_anthropic_llm(
                    role=role,
                    topic=topic,
                    trigger_type=trigger_type,
                    context=context,
                    opponent_arguments=opponent_arguments,
                    own_previous=own_previous,
                )
            elif provider_name == "openai":
                result = await self._call_openai_llm(
                    role=role,
                    topic=topic,
                    trigger_type=trigger_type,
                    context=context,
                    opponent_arguments=opponent_arguments,
                    own_previous=own_previous,
                )
            else:
                result = None
            if result is not None:
                return result
        return None

    async def _call_openai_llm(
        self,
        *,
        role: str,
        topic: str,
        trigger_type: str,
        context: str,
        opponent_arguments: list[dict[str, Any]] | None,
        own_previous: list[dict[str, Any]] | None,
    ) -> DebatePositionPayload | None:
        if self.openai_service is None:
            return None
        target = self._debate_target_for_role(role)
        if not self.openai_service.is_configured(target):
            return None

        prompt = self._build_debate_prompt(
            role=role,
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            opponent_arguments=opponent_arguments,
            own_previous=own_previous,
        )
        if hasattr(self.openai_service, "generate_json_for_target"):
            _, parsed = await self.openai_service.generate_json_for_target(
                target=target,
                system_prompt=self._debate_role_instruction(role),
                user_content=(
                    f"{prompt}\n\n"
                    "Return valid JSON only. "
                    f"Target schema: {DebatePositionPayload.model_json_schema()}"
                ),
                max_tokens=1000,
            )
            position = self._parse_debate_position_payload(parsed)
            if position is not None:
                return position

        return await self.openai_service.generate_debate_position(
            role=role,
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            opponent_arguments=opponent_arguments,
            own_previous=own_previous,
            target=target,
        )

    async def _call_anthropic_llm(
        self,
        *,
        role: str,
        topic: str,
        trigger_type: str,
        context: str,
        opponent_arguments: list[dict[str, Any]] | None,
        own_previous: list[dict[str, Any]] | None,
    ) -> DebatePositionPayload | None:
        if not self._anthropic_is_configured():
            return None
        if not self.settings.anthropic_model:
            return None
        provider = AnthropicProvider(
            api_key=self.settings.resolved_anthropic_api_key,
            base_url=self.settings.resolved_anthropic_base_url,
            timeout=self.settings.openai_timeout_seconds,
        )
        try:
            prompt = self._build_debate_prompt(
                role=role,
                topic=topic,
                trigger_type=trigger_type,
                context=context,
                opponent_arguments=opponent_arguments,
                own_previous=own_previous,
            )
            _, parsed = await provider.generate_json(
                model=self.settings.anthropic_model,
                system_prompt=self._debate_role_instruction(role),
                user_prompt=prompt,
                schema=DebatePositionPayload.model_json_schema(),
                max_tokens=1000,
                temperature=0.3,
            )
            return self._parse_debate_position_payload(parsed)
        finally:
            await provider.close()

    def _debate_provider_for_role(self, role: str) -> str:
        # Custom agents default to openai
        if role.startswith("custom_"):
            return "openai"
        role_providers = {
            "advocate": self.settings.debate_advocate_provider,
            "strategist": self.settings.debate_advocate_provider,
            "challenger": self.settings.debate_challenger_provider,
            "risk_analyst": self.settings.debate_challenger_provider,
            "arbitrator": self.settings.debate_arbitrator_provider,
            "opportunist": self.settings.debate_arbitrator_provider,
            "intel_analyst": self.settings.debate_challenger_provider,
            "geo_expert": self.settings.debate_advocate_provider,
            "econ_analyst": self.settings.debate_advocate_provider,
            "military_strategist": self.settings.debate_advocate_provider,
            "tech_foresight": self.settings.debate_advocate_provider,
            "social_impact": self.settings.debate_advocate_provider,
        }
        return role_providers.get(role, "openai").strip().lower() or "openai"

    def _get_agent_registry_config(self, role: str) -> dict[str, str] | None:
        """从 Agent Registry 获取角色的 provider 配置"""
        if self.agent_registry is None:
            return None
        # Custom agents use their role_key directly
        if role.startswith("custom_"):
            try:
                return self.agent_registry.get_provider_config(role)
            except Exception:
                return None
        agent_role = registry_role_for_debate(role)
        try:
            return self.agent_registry.get_provider_config(agent_role)
        except Exception:
            return None

    async def _call_registry_llm(
        self,
        *,
        role: str,
        topic: str,
        trigger_type: str,
        context: str,
        opponent_arguments: list[dict[str, Any]] | None,
        own_previous: list[dict[str, Any]] | None,
        cfg: dict[str, str],
    ) -> DebatePositionPayload | None:
        """使用 Agent Registry 的配置调用 LLM"""
        provider_type = cfg.get("provider_type", "openai")
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("base_url", "")
        model = cfg.get("model", "")

        if not api_key:
            return None

        prompt = self._build_debate_prompt(
            role=role,
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            opponent_arguments=opponent_arguments,
            own_previous=own_previous,
        )

        if provider_type == "anthropic":
            selected_model = model or self.settings.anthropic_model
            if not selected_model:
                return None
            provider = AnthropicProvider(api_key=api_key, base_url=base_url or None, timeout=45.0)
            try:
                _, parsed = await provider.generate_json(
                    model=selected_model,
                    system_prompt=self._debate_role_instruction(role),
                    user_prompt=prompt,
                    schema=DebatePositionPayload.model_json_schema(),
                    max_tokens=1000,
                    temperature=0.3,
                )
                return self._parse_debate_position_payload(parsed)
            finally:
                await provider.close()
        else:
            # OpenAI 兼容
            if not model:
                return None
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url or None,
                timeout=45.0,
            )
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": self._debate_role_instruction(role)},
                        {"role": "user", "content": f"{prompt}\n\nReturn valid JSON only."},
                    ],
                    max_tokens=1000,
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )
                import json

                content = resp.choices[0].message.content or "{}"
                parsed = json.loads(content)
                return self._parse_debate_position_payload(parsed)
            except Exception:
                return None
            finally:
                await client.close()

    def _anthropic_is_configured(self) -> bool:
        return bool(self.settings.resolved_anthropic_api_key)

    def _debate_role_instruction(self, role: str) -> str:
        return debate_role_instruction(role)

    def _build_debate_prompt(
        self,
        *,
        role: str,
        topic: str,
        trigger_type: str,
        context: str,
        opponent_arguments: list[dict[str, Any]] | None = None,
        own_previous: list[dict[str, Any]] | None = None,
    ) -> str:
        role_display = DEBATE_ROLE_DISPLAY.get(role, role)

        opponent_text = ""
        if opponent_arguments:
            opponent_text = "\n【前序论证摘要】\n" + "\n".join(
                f"- {a.get('claim', a.get('counter', str(a)))[:200]}"
                for a in opponent_arguments[:8]
            )

        own_text = ""
        if own_previous:
            own_text = "\n【你此前的论点】\n" + "\n".join(
                f"- {a.get('claim', str(a))[:200]}" for a in own_previous[:5]
            )

        return (
            f"角色：{role_display}\n"
            f"议题：{topic}\n"
            f"触发类型：{trigger_type}\n"
            f"背景信息、证据项和相关声明：\n{context}\n"
            f"{opponent_text}{own_text}\n\n"
            "请返回以下结构化结果：\n"
            "1. 立场（SUPPORT/OPPOSE/CONDITIONAL）\n"
            "2. 置信度（0-1之间的浮点数）\n"
            "3. 最多3条论证（每条包含：claim-论点声明、evidence_ids-引用的证据ID、"
            "reasoning-推理过程、strength-论点强度0-1）\n"
            "4. 可选的反驳/质询（target_argument_idx-目标论点索引、target_role-目标角色、"
            "question-直接质询问题、counter-反驳内容或预期回答）\n"
            "5. 可选的让步（argument_idx-论点索引、reason-让步原因）\n"
            "请尽量使用提供的evidence_ids。如果进行了跨域分析，在reasoning中明确标注关联领域。"
        )

    def _parse_debate_position_payload(
        self, parsed: dict[str, Any] | None
    ) -> DebatePositionPayload | None:
        if parsed is None:
            return None
        try:
            return DebatePositionPayload.model_validate(parsed)
        except Exception:
            return None

    def _debate_target_for_role(self, role: str) -> str:
        if self.openai_service is None:
            return "primary"
        # Custom agents default to primary target
        if role.startswith("custom_"):
            return "primary"
        role_targets = {
            "advocate": ("debate_advocate", "primary"),
            "challenger": ("debate_challenger", "extraction", "primary"),
            "arbitrator": ("debate_arbitrator", "report", "primary"),
            "strategist": ("debate_advocate", "primary"),
            "risk_analyst": ("debate_challenger", "extraction", "primary"),
            "opportunist": ("debate_arbitrator", "report", "primary"),
            "intel_analyst": ("debate_challenger", "extraction", "primary"),
            "geo_expert": ("debate_advocate", "primary"),
            "econ_analyst": ("debate_advocate", "primary"),
            "military_strategist": ("debate_advocate", "primary"),
            "tech_foresight": ("debate_advocate", "primary"),
            "social_impact": ("debate_advocate", "primary"),
        }
        for target in role_targets.get(role, ("primary",)):
            if self.openai_service.is_configured(target):
                return target
        return "primary"

    async def stream_rounds(
        self,
        *,
        topic: str,
        trigger_type: str,
        context: str,
        evidence_ids: list[str],
        debate_mode: str = "full",
        domain_id: str | None = None,
        custom_agents: list[dict[str, Any]] | None = None,
        session: AsyncSession | None = None,
        debate_id: str | None = None,
        interrupt_port: DebateInterruptPort | None = None,
    ) -> AsyncIterator[DebateStreamEvent]:
        """Yield ordered round and interrupt observations for one model-backed debate."""
        completed_rounds: list[dict[str, Any]] = []
        round_plan = build_round_plan(
            custom_agents,
            mode=debate_mode,
            domain_id=domain_id,
            topic=topic,
            context=context,
            evidence_count=len(evidence_ids),
        )

        for round_number, role, instruction in round_plan:
            if session is not None and debate_id is not None and interrupt_port is not None:
                pending_interrupts = await interrupt_port.get_pending_interrupts(session, debate_id)
                interrupt_context = interrupt_port.format_interrupts_for_context(pending_interrupts)
                if interrupt_context:
                    context = f"{context}\n\n{interrupt_context}"
                    injected_count = await interrupt_port.mark_interrupts_injected(
                        session, debate_id, round_number
                    )
                    await session.flush()
                    yield DebateStreamEvent(
                        event="debate_interrupt_injected",
                        payload={
                            "round_number": round_number,
                            "role": role,
                            "count": injected_count,
                            "interrupt_ids": [item.id for item in pending_interrupts],
                        },
                    )
            yield DebateStreamEvent(
                event="debate_round_start",
                payload={"round_number": round_number, "role": role},
            )
            round_payload = await self._execute_single_round(
                round_number=round_number,
                role=role,
                instruction=instruction,
                topic=topic,
                trigger_type=trigger_type,
                context=context,
                evidence_ids=evidence_ids,
                completed_rounds=completed_rounds,
            )
            completed_rounds.append(round_payload)
            yield DebateStreamEvent(event="debate_round_complete", payload={"round": round_payload})

    async def _execute_single_round(
        self,
        *,
        round_number: int,
        role: str,
        instruction: str,
        topic: str,
        trigger_type: str,
        context: str,
        evidence_ids: list[str],
        completed_rounds: list[dict[str, Any]],
    ) -> dict[str, Any]:
        messages = self._build_round_messages(
            round_number=round_number,
            role=role,
            instruction=instruction,
            context=context,
            completed_rounds=completed_rounds,
        )
        position = await self._call_llm(
            role=role,
            topic=topic,
            trigger_type=trigger_type,
            context=messages["context"],
            opponent_arguments=messages["opponent_arguments"],
            own_previous=messages["own_previous"],
        )
        if position is None:
            return self._fallback_stream_round(
                round_number=round_number,
                role=role,
                topic=topic,
                context=context,
                evidence_ids=evidence_ids,
                completed_rounds=completed_rounds,
            )
        return self._position_to_round_payload(round_number, role, position, evidence_ids)

    def _build_round_messages(
        self,
        *,
        round_number: int,
        role: str,
        instruction: str,
        context: str,
        completed_rounds: list[dict[str, Any]],
    ) -> dict[str, Any]:
        def argument_refs(rounds: list[dict[str, Any]]) -> list[dict[str, str]]:
            return [
                {
                    "claim": str(argument.get("claim", "")),
                    "reasoning": str(argument.get("reasoning", "")),
                }
                for round_payload in rounds
                for argument in round_payload.get("arguments", [])
            ]

        def own_refs() -> list[dict[str, str]]:
            return [
                {"claim": str(argument.get("claim", ""))}
                for round_payload in completed_rounds
                if round_payload["role"] == role
                for argument in round_payload.get("arguments", [])
            ]

        def debate_history() -> str:
            lines: list[str] = []
            for item in completed_rounds:
                lines.append(
                    f"Round {item['round_number']} {item['role']} "
                    f"({item['position']}, confidence {item['confidence']:.2f}):"
                )
                for argument in item.get("arguments", [])[:3]:
                    claim = str(argument.get("claim", ""))[:90]
                    reasoning = str(argument.get("reasoning", ""))[:70]
                    lines.append(f"- {claim} | {reasoning}")
            return "\n".join(lines)

        def pending_cross_questions() -> str:
            lines: list[str] = []
            for item in completed_rounds:
                for rebuttal in item.get("rebuttals", []) or []:
                    target_role = str(
                        rebuttal.get("target_role")
                        or rebuttal.get("target")
                        or rebuttal.get("to_role")
                        or ""
                    )
                    if target_role and target_role != role:
                        continue
                    question = rebuttal.get("question") or rebuttal.get("counter")
                    if not question:
                        continue
                    source_role = str(item.get("role", "unknown"))
                    lines.append(f"- From {source_role}: {str(question)[:220]}")
            return "\n".join(lines)

        opponent_rounds = [
            item
            for item in completed_rounds
            if (round_number == 2 and item["round_number"] == 1)
            or (round_number == 3 and item["round_number"] == 2)
            or (role == "arbitrator")
        ]
        history = debate_history()
        cross_questions = pending_cross_questions()
        return {
            "context": (
                f"{instruction}\n\n"
                f"Debate history so far:\n{history or 'No prior debate rounds.'}\n\n"
                f"Pending cross-examination questions for this role:\n{cross_questions or 'None.'}\n\n"
                f"Original context:\n{context}"
            ),
            "opponent_arguments": argument_refs(opponent_rounds) if opponent_rounds else None,
            "own_previous": own_refs() if role != "arbitrator" else None,
        }

    def _position_to_round_payload(
        self,
        round_number: int,
        role: str,
        position: DebatePositionPayload,
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        return {
            "round_number": round_number,
            "role": role,
            "position": position.position,
            "confidence": position.confidence,
            "arguments": [
                {
                    "claim": argument.claim,
                    "evidence_ids": argument.evidence_ids or evidence_ids[:3],
                    "reasoning": argument.reasoning,
                    "strength": argument.strength,
                }
                for argument in position.arguments
            ],
            "rebuttals": position.rebuttals or [],
            "concessions": position.concessions or [],
        }

    def _fallback_stream_round(
        self,
        *,
        round_number: int,
        role: str,
        topic: str,
        context: str,
        evidence_ids: list[str],
        completed_rounds: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        position = "OPPOSE" if role == "challenger" else "CONDITIONAL"
        if role == "advocate" and round_number == 1:
            position = "SUPPORT"
        context_signals = self._fallback_context_signals(context)
        primary_signal = context_signals[0] if context_signals else topic
        prior_claim = self._fallback_prior_claim(completed_rounds or [])
        role_label = role.replace("_", " ")
        if role in {"challenger", "risk_analyst", "intel_analyst"}:
            claim = f"{role_label} flags a verification risk in {topic}: {primary_signal}"
            reasoning = (
                "The fallback round preserved the adversarial review because the cited context "
                "still needs confirmation against source freshness, conflict claims, and "
                "downstream decision impact."
            )
            strength = "MODERATE" if evidence_ids else "WEAK"
            rebuttals = [
                {
                    "target_argument_idx": 0,
                    "counter": prior_claim
                    or f"The supportive case for {topic} has not yet resolved this risk.",
                    "evidence_ids": evidence_ids[:3],
                }
            ]
            concessions: list[dict[str, Any]] = []
        elif role in {"arbitrator", "opportunist"}:
            claim = f"{role_label} keeps {topic} conditional pending the decisive evidence check."
            reasoning = (
                "The fallback arbitration weighs the available context signals and keeps the "
                "verdict conditional until the debate has a fully structured support and "
                "challenge record."
            )
            strength = "MODERATE" if evidence_ids else "WEAK"
            rebuttals = []
            concessions = [
                {
                    "argument_idx": 0,
                    "reason": f"Recheck this context signal before promotion: {primary_signal}",
                }
            ]
        else:
            claim = f"{role_label} supports a provisional read on {topic}: {primary_signal}"
            reasoning = (
                "The fallback round anchors the role's position to the provided debate context, "
                "then narrows the claim to a provisional recommendation that should be refreshed "
                "when the model response becomes available."
            )
            strength = "MODERATE" if evidence_ids else "WEAK"
            rebuttals = []
            concessions = []
        return {
            "round_number": round_number,
            "role": role,
            "position": position,
            "confidence": 0.56 if evidence_ids else 0.48,
            "arguments": [
                {
                    "claim": claim,
                    "evidence_ids": evidence_ids[:3],
                    "reasoning": reasoning,
                    "strength": strength,
                    "fallback_generated": True,
                    "context_signals": context_signals,
                }
            ],
            "rebuttals": rebuttals,
            "concessions": concessions,
        }

    def _fallback_context_signals(self, context: str, limit: int = 3) -> list[str]:
        signals: list[str] = []
        preferred_prefixes = (
            "Claim:",
            "Evidence:",
            "Evidence title:",
            "Subject:",
            "Final state:",
            "Matched rules:",
            "Shocks:",
            "Report summary:",
            "Strongest support:",
            "Strongest conflict:",
            "Trigger context:",
        )
        for raw_line in context.splitlines():
            line = " ".join(raw_line.strip().split())
            if not line:
                continue
            if line.startswith(preferred_prefixes):
                signals.append(line[:240])
            elif not signals and len(line) >= 24:
                signals.append(line[:240])
            if len(signals) >= limit:
                break
        return list(dict.fromkeys(signals))

    def _fallback_prior_claim(self, completed_rounds: list[dict[str, Any]]) -> str | None:
        for round_payload in reversed(completed_rounds):
            for argument in round_payload.get("arguments", []) or []:
                claim = str(argument.get("claim", "")).strip()
                if claim:
                    return claim[:240]
        return None

    async def collect_rounds(
        self,
        *,
        topic: str,
        trigger_type: str,
        context: str,
        evidence_ids: list[str],
        debate_mode: str = "full",
        domain_id: str | None = None,
        custom_agents: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]] | None:
        """Collect completed model-backed rounds for non-streaming assessment."""
        if not self.is_available():
            return None

        rounds: list[dict[str, Any]] = []
        async for stream_event in self.stream_rounds(
            topic=topic,
            trigger_type=trigger_type,
            context=context,
            evidence_ids=evidence_ids,
            debate_mode=debate_mode,
            domain_id=domain_id,
            custom_agents=custom_agents,
        ):
            if stream_event.event == "debate_round_complete":
                rounds.append(stream_event.payload["round"])
        return rounds if rounds else None

    async def prepare(
        self,
        session: AsyncSession,
        payload: DebateTriggerRequest,
        *,
        context_port: DebatePreparationPort,
    ) -> DebateStreamPreparation | None:
        """Load target context and assessment metadata for streaming execution."""
        if payload.claim_id is not None:
            claim = await session.get(Claim, payload.claim_id)
            if claim is None:
                raise LookupError(f"Claim {payload.claim_id} was not found.")
            evidence = await session.get(EvidenceItem, claim.evidence_item_id)
            relations = await context_port.find_claim_relations(session, claim)
            decisive_evidence = list(
                dict.fromkeys(
                    [
                        claim.evidence_item_id,
                        *[item.evidence_item_id for item in relations.supportive_claims[:2]],
                        *[item.evidence_item_id for item in relations.conflicting_claims[:2]],
                    ]
                )
            )
            context_parts = [
                f"Claim: {claim.statement}",
                f"Claim confidence: {claim.confidence}",
                f"Evidence title: {evidence.title if evidence is not None else 'unknown'}",
                f"Supporting claims: {len(relations.supportive_claims)}",
                f"Conflicting claims: {len(relations.conflicting_claims)}",
            ]
            if payload.context_lines:
                context_parts.append("Trigger context:\n" + "\n".join(payload.context_lines))
            if relations.supportive_claims:
                context_parts.append(
                    f"Strongest support: {relations.supportive_claims[0].statement[:200]}"
                )
            if relations.conflicting_claims:
                context_parts.append(
                    f"Strongest conflict: {relations.conflicting_claims[0].statement[:200]}"
                )
            return DebateStreamPreparation(
                context="\n".join(context_parts),
                llm_evidence_ids=decisive_evidence,
                assessment_evidence_ids=decisive_evidence,
                assessment_kwargs={
                    "claim_id": claim.id,
                    "claim_statement": claim.statement,
                    "claim_confidence": float(claim.confidence),
                },
            )

        if payload.target_type == "branch":
            return None

        assert payload.run_id is not None
        run = await session.get(SimulationRun, payload.run_id)
        if run is None:
            raise LookupError(f"Simulation run {payload.run_id} was not found.")
        report = (
            await session.scalars(
                select(GeneratedReport)
                .where(GeneratedReport.run_id == run.id)
                .order_by(GeneratedReport.created_at.desc())
                .limit(1)
            )
        ).first()
        latest_decision = (
            await session.scalars(
                select(DecisionRecordRecord)
                .where(DecisionRecordRecord.run_id == run.id)
                .order_by(DecisionRecordRecord.tick.desc(), DecisionRecordRecord.sequence.desc())
                .limit(1)
            )
        ).first()
        shocks = list(
            (
                await session.scalars(
                    select(ExternalShockRecord)
                    .where(ExternalShockRecord.run_id == run.id)
                    .order_by(ExternalShockRecord.tick.asc())
                )
            ).all()
        )
        final_state = {
            key: float(value) for key, value in run.summary.get("final_state", {}).items()
        }
        evidence_ids = [str(value) for value in run.summary.get("evidence_ids", [])]
        evidence_statements = [str(value) for value in run.summary.get("evidence_statements", [])]
        matched_rules = [str(value) for value in run.summary.get("matched_rules", [])]
        subject_name = await context_port._run_subject_name(session, run)
        context_parts = [
            f"Domain: {run.domain_id}",
            f"Subject: {subject_name}",
            f"Final state: {final_state}",
            f"Matched rules: {matched_rules[:5]}",
            f"Shocks: {[shock.shock_type for shock in shocks[:5]]}",
        ] + [f"Evidence: {statement}" for statement in evidence_statements[:3]]
        if payload.context_lines:
            context_parts.append("Trigger context:\n" + "\n".join(payload.context_lines))
        if report is not None:
            context_parts.append(f"Report summary: {report.summary[:500]}")
        return DebateStreamPreparation(
            context="\n".join(context_parts),
            llm_evidence_ids=evidence_ids[:5],
            assessment_evidence_ids=evidence_ids,
            assessment_kwargs={
                "run_id": run.id,
                "report_id": report.id if report is not None else None,
                "latest_decision_id": latest_decision.id if latest_decision is not None else None,
                "final_state": final_state,
                "evidence_statements": evidence_statements[:3],
            },
        )
