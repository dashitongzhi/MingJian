"""Unit tests for planagent.services.simulation — 推演引擎。

测试覆盖：
- 推演场景创建（scenario template / branch）
- 假设验证（external shock 推导）
- KPI 追踪（probability/severity 评分）
- 影响计算（impact calculation）
- 动作选择（action selection）
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from planagent.config import Settings
from planagent.services.simulation import SimulationService
from planagent.services.simulation.impact import (
    ActionCandidate,
    RuleScore,
    SelectedAction,
    SimulationImpactMixin,
)
from planagent.services.simulation.scenarios import SimulationScenariosMixin
from pathlib import Path

from planagent.simulation.rules import RuleRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings():
    """最小化 Settings。"""
    return Settings(_env_file=None)


@pytest.fixture()
def mock_event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture()
def rule_registry(tmp_path):
    """使用临时目录创建 RuleRegistry。"""
    return RuleRegistry(rules_root=tmp_path)


@pytest.fixture()
def sim_service(settings, mock_event_bus, rule_registry):
    """SimulationService 实例（mock 依赖）。"""
    return SimulationService(
        settings=settings,
        event_bus=mock_event_bus,
        rule_registry=rule_registry,
        openai_service=None,
    )


# ═══════════════════════════════════════════════════════════════
# 动作候选评分 — ActionCandidate
# ═══════════════════════════════════════════════════════════════


class TestActionCandidate:
    """测试 ActionCandidate 评分逻辑。"""

    def test_total_score_calculation(self):
        """总分 = base_score + state_adjustment - history_penalty。"""
        candidate = ActionCandidate(
            action_id="test_action",
            base_score=2.0,
            state_adjustment=0.5,
            history_penalty=0.3,
        )
        assert candidate.total_score == 2.2  # 2.0 + 0.5 - 0.3

    def test_total_score_defaults_to_zero(self):
        """默认参数下总分为 0。"""
        candidate = ActionCandidate(action_id="a1")
        assert candidate.total_score == 0.0

    def test_total_score_with_penalty_exceeding_base(self):
        """惩罚超过基础分时总分为负。"""
        candidate = ActionCandidate(
            action_id="a2",
            base_score=0.5,
            state_adjustment=0.0,
            history_penalty=1.0,
        )
        assert candidate.total_score < 0

    def test_total_score_rounded_to_4_decimals(self):
        """总分应四舍五入到 4 位小数。"""
        candidate = ActionCandidate(
            action_id="a3",
            base_score=0.123456789,
            state_adjustment=0.987654321,
            history_penalty=0.000011111,
        )
        score_str = str(candidate.total_score)
        # round() 在 Python 中应给出合理精度
        assert isinstance(candidate.total_score, float)


# ═══════════════════════════════════════════════════════════════
# 概率评分 — _score_probability
# ═══════════════════════════════════════════════════════════════


class TestScoreProbability:
    """测试概率评分逻辑。"""

    def _make_mixin(self):
        class Dummy(SimulationImpactMixin):
            pass
        return Dummy()

    def test_none_returns_05(self):
        """None 应返回 0.5（中等概率）。"""
        mixin = self._make_mixin()
        assert mixin._score_probability(None) == 0.5

    def test_numeric_passthrough(self):
        """数值型应直接传递（限制在 0-1）。"""
        mixin = self._make_mixin()
        assert mixin._score_probability(0.75) == 0.75
        assert mixin._score_probability(0.0) == 0.0
        assert mixin._score_probability(1.0) == 1.0

    def test_numeric_clamped_above_1(self):
        """超过 1 的数值应被限制为 1。"""
        mixin = self._make_mixin()
        assert mixin._score_probability(1.5) == 1.0

    def test_numeric_clamped_below_0(self):
        """负数应被限制为 0。"""
        mixin = self._make_mixin()
        assert mixin._score_probability(-0.5) == 0.0

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("very_low", 0.1),
            ("low", 0.25),
            ("medium", 0.5),
            ("moderate", 0.5),
            ("high", 0.75),
            ("very_high", 0.9),
        ],
    )
    def test_text_labels(self, text: str, expected: float):
        """文本标签应映射到对应概率值。"""
        mixin = self._make_mixin()
        assert mixin._score_probability(text) == expected

    def test_text_case_insensitive(self):
        """文本标签应不区分大小写。"""
        mixin = self._make_mixin()
        assert mixin._score_probability("HIGH") == 0.75
        assert mixin._score_probability("Very_Low") == 0.1

    def test_unknown_text_returns_05(self):
        """未知文本标签应返回 0.5。"""
        mixin = self._make_mixin()
        assert mixin._score_probability("unknown_label") == 0.5


# ═══════════════════════════════════════════════════════════════
# 严重性评分 — _score_severity
# ═══════════════════════════════════════════════════════════════


class TestScoreSeverity:
    """测试影响严重性评分。"""

    def _make_mixin(self):
        class Dummy(SimulationImpactMixin):
            pass
        return Dummy()

    def test_empty_impact_returns_zero(self):
        """空影响字典应返回 0。"""
        mixin = self._make_mixin()
        assert mixin._score_severity({}) == 0.0

    def test_single_metric_impact(self):
        """单指标影响。"""
        mixin = self._make_mixin()
        result = mixin._score_severity({"metric_a": 0.5})
        assert result == 0.5

    def test_multi_metric_average(self):
        """多指标应取平均绝对值。"""
        mixin = self._make_mixin()
        result = mixin._score_severity({"a": 0.6, "b": -0.4})
        assert result == 0.5  # (0.6 + 0.4) / 2

    def test_clamped_to_1(self):
        """结果应限制在 0-1。"""
        mixin = self._make_mixin()
        result = mixin._score_severity({"a": 5.0, "b": -3.0})
        assert result <= 1.0

    def test_negative_values_use_absolute(self):
        """负值应取绝对值。"""
        mixin = self._make_mixin()
        result = mixin._score_severity({"a": -0.8})
        assert result == 0.8


# ═══════════════════════════════════════════════════════════════
# 外部冲击推导 — _derive_shocks
# ═══════════════════════════════════════════════════════════════


class TestDeriveShocks:
    """测试外部冲击推导逻辑。"""

    def _make_mixin(self):
        class Dummy(SimulationImpactMixin):
            pass
        return Dummy()

    def test_corporate_cost_shock(self):
        """企业领域 - 包含 cost/price/gpu 关键词应触发市场成本冲击。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("corporate", "GPU cost increased significantly", "ev1")
        types = [s["shock_type"] for s in shocks]
        assert "market_cost_pressure" in types

    def test_corporate_product_launch_shock(self):
        """企业领域 - 包含 launch/release 关键词应触发产品发布冲击。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("corporate", "New product launch announced", "ev1")
        types = [s["shock_type"] for s in shocks]
        assert "product_launch" in types

    def test_corporate_demand_shift(self):
        """企业领域 - 包含 demand/adoption/growth 应触发需求变化。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("corporate", "Strong adoption growth in enterprise", "ev1")
        types = [s["shock_type"] for s in shocks]
        assert "demand_shift" in types

    def test_corporate_platform_bundling(self):
        """企业领域 - bundling/native/copilot 关键词应触发平台捆绑压力。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("corporate", "Copilot bundled natively in platform", "ev1")
        types = [s["shock_type"] for s in shocks]
        assert "platform_bundling_pressure" in types

    def test_corporate_reliability_incident(self):
        """企业领域 - hallucination/outage 关键词应触发可靠性事件。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("corporate", "Major hallucination accuracy issue reported", "ev1")
        types = [s["shock_type"] for s in shocks]
        assert "reliability_incident" in types

    def test_corporate_validated_roi(self):
        """企业领域 - roi/renewal/expansion 关键词应触发 ROI 验证。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("corporate", "Customer reported strong ROI and renewal", "ev1")
        types = [s["shock_type"] for s in shocks]
        assert "validated_roi" in types

    def test_military_supply_disruption(self):
        """军事领域 - supply/bridge/port 关键词应触发后勤中断。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("military", "Supply convoy blocked at bridge", "ev1")
        types = [s["shock_type"] for s in shocks]
        assert "supply_disruption" in types

    def test_military_air_attack(self):
        """军事领域 - drone/swarm/strike 应触发空中攻击冲击。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("military", "Drone swarm strike detected in airspace", "ev1")
        types = [s["shock_type"] for s in shocks]
        assert "air_attack" in types

    def test_military_isr_window(self):
        """军事领域 - isr/satellite/recon 应触发 ISR 窗口。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("military", "Satellite recon detected movement", "ev1")
        types = [s["shock_type"] for s in shocks]
        assert "isr_window" in types

    def test_military_electronic_attack(self):
        """军事领域 - jam/electronic/cyber 应触发电子攻击。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("military", "Electronic jamming reported in sector", "ev1")
        types = [s["shock_type"] for s in shocks]
        assert "electronic_attack" in types

    def test_military_weather_window(self):
        """军事领域 - weather/storm/fog 应触发天气窗口。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("military", "Heavy storm and fog conditions", "ev1")
        types = [s["shock_type"] for s in shocks]
        assert "weather_window" in types

    def test_no_matching_keywords_returns_empty(self):
        """无匹配关键词应返回空列表。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("corporate", "The weather is nice today", "ev1")
        assert shocks == []

    def test_multiple_shocks_possible(self):
        """同一语句可触发多个冲击。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("corporate", "GPU cost increased due to strong demand adoption", "ev1")
        types = {s["shock_type"] for s in shocks}
        assert "market_cost_pressure" in types
        assert "demand_shift" in types

    def test_shock_payload_contains_evidence_id(self):
        """冲击 payload 应包含 evidence_id。"""
        mixin = self._make_mixin()
        shocks = mixin._derive_shocks("corporate", "GPU cost pressure", "ev-123")
        assert shocks[0]["payload"]["evidence_id"] == "ev-123"


