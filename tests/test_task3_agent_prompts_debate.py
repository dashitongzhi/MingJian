"""Tests for Task 3: Optimized agent prompts, auto-trigger debate, and position revision."""

from __future__ import annotations

import pytest

from planagent.domain.enums import EventTopic
from planagent.services.agent_registry import (
    ADVOCATE_PROMPT,
    ARBITRATOR_PROMPT,
    CHALLENGER_PROMPT,
    ECONOMIC_PROMPT,
    EVIDENCE_ASSESSOR_PROMPT,
    GEOPOLITICAL_PROMPT,
    MILITARY_PROMPT,
    SOCIAL_PROMPT,
    TECH_PROMPT,
    AgentRegistry,
    AgentRole,
    DEFAULT_AGENTS,
    get_agent_registry,
    reset_agent_registry,
)
from planagent.services.debate import DebateService


# ── Agent Prompt Optimization Tests ────────────────────────────


class TestAgentPrompts:
    """Test that all 9 agent prompts are properly optimized."""

    def test_all_agents_have_descriptions(self):
        """每个 Agent 都必须有非空的 description。"""
        for agent in DEFAULT_AGENTS:
            assert agent.description, f"Agent {agent.role.value} has empty description"
            assert len(agent.description) > 50, (
                f"Agent {agent.role.value} description too short: {len(agent.description)} chars"
            )

    def test_prompt_constants_defined(self):
        """所有9个 prompt 常量都已定义。"""
        constants = [
            ADVOCATE_PROMPT,
            CHALLENGER_PROMPT,
            ARBITRATOR_PROMPT,
            EVIDENCE_ASSESSOR_PROMPT,
            GEOPOLITICAL_PROMPT,
            ECONOMIC_PROMPT,
            MILITARY_PROMPT,
            TECH_PROMPT,
            SOCIAL_PROMPT,
        ]
        for const in constants:
            assert const is not None
            assert len(const) > 100

    def test_each_prompt_has_required_sections(self):
        """每个 prompt 必须包含关键结构化部分。"""
        required_sections = [
            "## 专业领域边界",
            "## 论证方法论",
            "## 与其他角色的协作规则",
            "## 输出格式",
        ]
        all_prompts = {
            "advocate": ADVOCATE_PROMPT,
            "challenger": CHALLENGER_PROMPT,
            "arbitrator": ARBITRATOR_PROMPT,
            "evidence_assessor": EVIDENCE_ASSESSOR_PROMPT,
            "geopolitical": GEOPOLITICAL_PROMPT,
            "economic": ECONOMIC_PROMPT,
            "military": MILITARY_PROMPT,
            "tech": TECH_PROMPT,
            "social": SOCIAL_PROMPT,
        }
        for role, prompt in all_prompts.items():
            for section in required_sections:
                assert section in prompt, (
                    f"Agent {role} missing section: {section}"
                )

    def test_prompts_reference_other_roles(self):
        """每个 prompt 必须至少引用1个其他角色名。"""
        role_names = ["ADVOCATE", "CHALLENGER", "ARBITRATOR", "EVIDENCE_ASSESSOR",
                      "GEOPOLITICAL", "MILITARY", "ECONOMIC", "TECH", "SOCIAL"]
        all_prompts = [
            ADVOCATE_PROMPT, CHALLENGER_PROMPT, ARBITRATOR_PROMPT,
            EVIDENCE_ASSESSOR_PROMPT, GEOPOLITICAL_PROMPT, ECONOMIC_PROMPT,
            MILITARY_PROMPT, TECH_PROMPT, SOCIAL_PROMPT,
        ]
        for prompt in all_prompts:
            other_roles_mentioned = sum(1 for name in role_names if name in prompt)
            assert other_roles_mentioned >= 1, (
                f"Prompt should reference at least 1 other role name"
            )

    def test_registry_agents_use_optimized_prompts(self):
        """AgentRegistry 中的 agent 应使用优化后的 prompt。"""
        registry = reset_agent_registry()
        agent = registry.get_agent(AgentRole.ADVOCATE)
        assert "## 专业领域边界" in agent.description
        assert "## 论证方法论" in agent.description

    def test_get_status_includes_descriptions(self):
        """get_status 应返回包含优化描述的 agent 信息。"""
        registry = reset_agent_registry()
        status = registry.get_status()
        assert len(status["agents"]) == 9
        for agent_info in status["agents"]:
            assert "## 论证方法论" in agent_info["description"], (
                f"Agent {agent_info['role']} status missing optimized description"
            )


