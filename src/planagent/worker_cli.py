from __future__ import annotations

import argparse
import asyncio
import json

import planagent.simulation  # noqa: F401
from planagent.config import get_settings
from planagent.events.bus import build_event_bus
from planagent.services.openai_client import OpenAIService
from planagent.simulation.rules import get_rule_registry
from planagent.workers.base import Worker
from planagent.workers.ingest import IngestWorker
from planagent.workers.knowledge import KnowledgeWorker
from planagent.workers.report import ReportWorker
from planagent.workers.review import ReviewWorker
from planagent.workers.simulation import SimulationWorker


def build_worker(worker_name: str) -> Worker:
    settings = get_settings()
    event_bus = build_event_bus(settings)
    rule_registry = get_rule_registry(settings.rules_dir)
    openai_service = OpenAIService(settings)
    factories = {
        "ingest-worker": lambda: IngestWorker(settings, event_bus, openai_service),
        "knowledge-worker": lambda: KnowledgeWorker(),
        "review-worker": lambda: ReviewWorker(),
        "simulation-worker": lambda: SimulationWorker(settings, event_bus, rule_registry, openai_service),
        "report-worker": lambda: ReportWorker(settings, event_bus, rule_registry, openai_service),
    }
    try:
        worker = factories[worker_name]()
    except KeyError as exc:
        raise SystemExit(f"Unknown worker: {worker_name}") from exc
    if not hasattr(worker, "openai_service"):
        worker.openai_service = openai_service
    return worker


def list_workers() -> list[dict[str, object]]:
    return [
        IngestWorker.description.to_dict(),
        KnowledgeWorker.description.to_dict(),
        ReviewWorker.description.to_dict(),
        SimulationWorker.description.to_dict(),
        ReportWorker.description.to_dict(),
    ]


async def run_worker(worker_name: str, loop: bool, interval_seconds: float) -> None:
    worker = build_worker(worker_name)
    try:
        while True:
            result = await worker.run_once()
            print(json.dumps({"worker": worker_name, "result": result}, ensure_ascii=True))
            if not loop:
                return
            await asyncio.sleep(interval_seconds)
    finally:
        if hasattr(worker, "service"):
            await worker.service.event_bus.close()
        if hasattr(worker, "openai_service") and worker.openai_service is not None:
            await worker.openai_service.close()


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