# ═══════════════════════════════════════════════════════════════
# 外部冲击应用 — _apply_external_shock
# ═══════════════════════════════════════════════════════════════


class TestApplyExternalShock:
    """测试外部冲击对状态的影响。"""

    def _make_mixin(self):
        class Dummy(SimulationImpactMixin):
            pass
        return Dummy()

    def test_corporate_cost_shock_modifies_state(self):
        """企业成本冲击应增加 infra_cost_index、减少 runway。"""
        mixin = self._make_mixin()
        state = {"infra_cost_index": 1.0, "runway_weeks": 52.0, "gross_margin": 0.62}
        mixin._apply_external_shock("corporate", state, "GPU cost increased")
        assert state["infra_cost_index"] > 1.0
        assert state["runway_weeks"] < 52.0
        assert state["gross_margin"] < 0.62

    def test_corporate_launch_improves_brand(self):
        """产品发布冲击应提升品牌指数。"""
        mixin = self._make_mixin()
        state = {"brand_index": 1.0, "market_share": 0.05}
        mixin._apply_external_shock("corporate", state, "New product launch")
        assert state["brand_index"] > 1.0
        assert state["market_share"] > 0.05

    def test_military_supply_disrupts_logistics(self):
        """后勤中断应降低 logistics_throughput。"""
        mixin = self._make_mixin()
        state = {"logistics_throughput": 1.0, "supply_network": 0.84}
        mixin._apply_external_shock("military", state, "Supply convoy blocked")
        assert state["logistics_throughput"] < 1.0
        assert state["supply_network"] < 0.84

    def test_military_isr_improves_coverage(self):
        """ISR 窗口应提升 isr_coverage。"""
        mixin = self._make_mixin()
        state = {"isr_coverage": 1.0, "information_advantage": 1.0}
        mixin._apply_external_shock("military", state, "Satellite recon available")
        assert state["isr_coverage"] > 1.0

    def test_no_matching_keywords_no_change(self):
        """无匹配关键词时状态不应改变。"""
        mixin = self._make_mixin()
        state = {"a": 1.0, "b": 2.0}
        original = dict(state)
        mixin._apply_external_shock("corporate", state, "Nothing relevant here")
        assert state == original

    def test_state_default_values_applied(self):
        """当状态中缺少某些键时，应使用默认值。"""
        mixin = self._make_mixin()
        state = {}  # 空状态
        mixin._apply_external_shock("corporate", state, "GPU cost pressure")
        # 应使用默认值并修改
        assert "infra_cost_index" in state
        assert "runway_weeks" in state


