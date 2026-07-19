from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from planagent.config import Settings
from planagent.domain.models import WatchRule
from planagent.services.watch_execution import (
    MIN_WATCH_EXECUTION_LEASE_SECONDS,
    WatchExecutionLeaseLostError,
    WatchExecutionLeaseManager,
    WatchExecutionService,
    new_watch_execution_owner,
    watch_execution_lease_expires_at,
)
from planagent.workers.watch_ingest import WatchIngestWorker


def _rule(domain_id: str = "corporate") -> WatchRule:
    return WatchRule(
        id="watch-1",
        name="Watch",
        domain_id=domain_id,
        query="Blue Team" if domain_id == "military" else "Acme AI",
        source_types=[],
        auto_trigger_simulation=True,
        auto_trigger_debate=True,
        tick_count=2,
    )


def test_watch_execution_lease_has_safe_minimum_and_unique_owner() -> None:
    settings = Settings(_env_file=None, worker_lease_seconds=60)
    now = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)

    expires_at = watch_execution_lease_expires_at(settings, now)

    assert int((expires_at - now).total_seconds()) == MIN_WATCH_EXECUTION_LEASE_SECONDS
    assert new_watch_execution_owner("worker") != new_watch_execution_owner("worker")


@pytest.mark.asyncio
async def test_watch_execution_runs_shared_simulation_and_debate_actions() -> None:
    simulation_service = SimpleNamespace(
        create_simulation_run=AsyncMock(return_value=SimpleNamespace(id="simulation-1"))
    )
    debate_workflow = SimpleNamespace(decide=AsyncMock(return_value=SimpleNamespace(id="debate-1")))
    service = WatchExecutionService(simulation_service, debate_workflow)

    result = await service.run_actions(
        SimpleNamespace(),
        _rule("military"),
        should_run=True,
        debate_context=("material evidence changed",),
    )

    assert result.simulation_run_id == "simulation-1"
    assert result.debate_id == "debate-1"
    simulation_payload = simulation_service.create_simulation_run.await_args.args[1]
    assert simulation_payload.domain_id == "military"
    debate_command = debate_workflow.decide.await_args.args[1]
    assert debate_command.context == ("material evidence changed",)


@pytest.mark.asyncio
async def test_worker_claims_are_committed_before_polling() -> None:
    class ScalarResult:
        def all(self) -> list[str]:
            return ["watch-1"]

    session = SimpleNamespace(
        scalars=AsyncMock(return_value=ScalarResult()),
        execute=AsyncMock(return_value=SimpleNamespace(rowcount=1)),
        get=AsyncMock(return_value=SimpleNamespace(id="watch-1")),
        commit=AsyncMock(),
    )
    worker = WatchIngestWorker.__new__(WatchIngestWorker)
    worker.settings = Settings(_env_file=None, worker_lease_seconds=60)
    worker.watch_execution_leases = WatchExecutionLeaseManager(worker.settings)

    claimed = await worker._claim_due_rules(
        session,
        limit=1,
        worker_id="watch-ingest-worker:unique",
    )

    assert [rule.id for rule in claimed] == ["watch-1"]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_cannot_complete_after_losing_its_lease() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(rowcount=0)),
        rollback=AsyncMock(),
        commit=AsyncMock(),
    )
    worker = WatchIngestWorker.__new__(WatchIngestWorker)
    worker.worker_instance_id = "watch-ingest-worker:old"
    worker.watch_execution_leases = WatchExecutionLeaseManager(Settings(_env_file=None))
    rule = SimpleNamespace(
        id="watch-1",
        created_at=datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc),
        poll_interval_minutes=60,
    )

    with pytest.raises(WatchExecutionLeaseLostError):
        await worker._mark_poll_success(session, rule)

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_strategic_refresh_failure_is_explicit_and_redacted() -> None:
    worker = WatchIngestWorker.__new__(WatchIngestWorker)
    worker._find_strategic_session = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(id="session-1")
    )
    worker.assistant_service = SimpleNamespace(
        load_session_payload=AsyncMock(return_value=SimpleNamespace()),
        run=AsyncMock(side_effect=RuntimeError("provider token sk-secret")),
    )
    session = SimpleNamespace(rollback=AsyncMock())
    rule = SimpleNamespace(id="watch-1", auto_trigger_debate=True)

    result = await worker._maybe_refresh_strategic_session(
        rule,
        session,
        "material change",
        "high",
        {"should_refresh": True},
        [],
    )

    assert result == {"refresh_failed": "true"}
    session.rollback.assert_awaited_once()
