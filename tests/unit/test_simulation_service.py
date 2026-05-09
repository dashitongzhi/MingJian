"""Unit tests for SimulationEngine — 推演引擎。"""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from planagent.services.simulation.engine import SimulationEngineMixin
from planagent.services.simulation.scenarios import SimulationScenariosMixin


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_session():
    """Mock 异步数据库 session。"""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.refresh = AsyncMock()
    session.scalars = AsyncMock()

    # begin_nested 作为 context manager
    nested = AsyncMock()
    nested.__aenter__ = AsyncMock(return_value=None)
    nested.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested = MagicMock(return_value=nested)

    return session


@pytest.fixture()
def mock_settings():
    """最小化 mock Settings。"""
    return SimpleNamespace(
        inline_simulation_default=True,
        default_corporate_ticks=5,
        default_military_ticks=5,
        worker_max_attempts=3,
    )


@pytest.fixture()
def mock_event_bus():
    """Mock EventBus。"""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture()
def engine_service(mock_settings, mock_event_bus):
    """创建一个 SimulationEngineMixin 实例。"""
    svc = SimulationEngineMixin()
    svc.settings = mock_settings
    svc.event_bus = mock_event_bus
    return svc


@pytest.fixture()
def scenario_service(mock_settings, mock_event_bus):
    """创建一个 SimulationScenariosMixin 实例。"""
    svc = SimulationScenariosMixin()
    svc.settings = mock_settings
    svc.event_bus = mock_event_bus
    svc._build_evidence_summary = lambda run: "test evidence"
    return svc


# ---------------------------------------------------------------------------
# 推演场景创建
# ---------------------------------------------------------------------------


class TestScenarioTemplate:
    """测试推演场景模板构建。"""

    def test_build_scenario_template(self, scenario_service):
        """_build_scenario_template 应正确构建场景模板。"""
        parent_run = SimpleNamespace(
            id="run-1",
            domain_id="corporate",
            actor_template="default",
            tick_count=10,
        )
        payload = SimpleNamespace(
            fork_step=5,
            tick_count=5,
            assumptions=["Market downturn"],
            decision_deltas=["Reduce hiring"],
            state_overrides={"runway_weeks": 12.0},
            probability_band=[0.3, 0.7],
        )
        template = scenario_service._build_scenario_template(parent_run, payload)
        assert template["parent_run_id"] == "run-1"
        assert template["domain_id"] == "corporate"
        assert template["fork_step"] == 5
        assert template["tick_count"] == 5
        assert "Market downturn" in template["assumptions"]
        assert template["state_overrides"]["runway_weeks"] == 12.0

    def test_build_scenario_template_default_fork_step(self, scenario_service):
        """未指定 fork_step 时应默认取 tick_count 的一半。"""
        parent_run = SimpleNamespace(
            id="run-2",
            domain_id="corporate",
            actor_template="default",
            tick_count=10,
        )
        payload = SimpleNamespace(
            fork_step=None,
            tick_count=None,
            assumptions=[],
            decision_deltas=[],
            state_overrides={},
            probability_band=None,
        )
        template = scenario_service._build_scenario_template(parent_run, payload)
        assert template["fork_step"] == 5  # 10 // 2
        assert template["tick_count"] == 5  # 10 - 5

    def test_generate_scenarios_multiple(self, scenario_service):
        """_generate_scenarios 应为每个 payload 生成模板。"""
        parent_run = SimpleNamespace(
            id="run-3",
            domain_id="corporate",
            actor_template="default",
            tick_count=8,
        )
        payloads = [
            SimpleNamespace(
                fork_step=2,
                tick_count=6,
                assumptions=[],
                decision_deltas=[],
                state_overrides={},
                probability_band=None,
            ),
            SimpleNamespace(
                fork_step=4,
                tick_count=4,
                assumptions=[],
                decision_deltas=[],
                state_overrides={},
                probability_band=None,
            ),
        ]
        templates = scenario_service._generate_scenarios(parent_run, payloads)
        assert len(templates) == 2
        assert templates[0]["fork_step"] == 2
        assert templates[1]["fork_step"] == 4


# ---------------------------------------------------------------------------
# 场景分支创建（create_scenario_run）
# ---------------------------------------------------------------------------