# ── Auto-Trigger Debate Tests ────────────────────────────────


class TestAutoDetectDisagreement:
    """Test the auto_detect_disagreement static method."""

    def test_no_trigger_when_consensus(self):
        """所有 Agent 一致时不触发辩论。"""
        assessments = [
            {"role": "advocate", "position": "SUPPORT", "confidence": 0.8},
            {"role": "challenger", "position": "SUPPORT", "confidence": 0.75},
            {"role": "geo_expert", "position": "SUPPORT", "confidence": 0.7},
        ]
        result = DebateService.auto_detect_disagreement(assessments)
        assert result["should_trigger"] is False
        assert result["trigger_reasons"] == []
        assert result["confidence_spread"] < 0.30

    def test_trigger_on_high_confidence_spread(self):
        """置信度差异 > 30% 时触发辩论。"""
        assessments = [
            {"role": "advocate", "position": "SUPPORT", "confidence": 0.9},
            {"role": "challenger", "position": "CONDITIONAL", "confidence": 0.3},
        ]
        result = DebateService.auto_detect_disagreement(assessments)
        assert result["should_trigger"] is True
        assert any("置信度差异" in r for r in result["trigger_reasons"])
        assert result["confidence_spread"] > 0.30

    def test_trigger_on_position_opposition(self):
        """SUPPORT vs OPPOSE 立场对立时触发辩论。"""
        assessments = [
            {"role": "advocate", "position": "SUPPORT", "confidence": 0.7},
            {"role": "challenger", "position": "OPPOSE", "confidence": 0.65},
        ]
        result = DebateService.auto_detect_disagreement(assessments)
        assert result["should_trigger"] is True
        assert any("立场对立" in r for r in result["trigger_reasons"])
        assert len(result["position_conflicts"]) == 1
        assert "advocate" in result["position_conflicts"][0]["support"]
        assert "challenger" in result["position_conflicts"][0]["oppose"]

    def test_trigger_on_both_conditions(self):
        """同时满足置信度差异和立场对立时触发。"""
        assessments = [
            {"role": "advocate", "position": "SUPPORT", "confidence": 0.9},
            {"role": "challenger", "position": "OPPOSE", "confidence": 0.2},
            {"role": "geo_expert", "position": "SUPPORT", "confidence": 0.8},
            {"role": "military_strategist", "position": "OPPOSE", "confidence": 0.4},
        ]
        result = DebateService.auto_detect_disagreement(assessments)
        assert result["should_trigger"] is True
        assert len(result["trigger_reasons"]) >= 2
        assert result["confidence_spread"] > 0.30

    def test_no_trigger_with_few_agents(self):
        """少于2个 Agent 时不触发辩论。"""
        assessments = [
            {"role": "advocate", "position": "SUPPORT", "confidence": 0.9},
        ]
        result = DebateService.auto_detect_disagreement(assessments)
        assert result["should_trigger"] is False

    def test_custom_threshold(self):
        """自定义置信度阈值。"""
        assessments = [
            {"role": "advocate", "position": "CONDITIONAL", "confidence": 0.8},
            {"role": "challenger", "position": "CONDITIONAL", "confidence": 0.6},
        ]
        # 默认阈值 0.30 不触发
        result = DebateService.auto_detect_disagreement(assessments, confidence_threshold=0.30)
        assert result["should_trigger"] is False

        # 降低阈值到 0.15 触发
        result = DebateService.auto_detect_disagreement(assessments, confidence_threshold=0.15)
        assert result["should_trigger"] is True

    def test_disagreement_details_structure(self):
        """disagreement_details 应包含完整的 agent 位置信息。"""
        assessments = [
            {
                "role": "advocate",
                "position": "SUPPORT",
                "confidence": 0.7,
                "arguments": [{"claim": "Test claim"}],
            },
            {
                "role": "challenger",
                "position": "OPPOSE",
                "confidence": 0.6,
                "arguments": [{"claim": "Counter claim"}],
            },
        ]
        result = DebateService.auto_detect_disagreement(assessments)
        details = result["disagreement_details"]
        assert "agent_positions" in details
        assert len(details["agent_positions"]) == 2
        assert details["agent_positions"][0]["role"] == "advocate"
        assert details["agent_positions"][0]["key_argument"] == "Test claim"

    def test_position_case_insensitive(self):
        """立场检测应大小写不敏感。"""
        assessments = [
            {"role": "advocate", "position": "support", "confidence": 0.7},
            {"role": "challenger", "position": "OPPOSE", "confidence": 0.6},
        ]
        result = DebateService.auto_detect_disagreement(assessments)
        assert result["should_trigger"] is True