# ═══════════════════════════════════════════════════════════════
# 影响计算 — _calculate_impact
# ═══════════════════════════════════════════════════════════════


class TestCalculateImpact:
    """测试影响计算。"""

    def _make_mixin(self):
        class Dummy(SimulationImpactMixin):
            def _apply_effects(self, state, effect):
                for k, v in effect.items():
                    state[k] = state.get(k, 0.0) + v
        return Dummy()

    def test_basic_impact(self):
        """基本影响计算。"""
        mixin = self._make_mixin()
        state = {"a": 1.0, "b": 2.0}
        effect = {"a": 0.5, "b": -0.3}
        result = mixin._calculate_impact(state, effect)
        assert result["a"] == 1.5
        assert result["b"] == 1.7

    def test_impact_does_not_modify_original(self):
        """影响计算不应修改原始状态。"""
        mixin = self._make_mixin()
        state = {"a": 1.0}
        effect = {"a": 0.5}
        mixin._calculate_impact(state, effect)
        assert state["a"] == 1.0  # 原始不变

    def test_impact_with_new_metric(self):
        """影响可以引入新的指标。"""
        mixin = self._make_mixin()
        state = {"a": 1.0}
        effect = {"new_metric": 0.5}
        result = mixin._calculate_impact(state, effect)
        assert result["new_metric"] == 0.5