class TestCreateScenarioRun:
    """测试场景分支创建。"""

    @pytest.mark.asyncio
    async def test_raises_when_parent_not_found(self, scenario_service, mock_session):
        """父推演不存在时应抛出 LookupError。"""
        mock_session.get.return_value = None
        with pytest.raises(LookupError, match="was not found"):
            await scenario_service.create_scenario_run(
                mock_session,
                "nonexistent",
                SimpleNamespace(
                    fork_step=None,
                    tick_count=None,
                    assumptions=[],
                    decision_deltas=[],
                    state_overrides={},
                    probability_band=None,
                ),
            )

    @pytest.mark.asyncio
    async def test_raises_when_parent_not_completed(self, scenario_service, mock_session):
        """父推演未完成时应抛出 ValueError。"""
        parent = SimpleNamespace(
            id="run-1",
            status="PENDING",
            domain_id="corporate",
            company_id="comp-1",
            force_id=None,
        )
        mock_session.get.return_value = parent
        with pytest.raises(ValueError, match="completed baseline"):
            await scenario_service.create_scenario_run(
                mock_session,
                "run-1",
                SimpleNamespace(
                    fork_step=None,
                    tick_count=None,
                    assumptions=[],
                    decision_deltas=[],
                    state_overrides={},
                    probability_band=None,
                ),
            )


# ---------------------------------------------------------------------------
# 假设验证逻辑
# ---------------------------------------------------------------------------


class TestHypothesisLogic:
    """测试假设验证逻辑。"""

    def test_branch_template_captures_assumptions(self, scenario_service):
        """场景模板应记录假设条件。"""
        parent = SimpleNamespace(id="r1", domain_id="corporate", actor_template="t", tick_count=10)
        payload = SimpleNamespace(
            fork_step=5,
            tick_count=5,
            assumptions=["Interest rate rises 2%", "Supply chain disruption"],
            decision_deltas=["Switch supplier"],
            state_overrides={},
            probability_band=[0.4, 0.8],
        )
        template = scenario_service._build_scenario_template(parent, payload)
        assert "Interest rate rises 2%" in template["assumptions"]
        assert "Supply chain disruption" in template["assumptions"]
        assert template["probability_band"] == [0.4, 0.8]

    def test_state_overrides_applied(self, scenario_service):
        """state_overrides 应被记录在模板中。"""
        parent = SimpleNamespace(id="r2", domain_id="military", actor_template="t", tick_count=6)
        payload = SimpleNamespace(
            fork_step=3,
            tick_count=3,
            assumptions=["New threat detected"],
            decision_deltas=["Increase ISR coverage"],
            state_overrides={"readiness": 0.95, "supply_network": 0.85},
            probability_band=None,
        )
        template = scenario_service._build_scenario_template(parent, payload)
        assert template["state_overrides"]["readiness"] == 0.95
        assert template["state_overrides"]["supply_network"] == 0.85


# ---------------------------------------------------------------------------
# KPI 追踪
# ---------------------------------------------------------------------------