# ── Position Revision Tests ──────────────────────────────────


class TestPositionRevision:
    """Test detect_overturned_arguments and generate_revision_prompt."""

    def test_detect_confidence_drop(self):
        """检测置信度显著下降。"""
        rounds = [
            {"role": "advocate", "round_number": 1, "confidence": 0.9,
             "position": "SUPPORT", "concessions": []},
            {"role": "challenger", "round_number": 1, "confidence": 0.7,
             "position": "OPPOSE", "concessions": []},
            {"role": "advocate", "round_number": 3, "confidence": 0.4,
             "position": "SUPPORT",
             "concessions": [{"reason": "Supply chain data was unreliable"}]},
        ]
        overturned = DebateService.detect_overturned_arguments(rounds)
        assert len(overturned) == 1
        assert overturned[0]["role"] == "advocate"
        assert overturned[0]["confidence_drop"] > 0.3
        assert overturned[0]["revision_needed"] is True

    def test_detect_position_flip(self):
        """检测立场翻转。"""
        rounds = [
            {"role": "advocate", "round_number": 1, "confidence": 0.8,
             "position": "SUPPORT", "concessions": []},
            {"role": "advocate", "round_number": 3, "confidence": 0.3,
             "position": "OPPOSE", "concessions": []},
        ]
        overturned = DebateService.detect_overturned_arguments(rounds)
        assert len(overturned) == 1
        assert overturned[0]["position_flipped"] is True
        assert overturned[0]["original_position"] == "SUPPORT"
        assert overturned[0]["revised_position"] == "OPPOSE"

    def test_detect_explicit_concessions(self):
        """检测明确放弃的论点。"""
        rounds = [
            {"role": "challenger", "round_number": 1, "confidence": 0.7,
             "position": "OPPOSE", "concessions": []},
            {"role": "challenger", "round_number": 3, "confidence": 0.6,
             "position": "CONDITIONAL",
             "concessions": [{"reason": "Historical analogy was flawed"}]},
        ]
        overturned = DebateService.detect_overturned_arguments(rounds)
        assert len(overturned) == 1
        assert "Historical analogy was flawed" in overturned[0]["overturned_claims"]

    def test_no_overturn_with_stable_confidence(self):
        """置信度稳定时不应标记为被推翻。"""
        rounds = [
            {"role": "advocate", "round_number": 1, "confidence": 0.7,
             "position": "SUPPORT", "concessions": []},
            {"role": "advocate", "round_number": 3, "confidence": 0.65,
             "position": "SUPPORT", "concessions": []},
        ]
        overturned = DebateService.detect_overturned_arguments(rounds)
        assert len(overturned) == 0

    def test_empty_rounds(self):
        """空轮次列表应返回空结果。"""
        overturned = DebateService.detect_overturned_arguments([])
        assert overturned == []

    def test_single_round_per_role(self):
        """单轮角色不应被标记为推翻。"""
        rounds = [
            {"role": "advocate", "round_number": 1, "confidence": 0.8,
             "position": "SUPPORT", "concessions": []},
        ]
        overturned = DebateService.detect_overturned_arguments(rounds)
        assert len(overturned) == 0

    def test_custom_threshold(self):
        """自定义推翻阈值。"""
        rounds = [
            {"role": "advocate", "round_number": 1, "confidence": 0.8,
             "position": "SUPPORT", "concessions": []},
            {"role": "advocate", "round_number": 3, "confidence": 0.6,
             "position": "SUPPORT", "concessions": []},
        ]
        # 默认阈值 0.3 不触发
        overturned = DebateService.detect_overturned_arguments(rounds, overturn_threshold=0.3)
        assert len(overturned) == 0

        # 降低阈值到 0.15 触发
        overturned = DebateService.detect_overturned_arguments(rounds, overturn_threshold=0.15)
        assert len(overturned) == 1

    def test_generate_revision_prompt(self):
        """修订提示应包含关键信息。"""
        service = DebateService.__new__(DebateService)
        prompt = service.generate_revision_prompt(
            role="advocate",
            original_position="SUPPORT",
            revised_position="CONDITIONAL",
            overturned_claims=["Data was unreliable", "Logic was circular"],
            confidence_drop=0.4,
        )
        assert "advocate" in prompt
        assert "SUPPORT" in prompt
        assert "CONDITIONAL" in prompt
        assert "40.0%" in prompt
        assert "Data was unreliable" in prompt
        assert "Logic was circular" in prompt
        assert "修订操作" in prompt

    def test_generate_revision_prompt_no_claims(self):
        """没有明确放弃记录时的修订提示。"""
        service = DebateService.__new__(DebateService)
        prompt = service.generate_revision_prompt(
            role="challenger",
            original_position="OPPOSE",
            revised_position="CONDITIONAL",
            overturned_claims=[],
            confidence_drop=0.35,
        )
        assert "无明确放弃记录" in prompt
        assert "challenger" in prompt


