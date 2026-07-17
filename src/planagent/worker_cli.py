from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

import planagent.simulation  # noqa: F401
from planagent.config import get_settings
from planagent.db import get_database
from planagent.domain.models import DeadLetterEvent
from planagent.events.bus import ConsumedEvent
from planagent.events.bus import build_event_bus
from planagent.services.notification import NotificationConfig
from planagent.services.notification import NotificationService
from planagent.services.openai_client import OpenAIService
from planagent.simulation.rules import get_rule_registry
from planagent.workers.base import Worker
from planagent.workers.graph import GraphWorker
from planagent.workers.ingest import IngestWorker
from planagent.workers.knowledge import KnowledgeWorker
from planagent.workers.prediction_revision import PredictionRevisionWorker
from planagent.workers.report import ReportWorker
from planagent.workers.review import ReviewWorker
from planagent.workers.simulation import SimulationWorker
from planagent.workers.strategic_watch import StrategicWatchWorker
from planagent.workers.calibration import CalibrationWorker
from planagent.workers.watch_ingest import WatchIngestWorker

_WORKER_PUBLIC_ERROR = "Worker execution failed"


def build_worker(worker_name: str) -> Worker:
    settings = get_settings()
    event_bus = build_event_bus(settings)
    rule_registry = get_rule_registry(settings.rules_dir)
    openai_service = OpenAIService(settings)
    notification_service = _build_notification_service(settings)
    factories = {
        "ingest-worker": lambda: IngestWorker(settings, event_bus, openai_service),
        "knowledge-worker": lambda: KnowledgeWorker(settings, event_bus, openai_service),
        "graph-worker": lambda: GraphWorker(settings, event_bus),
        "review-worker": lambda: ReviewWorker(settings, event_bus, openai_service),
        "simulation-worker": lambda: SimulationWorker(
            settings, event_bus, rule_registry, openai_service
        ),
        "report-worker": lambda: ReportWorker(settings, event_bus, rule_registry, openai_service),
        "strategic-watch-worker": lambda: StrategicWatchWorker(
            settings,
            event_bus,
            rule_registry,
            openai_service,
        ),
        "watch-ingest-worker": lambda: WatchIngestWorker(
            settings,
            event_bus,
            rule_registry,
            openai_service,
            notification_service,
        ),
        "prediction-revision-worker": lambda: PredictionRevisionWorker(
            settings,
            event_bus,
            rule_registry,
            openai_service,
        ),
        "calibration-worker": lambda: CalibrationWorker(
            settings,
            rule_registry,
        ),
    }
    try:
        worker = factories[worker_name]()
    except KeyError as exc:
        raise SystemExit(f"Unknown worker: {worker_name}") from exc
    if not hasattr(worker, "openai_service"):
        worker.openai_service = openai_service
    return worker


def _build_notification_service(settings) -> NotificationService:
    return NotificationService(
        NotificationConfig(
            smtp_host=getattr(settings, "smtp_host", None),
            smtp_port=getattr(settings, "smtp_port", 587),
            smtp_user=getattr(settings, "smtp_user", None),
            smtp_password=getattr(settings, "smtp_password", None),
            webhook_urls=getattr(settings, "webhook_urls", []),
        )
    )


def list_workers() -> list[dict[str, object]]:
    return [
        IngestWorker.description.to_dict(),
        KnowledgeWorker.description.to_dict(),
        GraphWorker.description.to_dict(),
        ReviewWorker.description.to_dict(),
        SimulationWorker.description.to_dict(),
        ReportWorker.description.to_dict(),
        StrategicWatchWorker.description.to_dict(),
        WatchIngestWorker.description.to_dict(),
        PredictionRevisionWorker.description.to_dict(),
        CalibrationWorker.description.to_dict(),
    ]


async def run_worker(worker_name: str, loop: bool, interval_seconds: float) -> None:
    worker = build_worker(worker_name)
    event_bus = getattr(worker, "event_bus", None)
    consumer_name = f"{worker_name}-{os.getpid()}"
    try:
        if loop and _supports_stream_consumers(worker, event_bus):
            await _run_stream_worker(worker_name, worker, event_bus, consumer_name)
            return

        while True:
            try:
                result = await worker.run_once()
            except Exception as exc:
                await _record_dead_letter(worker_name, None, None, None, {}, exc)
                if event_bus is not None:
                    await event_bus.publish_dead_letter(
                        worker_name,
                        {"error": _WORKER_PUBLIC_ERROR},
                    )
                raise
            print(json.dumps({"worker": worker_name, "result": result}, ensure_ascii=True))
            if not loop:
                return
            await asyncio.sleep(interval_seconds)
    finally:
        if event_bus is not None:
            await event_bus.close()
        if hasattr(worker, "openai_service") and worker.openai_service is not None:
            await worker.openai_service.close()
        if hasattr(worker, "notification_service") and worker.notification_service is not None:
            await worker.notification_service.close()