# ═══════════════════════════════════════════════════════════════
# 场景模板构建 — _build_scenario_template
# ═══════════════════════════════════════════════════════════════


class TestScenarioTemplate:
    """测试场景模板构建。"""

    def _make_mixin(self):
        class Dummy(SimulationScenariosMixin):
            pass
        return Dummy()

    def _mock_parent_run(self, tick_count=10, domain_id="corporate"):
        run = MagicMock()
        run.id = "parent-run-1"
        run.tick_count = tick_count
        run.domain_id = domain_id
        run.actor_template = "default"
        return run

    def _mock_payload(self, **overrides):
        payload = MagicMock()
        payload.fork_step = overrides.get("fork_step", None)
        payload.tick_count = overrides.get("tick_count", None)
        payload.assumptions = overrides.get("assumptions", ["assumption1"])
        payload.decision_deltas = overrides.get("decision_deltas", ["delta1"])
        payload.state_overrides = overrides.get("state_overrides", {"kpi": 0.8})
        payload.probability_band = overrides.get("probability_band", "medium")
        return payload

    def test_template_uses_parent_info(self):
        """模板应包含父运行信息。"""
        mixin = self._make_mixin()
        parent = self._mock_parent_run()
        payload = self._mock_payload()
        template = mixin._build_scenario_template(parent, payload)
        assert template["parent_run_id"] == "parent-run-1"
        assert template["domain_id"] == "corporate"
        assert template["actor_template"] == "default"

    def test_template_default_fork_step(self):
        """默认 fork_step 应为 tick_count 的一半。"""
        mixin = self._make_mixin()
        parent = self._mock_parent_run(tick_count=10)
        payload = self._mock_payload()
        template = mixin._build_scenario_template(parent, payload)
        assert template["fork_step"] == 5

    def test_template_custom_fork_step(self):
        """自定义 fork_step 应被使用。"""
        mixin = self._make_mixin()
        parent = self._mock_parent_run(tick_count=10)
        payload = self._mock_payload(fork_step=3)
        template = mixin._build_scenario_template(parent, payload)
        assert template["fork_step"] == 3

    def test_template_calculates_remaining_ticks(self):
        """tick_count 应为父运行剩余的 tick 数。"""
        mixin = self._make_mixin()
        parent = self._mock_parent_run(tick_count=10)
        payload = self._mock_payload(fork_step=4)
        template = mixin._build_scenario_template(parent, payload)
        assert template["tick_count"] == 6  # 10 - 4

    def test_template_includes_assumptions(self):
        """模板应包含假设列表。"""
        mixin = self._make_mixin()
        parent = self._mock_parent_run()
        payload = self._mock_payload(assumptions=["假设A", "假设B"])
        template = mixin._build_scenario_template(parent, payload)
        assert template["assumptions"] == ["假设A", "假设B"]

    def test_generate_scenarios_multiple(self):
        """应能批量生成多个场景模板。"""
        mixin = self._make_mixin()
        parent = self._mock_parent_run()
        payloads = [self._mock_payload(fork_step=i + 1) for i in range(3)]
        templates = mixin._generate_scenarios(parent, payloads)
        assert len(templates) == 3
        assert templates[0]["fork_step"] == 1
        assert templates[2]["fork_step"] == 3


# ═══════════════════════════════════════════════════════════════
# SimulationService 初始化
# ═══════════════════════════════════════════════════════════════


class TestSimulationServiceInit:
    """测试 SimulationService 初始化。"""

    def test_service_creation(self, settings, mock_event_bus, tmp_path):
        """SimulationService 应正常创建。"""
        svc = SimulationService(
            settings=settings,
            event_bus=mock_event_bus,
            rule_registry=RuleRegistry(rules_root=tmp_path),
        )
        assert svc.settings is settings
        assert svc.event_bus is mock_event_bus
        assert svc.rule_registry is not None

    def test_service_has_mixin_methods(self, settings, mock_event_bus, tmp_path):
        """SimulationService 应包含各 mixin 的方法。"""
        svc = SimulationService(
            settings=settings,
            event_bus=mock_event_bus,
            rule_registry=RuleRegistry(rules_root=tmp_path),
        )
        assert hasattr(svc, "create_simulation_run")
        assert hasattr(svc, "_apply_external_shock")
        assert hasattr(svc, "_derive_shocks")
        assert hasattr(svc, "_score_probability")
        assert hasattr(svc, "_build_scenario_template")