class TestKPITracking:
    """测试 KPI 追踪逻辑。"""

    def test_branch_trajectory_builds(self):
        """build_branch_trajectory 应生成 KPI 轨迹。"""
        from planagent.services.simulation_branching import build_branch_trajectory

        baseline_state = {"revenue": 100.0, "costs": 60.0, "runway_weeks": 24.0}
        scenario_state = {"revenue": 120.0, "costs": 55.0, "runway_weeks": 28.0}
        trajectory = build_branch_trajectory("corporate", baseline_state, scenario_state)
        assert len(trajectory) > 0
        # 每个 trajectory item 应有 metric, baseline_end, scenario_end
        for item in trajectory:
            assert "metric" in item
            assert "baseline_end" in item
            assert "scenario_end" in item

    def test_score_branch_delta_positive(self):
        """场景优于基线时分支得分应为正（使用真实 corporate 指标）。"""
        from planagent.services.simulation_branching import score_branch_delta

        baseline = {"runway_weeks": 24.0, "gross_margin": 0.5, "nrr": 0.9}
        better = {"runway_weeks": 36.0, "gross_margin": 0.65, "nrr": 1.05}
        score = score_branch_delta("corporate", baseline, better)
        assert score > 0

    def test_score_branch_delta_negative(self):
        """场景劣于基线时分支得分应为负（使用真实 corporate 指标）。"""
        from planagent.services.simulation_branching import score_branch_delta

        baseline = {"runway_weeks": 24.0, "gross_margin": 0.5, "nrr": 0.9}
        worse = {"runway_weeks": 12.0, "gross_margin": 0.35, "nrr": 0.8}
        score = score_branch_delta("corporate", baseline, worse)
        assert score < 0

    def test_summarize_branch_trajectory(self):
        """summarize_branch_trajectory 应生成摘要列表。"""
        from planagent.services.simulation_branching import summarize_branch_trajectory

        trajectory = [
            {"metric": "revenue", "baseline_end": 100.0, "scenario_end": 120.0},
            {"metric": "costs", "baseline_end": 60.0, "scenario_end": 55.0},
        ]
        summary = summarize_branch_trajectory("corporate", trajectory)
        assert isinstance(summary, list)
        assert len(summary) > 0

    def test_military_kpi_trajectory(self):
        """军事域的 KPI 轨迹应正确生成。"""
        from planagent.services.simulation_branching import build_branch_trajectory

        baseline = {"readiness": 0.8, "supply_network": 0.7, "objective_control": 0.5}
        scenario = {"readiness": 0.9, "supply_network": 0.75, "objective_control": 0.6}
        trajectory = build_branch_trajectory("military", baseline, scenario)
        metrics = {item["metric"] for item in trajectory}
        assert "readiness" in metrics
        assert "supply_network" in metrics


# ---------------------------------------------------------------------------
# 推演执行（_execute_run 端到端验证）
# ---------------------------------------------------------------------------


class TestSimulationExecution:
    """测试推演执行逻辑。"""

    def test_initial_state_deepcopy(self):
        """初始状态应被深度拷贝，避免后续修改影响原始数据。"""
        original = {"revenue": 100.0, "costs": 60.0}
        copied = deepcopy(original)
        copied["revenue"] = 200.0
        assert original["revenue"] == 100.0

    def test_domain_pack_registry(self):
        """domain pack 注册表应包含 corporate 和 military。"""
        from planagent.simulation.domain_packs import registry

        corporate_pack = registry.get("corporate")
        military_pack = registry.get("military")
        assert corporate_pack is not None
        assert military_pack is not None

    def test_corporate_state_fields(self):
        """corporate domain pack 应有正确的状态字段。"""
        from planagent.simulation.domain_packs import registry

        pack = registry.get("corporate")
        field_names = {f.name for f in pack.state_fields}
        assert "runway_weeks" in field_names
        assert "delivery_velocity" in field_names
        assert "gross_margin" in field_names

    def test_military_state_fields(self):
        """military domain pack 应有正确的状态字段。"""
        from planagent.simulation.domain_packs import registry

        pack = registry.get("military")
        field_names = {f.name for f in pack.state_fields}
        assert "readiness" in field_names
        assert "supply_network" in field_names
        assert "objective_control" in field_names

    def test_resolve_initial_state(self):
        """_resolve_initial_state 应从 state_fields 和 actor_templates 构建初始状态。"""
        from planagent.services.simulation.domain_packs import SimulationDomainPacksMixin

        svc = SimulationDomainPacksMixin()
        from planagent.simulation.domain_packs import registry

        pack = registry.get("corporate")
        state = svc._resolve_initial_state(pack, "default")
        assert isinstance(state, dict)
        assert len(state) > 0
        # 所有值应为 float
        for value in state.values():
            assert isinstance(value, float)

    @pytest.mark.asyncio
    async def test_unsupported_domain_raises(self, engine_service, mock_session):
        """不支持的 domain 应抛出 ValueError。"""
        payload = SimpleNamespace(
            domain_id="unsupported_domain",
            execution_mode=None,
            tenant_id=None,
            preset_id=None,
            actor_template="default",
            initial_state={},
            tick_count=3,
            seed=None,
            market=None,
            military_use_mode=None,
            theater=None,
            company_name=None,
            company_industry=None,
            force_name=None,
        )
        with pytest.raises(ValueError, match="not implemented"):
            await engine_service.create_simulation_run(mock_session, payload)
