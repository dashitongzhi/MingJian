"""Unit tests for DebateService — 辩论服务。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from planagent.services.debate import DebateService, DebateAssessment
from planagent.services.debate.triggers import DebateTriggerMixin
from planagent.services.debate.adjudication import DebateAdjudicationMixin


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_settings():
    """最小化 mock Settings。"""
    settings = SimpleNamespace()
    return settings


@pytest.fixture()
def mock_event_bus():
    """Mock EventBus，记录 publish 调用。"""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture()
def mock_openai_service():
    """Mock OpenAI 服务。"""
    svc = AsyncMock()
    svc.is_configured.return_value = False
    return svc


@pytest.fixture()
def debate_service(mock_settings, mock_event_bus, mock_openai_service):
    """创建一个 DebateService 实例，外部依赖全部 mock。"""
    svc = DebateService.__new__(DebateService)
    svc.settings = mock_settings
    svc.event_bus = mock_event_bus
    svc.openai_service = mock_openai_service
    svc.agent_registry = None
    return svc


# ---------------------------------------------------------------------------
# 自动分歧检测（auto_detect_disagreement）
# ---------------------------------------------------------------------------


class TestAutoDetectDisagreement:
    """测试自动分歧检测逻辑。"""

    def test_no_disagreement_when_single_agent(self):
        """只有一个 agent 评估时不应触发辩论。"""
        assessments = [
            {"role": "advocate", "position": "SUPPORT", "confidence": 0.8, "arguments": []},
        ]
        result = DebateTriggerMixin.auto_detect_disagreement(assessments)
        assert result["should_trigger"] is False
        assert result["trigger_reasons"] == []

    def test_no_disagreement_when_agreement(self):
        """所有 agent 立场一致且置信度接近时不应触发辩论。"""
        assessments = [
            {"role": "advocate", "position": "SUPPORT", "confidence": 0.8, "arguments": []},
            {"role": "challenger", "position": "SUPPORT", "confidence": 0.75, "arguments": []},
        ]
        result = DebateTriggerMixin.auto_detect_disagreement(assessments)
        assert result["should_trigger"] is False

    def test_detects_confidence_spread(self):
        """置信度差异超过阈值时应触发辩论。"""
        assessments = [
            {"role": "advocate", "position": "SUPPORT", "confidence": 0.9, "arguments": []},
            {"role": "challenger", "position": "CONDITIONAL", "confidence": 0.4, "arguments": []},
        ]
        result = DebateTriggerMixin.auto_detect_disagreement(assessments, confidence_threshold=0.30)
        assert result["should_trigger"] is True
        assert result["confidence_spread"] == pytest.approx(0.5)
        assert len(result["trigger_reasons"]) > 0

    def test_detects_position_conflict(self):
        """SUPPORT vs OPPOSE 立场对立时应触发辩论。"""
        assessments = [
            {"role": "advocate", "position": "SUPPORT", "confidence": 0.7, "arguments": []},
            {"role": "challenger", "position": "OPPOSE", "confidence": 0.6, "arguments": []},
        ]
        result = DebateTriggerMixin.auto_detect_disagreement(assessments, confidence_threshold=0.5)
        assert result["should_trigger"] is True
        assert len(result["position_conflicts"]) == 1
        assert result["position_conflicts"][0]["support"] == ["advocate"]
        assert result["position_conflicts"][0]["oppose"] == ["challenger"]

    def test_disagreement_details_populated(self, debate_service):
        """分歧详情应包含各 agent 的立场和置信度。"""
        assessments = [
            {
                "role": "advocate",
                "position": "SUPPORT",
                "confidence": 0.9,
                "arguments": [{"claim": "Revenue will grow", "reasoning": "Market trends"}],
            },
            {
                "role": "challenger",
                "position": "OPPOSE",
                "confidence": 0.3,
                "arguments": [{"claim": "Market is saturated", "reasoning": "Competition"}],
            },
        ]
        result = DebateTriggerMixin.auto_detect_disagreement(assessments)
        assert result["should_trigger"] is True
        details = result["disagreement_details"]
        assert len(details["agent_positions"]) == 2
        assert details["agent_positions"][0]["role"] == "advocate"
        assert details["agent_positions"][0]["key_argument"] == "Revenue will grow"

    def test_empty_assessments(self):
        """空评估列表不应触发辩论。"""
        result = DebateTriggerMixin.auto_detect_disagreement([])
        assert result["should_trigger"] is False
        assert result["confidence_spread"] == 0.0


# ---------------------------------------------------------------------------
# 辩论裁决生成（_generate_adjudication）
# ---------------------------------------------------------------------------


class TestDebateAdjudication:
    """测试辩论裁决逻辑。"""

    def _make_service(self):
        """创建一个纯裁决 mixin 实例。"""
        svc = DebateAdjudicationMixin()
        return svc

    def test_accepted_when_support_high(self):
        """支持方置信度显著高于挑战方时应 ACCEPTED。"""
        svc = self._make_service()
        verdict = svc._generate_adjudication(
            support_confidence=0.85,
            challenge_confidence=0.5,
            arbitrator_rounds=[],
        )
        assert verdict == "ACCEPTED"

    def test_rejected_when_challenge_high(self):
        """挑战方置信度显著高于支持方时应 REJECTED。"""
        svc = self._make_service()
        verdict = svc._generate_adjudication(
            support_confidence=0.4,
            challenge_confidence=0.8,
            arbitrator_rounds=[],
        )
        assert verdict == "REJECTED"

    def test_conditional_when_close(self):
        """双方置信度接近时应 CONDITIONAL。"""
        svc = self._make_service()
        verdict = svc._generate_adjudication(
            support_confidence=0.6,
            challenge_confidence=0.55,
            arbitrator_rounds=[],
        )
        assert verdict == "CONDITIONAL"

    def test_arbitrator_support_overrides(self):
        """仲裁者 SUPPORT 立场应覆盖默认判定。"""
        svc = self._make_service()
        verdict = svc._generate_adjudication(
            support_confidence=0.5,
            challenge_confidence=0.5,
            arbitrator_rounds=[{"position": "SUPPORT", "confidence": 0.7}],
        )
        assert verdict == "ACCEPTED"

    def test_arbitrator_oppose_overrides(self):
        """仲裁者 OPPOSE 立场应覆盖默认判定。"""
        svc = self._make_service()
        verdict = svc._generate_adjudication(
            support_confidence=0.8,
            challenge_confidence=0.3,
            arbitrator_rounds=[{"position": "OPPOSE", "confidence": 0.6}],
        )
        assert verdict == "REJECTED"


# ---------------------------------------------------------------------------
# 辩论结果汇总（_build_assessment_from_llm_rounds）
# ---------------------------------------------------------------------------


class TestDebateAssessment:
    """测试辩论结果汇总。"""

    def _make_service(self):
        """创建一个带辅助方法的 mixin 实例。"""
        svc = DebateAdjudicationMixin()
        # mock _generate_recommendations 等辅助方法
        svc._generate_recommendations = lambda **kw: [{"title": "test rec"}]
        svc._generate_risk_factors = lambda **kw: ["test risk"]
        svc._generate_alternative_scenarios = lambda **kw: [{"label": "alt"}]
        svc._generate_conclusion_summary = lambda **kw: "test conclusion"
        return svc

    def _make_payload(self):
        """创建 mock DebateTriggerRequest。"""
        payload = SimpleNamespace()
        payload.context_lines = ["test context"]
        payload.topic = "Test topic"
        payload.trigger_type = "manual"
        return payload

    def test_llm_rounds_accepted_verdict(self):
        """advocate 置信度高时应判定 ACCEPTED。"""
        svc = self._make_service()
        rounds = [
            {
                "round_number": 1,
                "role": "advocate",
                "position": "SUPPORT",
                "confidence": 0.9,
                "arguments": [{"claim": "Growth is strong", "evidence_ids": [], "reasoning": "Data shows it", "strength": "STRONG"}],
                "rebuttals": [],
                "concessions": [],
            },
            {
                "round_number": 1,
                "role": "challenger",
                "position": "OPPOSE",
                "confidence": 0.3,
                "arguments": [{"claim": "Risk exists", "evidence_ids": [], "reasoning": "Market uncertain", "strength": "WEAK"}],
                "rebuttals": [],
                "concessions": [],
            },
        ]
        payload = self._make_payload()
        assessment = svc._build_assessment_from_llm_rounds(
            rounds, evidence_ids=["ev1", "ev2"], payload=payload,
        )
        assert isinstance(assessment, DebateAssessment)
        assert assessment.verdict == "ACCEPTED"
        assert assessment.support_confidence == 0.9
        assert assessment.challenge_confidence == 0.3
        assert len(assessment.winning_arguments) > 0

    def test_llm_rounds_rejected_verdict(self):
        """challenger 置信度高时应判定 REJECTED。"""
        svc = self._make_service()
        rounds = [
            {
                "round_number": 1,
                "role": "advocate",
                "position": "SUPPORT",
                "confidence": 0.3,
                "arguments": [{"claim": "Maybe ok", "evidence_ids": [], "reasoning": "Unclear", "strength": "WEAK"}],
                "rebuttals": [],
                "concessions": [],
            },
            {
                "round_number": 1,
                "role": "challenger",
                "position": "OPPOSE",
                "confidence": 0.85,
                "arguments": [{"claim": "Definitely risky", "evidence_ids": [], "reasoning": "Data is bad", "strength": "STRONG"}],
                "rebuttals": [],
                "concessions": [],
            },
        ]
        payload = self._make_payload()
        assessment = svc._build_assessment_from_llm_rounds(
            rounds, evidence_ids=["ev1"], payload=payload,
        )
        assert assessment.verdict == "REJECTED"
        # minority_opinion 取自 challenger_rounds（赢方），实际来自首轮挑战论点
        assert assessment.minority_opinion == "Definitely risky"

    def test_llm_rounds_conditional_verdict(self):
        """双方置信度接近时应判定 CONDITIONAL。"""
        svc = self._make_service()
        rounds = [
            {
                "round_number": 1,
                "role": "advocate",
                "position": "SUPPORT",
                "confidence": 0.65,
                "arguments": [{"claim": "Some support", "evidence_ids": [], "reasoning": "Partial data", "strength": "MODERATE"}],
                "rebuttals": [],
                "concessions": [],
            },
            {
                "round_number": 1,
                "role": "challenger",
                "position": "CONDITIONAL",
                "confidence": 0.6,
                "arguments": [{"claim": "Some doubt", "evidence_ids": [], "reasoning": "Gaps exist", "strength": "MODERATE"}],
                "rebuttals": [],
                "concessions": [],
            },
        ]
        payload = self._make_payload()
        assessment = svc._build_assessment_from_llm_rounds(
            rounds, evidence_ids=["ev1"], payload=payload,
        )
        assert assessment.verdict == "CONDITIONAL"
        assert assessment.conditions is not None

    def test_assessment_with_arbitrator(self):
        """有仲裁者时应使用仲裁者判定。"""
        svc = self._make_service()
        rounds = [
            {
                "round_number": 1, "role": "advocate", "position": "SUPPORT",
                "confidence": 0.5, "arguments": [], "rebuttals": [], "concessions": [],
            },
            {
                "round_number": 1, "role": "challenger", "position": "OPPOSE",
                "confidence": 0.5, "arguments": [], "rebuttals": [], "concessions": [],
            },
            {
                "round_number": 2, "role": "arbitrator", "position": "SUPPORT",
                "confidence": 0.8, "arguments": [{"claim": "Support wins", "evidence_ids": [], "reasoning": "Evidence is clear", "strength": "STRONG"}],
                "rebuttals": [], "concessions": [],
            },
        ]
        payload = self._make_payload()
        assessment = svc._build_assessment_from_llm_rounds(
            rounds, evidence_ids=["ev1"], payload=payload,
        )
        assert assessment.verdict == "ACCEPTED"

    def test_assessment_context_payload(self):
        """结果应包含 context_payload。"""
        svc = self._make_service()
        rounds = [
            {
                "round_number": 1, "role": "advocate", "position": "SUPPORT",
                "confidence": 0.8, "arguments": [], "rebuttals": [], "concessions": [],
            },
        ]
        payload = self._make_payload()
        assessment = svc._build_assessment_from_llm_rounds(
            rounds, evidence_ids=["ev1"], payload=payload,
            run_id="run-123", report_id="rep-456",
        )
        assert assessment.context_payload["run_id"] == "run-123"
        assert assessment.context_payload["report_id"] == "rep-456"
        assert assessment.context_payload["debate_method"] == "llm"

    def test_assessment_has_recommendations_and_risks(self):
        """结果应包含建议和风险因素。"""
        svc = self._make_service()
        rounds = [
            {
                "round_number": 1, "role": "advocate", "position": "SUPPORT",
                "confidence": 0.8, "arguments": [], "rebuttals": [], "concessions": [],
            },
        ]
        payload = self._make_payload()
        assessment = svc._build_assessment_from_llm_rounds(
            rounds, evidence_ids=["ev1"], payload=payload,
        )
        assert len(assessment.recommendations) > 0
        assert len(assessment.risk_factors) > 0
        assert assessment.conclusion_summary == "test conclusion"


# ---------------------------------------------------------------------------
# 辩论结果汇总 - 多轮次
# ---------------------------------------------------------------------------


class TestDebateMultiRound:
    """测试多轮辩论结果。"""

    def _make_service(self):
        svc = DebateAdjudicationMixin()
        svc._generate_recommendations = lambda **kw: []
        svc._generate_risk_factors = lambda **kw: []
        svc._generate_alternative_scenarios = lambda **kw: []
        svc._generate_conclusion_summary = lambda **kw: "summary"
        return svc

    def test_multi_round_aggregates_confidence(self):
        """多轮辩论应取各阵营最高置信度。"""
        svc = self._make_service()
        rounds = [
            {
                "round_number": 1, "role": "advocate", "position": "SUPPORT",
                "confidence": 0.6, "arguments": [{"claim": "arg1", "evidence_ids": [], "reasoning": "", "strength": "MODERATE"}],
                "rebuttals": [], "concessions": [],
            },
            {
                "round_number": 2, "role": "advocate", "position": "SUPPORT",
                "confidence": 0.85, "arguments": [{"claim": "arg2", "evidence_ids": [], "reasoning": "", "strength": "STRONG"}],
                "rebuttals": [], "concessions": [],
            },
            {
                "round_number": 1, "role": "challenger", "position": "OPPOSE",
                "confidence": 0.4, "arguments": [{"claim": "challenge1", "evidence_ids": [], "reasoning": "", "strength": "WEAK"}],
                "rebuttals": [], "concessions": [],
            },
        ]
        payload = SimpleNamespace(context_lines=[], topic="Test", trigger_type="manual")
        assessment = svc._build_assessment_from_llm_rounds(
            rounds, evidence_ids=["ev1"], payload=payload,
        )
        # advocate 最高 0.85，challenger 最高 0.4
        assert assessment.support_confidence == 0.85
        assert assessment.challenge_confidence == 0.4
        assert assessment.verdict == "ACCEPTED"

    def test_fallback_rounds_with_no_arguments(self):
        """无 argument 的轮次应有默认 winning_arguments。"""
        svc = self._make_service()
        rounds = [
            {
                "round_number": 1, "role": "advocate", "position": "SUPPORT",
                "confidence": 0.7, "arguments": [], "rebuttals": [], "concessions": [],
            },
        ]
        payload = SimpleNamespace(context_lines=[], topic="T", trigger_type="manual")
        assessment = svc._build_assessment_from_llm_rounds(
            rounds, evidence_ids=["ev1"], payload=payload,
        )
        assert len(assessment.winning_arguments) >= 1


# ---------------------------------------------------------------------------
# 辅助方法
# ---------------------------------------------------------------------------


class TestDebateHelpers:
    """测试辩论服务辅助方法。"""

    def test_round_key_arguments(self, debate_service):
        """_round_key_arguments 应提取关键论点。"""
        round_payload = {
            "arguments": [
                {"claim": "Point A"},
                {"claim": "Point B"},
                {"claim": "Point C"},
                {"claim": "Point D"},
            ],
        }
        result = debate_service._round_key_arguments(round_payload)
        assert len(result) == 3  # 最多取 3 个
        assert "Point A" in result

    def test_round_key_arguments_empty(self, debate_service):
        """无 arguments 时应返回空列表。"""
        round_payload = {"arguments": []}
        result = debate_service._round_key_arguments(round_payload)
        assert result == []

    def test_round_complete_payload(self, debate_service):
        """_round_complete_payload 应返回正确格式。"""
        round_payload = {
            "round_number": 1,
            "role": "advocate",
            "position": "SUPPORT",
            "confidence": 0.8,
            "arguments": [{"claim": "Arg1"}],
        }
        result = debate_service._round_complete_payload(round_payload)
        assert result["round_number"] == 1
        assert result["role"] == "advocate"
        assert result["position"] == "SUPPORT"
        assert result["confidence"] == 0.8
        assert "Arg1" in result["key_arguments"]
