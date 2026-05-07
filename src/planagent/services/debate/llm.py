from __future__ import annotations

from typing import Any

from planagent.services.openai_client import DebatePositionPayload
from planagent.services.providers import AnthropicProvider

from .prompts import debate_role_instruction


class DebateLLMMixin:
    def _has_available_debate_provider(self) -> bool:
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
        provider = AnthropicProvider(
            api_key=self.settings.resolved_anthropic_api_key,
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

    def _get_custom_agents(self) -> list[dict[str, Any]]:
        """Get custom agent configs from the agent registry or YAML."""
        try:
            from planagent.services.agent_registry import load_custom_agent_configs

            return load_custom_agent_configs()
        except Exception:
            return []

    def _get_agent_registry_config(self, role: str) -> dict[str, str] | None:
        """从 Agent Registry 获取角色的 provider 配置"""
        if self.agent_registry is None:
            return None
        role_map = {
            "advocate": "advocate",
            "strategist": "advocate",
            "challenger": "challenger",
            "risk_analyst": "challenger",
            "arbitrator": "arbitrator",
            "opportunist": "arbitrator",
            "intel_analyst": "challenger",
            "geo_expert": "advocate",
            "econ_analyst": "advocate",
            "military_strategist": "advocate",
            "tech_foresight": "advocate",
            "social_impact": "advocate",
        }
        # Custom agents use their role_key directly
        if role.startswith("custom_"):
            try:
                return self.agent_registry.get_provider_config(role)
            except Exception:
                return None
        agent_role = role_map.get(role)
        if agent_role is None:
            return None
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
            provider = AnthropicProvider(api_key=api_key, timeout=45.0)
            try:
                _, parsed = await provider.generate_json(
                    model=model or self.settings.anthropic_model,
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
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url or None,
                timeout=45.0,
            )
            try:
                resp = await client.chat.completions.create(
                    model=model or "gpt-4o",
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
        _ROLE_DISPLAY = {
            "advocate": "战略支持者🟢",
            "challenger": "风险挑战者🔴",
            "arbitrator": "首席仲裁官⚖️",
            "intel_analyst": "情报分析师🔍",
            "geo_expert": "地缘政治专家🌍",
            "econ_analyst": "经济分析师💰",
            "military_strategist": "军事战略家⚔️",
            "tech_foresight": "技术前瞻者🔮",
            "social_impact": "社会影响评估师👥",
        }
        role_display = _ROLE_DISPLAY.get(role, role)

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
            "4. 可选的反驳（target_argument_idx-目标论点索引、counter-反驳内容）\n"
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