# ── EventTopic Tests ─────────────────────────────────────────


class TestEventTopicExtensions:
    """Test new event topic enums."""

    def test_debate_auto_trigger_topic(self):
        """DEBATE_AUTO_TRIGGER 事件主题应存在。"""
        assert hasattr(EventTopic, "DEBATE_AUTO_TRIGGER")
        assert EventTopic.DEBATE_AUTO_TRIGGER.value == "debate.auto_trigger"

    def test_debate_revision_topic(self):
        """DEBATE_REVISION 事件主题应存在。"""
        assert hasattr(EventTopic, "DEBATE_REVISION")
        assert EventTopic.DEBATE_REVISION.value == "debate.revision"

    def test_all_debate_topics_exist(self):
        """所有辩论相关事件主题应存在。"""
        debate_topics = [
            "DEBATE_TRIGGERED",
            "DEBATE_COMPLETED",
            "DEBATE_AUTO_TRIGGER",
            "DEBATE_REVISION",
        ]
        for topic_name in debate_topics:
            assert hasattr(EventTopic, topic_name), f"Missing topic: {topic_name}"


# ── Integration Tests ─────────────────────────────────────────


class TestAgentRegistryIntegration:
    """Test agent registry integration with optimized prompts."""

    def test_all_nine_roles_present(self):
        """注册中心应包含全部9个角色。"""
        registry = reset_agent_registry()
        agents = registry.get_all_agents()
        assert len(agents) == 9
        roles = {a.role for a in agents}
        assert roles == set(AgentRole)

    def test_core_agents_have_priority_one(self):
        """核心辩论角色（ADVOCATE/CHALLENGER/ARBITRATOR）优先级为1。"""
        registry = reset_agent_registry()
        for role in [AgentRole.ADVOCATE, AgentRole.CHALLENGER, AgentRole.ARBITRATOR]:
            assert registry.get_agent(role).priority == 1

    def test_perspective_agents_have_priority_two(self):
        """视角分析角色优先级为2。"""
        registry = reset_agent_registry()
        perspective_roles = [
            AgentRole.EVIDENCE_ASSESSOR,
            AgentRole.GEOPOLITICAL,
            AgentRole.ECONOMIC,
            AgentRole.MILITARY,
            AgentRole.TECH,
            AgentRole.SOCIAL,
        ]
        for role in perspective_roles:
            assert registry.get_agent(role).priority == 2

    def test_descriptions_are_structured_prompts(self):
        """描述应是结构化的 prompt（包含 ## 标记）。"""
        registry = reset_agent_registry()
        for agent in registry.get_all_agents():
            assert "##" in agent.description, (
                f"Agent {agent.role.value} description lacks structured sections"
            )