def _supports_stream_consumers(worker: Worker, event_bus: object | None) -> bool:
    if event_bus is None:
        return False
    if getattr(worker, "uses_internal_event_consumer", False):
        return False
    consumes = getattr(worker.description, "consumes", ())
    return bool(consumes) and bool(getattr(event_bus, "supports_stream_consumers", False))


async def _run_stream_worker(
    worker_name: str,
    worker: Worker,
    event_bus: object,
    consumer_name: str,
) -> None:
    consumes = list(worker.description.consumes)
    settings = get_settings()
    initial_result = await worker.run_once()
    print(
        json.dumps(
            {"worker": worker_name, "triggered_by": ["startup_sweep"], "result": initial_result},
            ensure_ascii=True,
        )
    )

    while True:
        refresh_backpressure = getattr(event_bus, "refresh_backpressure", None)
        if refresh_backpressure is not None:
            await refresh_backpressure(
                topics=consumes,
                group=worker_name,
                pending_threshold=settings.backpressure_pending_threshold,
                ttl_seconds=max(30, settings.stream_consumer_block_ms // 1000 * 3),
            )

        events = await event_bus.reclaim_pending(
            topics=consumes,
            group=worker_name,
            consumer=consumer_name,
            min_idle_ms=60_000,
            count=settings.stream_consumer_count,
        )
        if not events:
            events = await event_bus.consume(
                topics=consumes,
                group=worker_name,
                consumer=consumer_name,
                count=settings.stream_consumer_count,
                block_ms=settings.stream_consumer_block_ms,
            )
        if not events:
            continue

        try:
            result = await worker.run_once()
        except Exception as exc:
            for event in events:
                await _retry_or_dead_letter_event(
                    event_bus,
                    worker_name,
                    consumer_name,
                    event,
                    exc,
                    settings.worker_max_attempts,
                    settings.stream_retry_base_seconds,
                )
            continue
        print(
            json.dumps(
                {
                    "worker": worker_name,
                    "triggered_by": [event.topic for event in events],
                    "result": result,
                },
                ensure_ascii=True,
            )
        )
        await _ack_events(event_bus, worker_name, events)


async def _ack_events(event_bus: object, worker_name: str, events: list[ConsumedEvent]) -> None:
    for event in events:
        await event_bus.ack(event.topic, worker_name, event.message_id)


async def _retry_or_dead_letter_event(
    event_bus: object,
    worker_name: str,
    consumer_name: str,
    event: ConsumedEvent,
    exc: Exception,
    max_attempts: int,
    retry_base_seconds: float,
) -> None:
    payload = dict(event.payload)
    raw_metadata = payload.get("_worker")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    attempts = int(metadata.get("attempts", 1) or 1)
    next_attempt = attempts + 1
    if next_attempt <= max(1, max_attempts):
        payload["_worker"] = {
            **metadata,
            "attempts": next_attempt,
            "last_error": _WORKER_PUBLIC_ERROR,
        }
        payload["attempt"] = next_attempt
        await asyncio.sleep(max(0.0, retry_base_seconds) * min(8, 2 ** max(0, attempts - 1)))
        await event_bus.publish(event.topic, payload)
        await event_bus.ack(event.topic, worker_name, event.message_id)
        return

    await _record_dead_letter(
        worker_name,
        event.topic,
        consumer_name,
        event.message_id,
        event.payload,
        exc,
    )
    await event_bus.publish_dead_letter(
        event.topic,
        {
            "group": worker_name,
            "consumer": consumer_name,
            "message_id": event.message_id,
            "payload": event.payload,
            "attempts": attempts,
            "attempt": attempts,
            "error": _WORKER_PUBLIC_ERROR,
        },
    )
    await event_bus.ack(event.topic, worker_name, event.message_id)


async def _record_dead_letter(
    worker_name: str,
    topic: str | None,
    consumer_name: str | None,
    message_id: str | None,
    payload: dict[str, Any],
    exc: Exception,
) -> None:
    database = get_database()
    await database.ensure_initialized()
    async with database.session() as session:
        session.add(
            DeadLetterEvent(
                topic=topic or worker_name,
                group_name=worker_name,
                consumer_name=consumer_name,
                message_id=message_id,
                payload=payload,
                error=_WORKER_PUBLIC_ERROR,
            )
        )
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="PlanAgent worker runner")
    parser.add_argument(
        "worker",
        nargs="?",
        default="list",
        help="Worker id to run, or 'list' to describe available workers.",
    )
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=5.0,
        help="Delay between loop iterations.",
    )
    args = parser.parse_args()

    if args.worker == "list":
        print(json.dumps(list_workers(), ensure_ascii=True, indent=2))
        return

    asyncio.run(run_worker(args.worker, args.loop, args.interval_seconds))


if __name__ == "__main__":
    main()
