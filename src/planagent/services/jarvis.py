from __future__ import annotations

import asyncio
import uuid
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from planagent.config import Settings
from planagent.domain.enums import EventTopic
from planagent.events.bus import EventBus
from planagent.services.openai_client import OpenAIService


@dataclass(frozen=True)
class JarvisTask:
    task_type: str
    payload: dict[str, Any]
    run_id: str | None = None
    target_id: str | None = None
    profile_id: str = "default"


@dataclass(frozen=True)
class JarvisStepResult:
    step: str
    target: str
    provider: str
    model: str
    status: str
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int = 0


@dataclass
class JarvisResult:
    task_id: str
    profile_id: str
    status: str
    steps: list[JarvisStepResult] = field(default_factory=list)
    verdict: str = "PASS"
    pass_score: int = 0
    critical_issues: int = 0
    state_path: list[str] = field(default_factory=list)
    validation_dimensions: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "profile_id": self.profile_id, "status": self.status,
            "steps": [{"step": s.step, "target": s.target, "provider": s.provider, "model": s.model, "status": s.status, "output": s.output, "error": s.error, "duration_ms": s.duration_ms} for s in self.steps],
            "verdict": self.verdict, "pass_score": self.pass_score, "critical_issues": self.critical_issues,
            "state_path": self.state_path, "validation_dimensions": self.validation_dimensions,
            "created_at": self.created_at.isoformat(),
        }


TASK_ROUTES: dict[str, list[str]] = {
    "analysis": ["primary"], "extraction": ["extraction"], "x_search": ["x_search"],
    "report": ["report"], "debate": ["debate_advocate", "debate_challenger", "debate_arbitrator"],
    "full_pipeline": ["primary", "extraction", "x_search", "report", "debate_advocate", "debate_challenger", "debate_arbitrator"],
}

STATE_PATH = ["INIT", "INGEST", "EXTRACT", "ANALYZE", "SIMULATE", "DEBATE", "DONE"]
VALIDATION_DIMENSIONS = {
    "source_coverage": "Cross-platform source completeness", "evidence_quality": "Claim confidence and provenance depth",
    "simulation_fidelity": "Tick realism and rule coverage", "debate_rigor": "Multi-round dialectical quality",
    "prediction_calibration": "Brier score vs human baseline", "response_latency": "End-to-end pipeline speed",
    "cost_efficiency": "Token spend per decision-quality output",
}


class JarvisOrchestrator:
    def __init__(self, settings: Settings, openai_service: OpenAIService, event_bus: EventBus | None = None) -> None:
        self._settings = settings
        self._openai = openai_service
        self._event_bus = event_bus

    async def orchestrate(self, task: JarvisTask) -> JarvisResult:
        task_id = str(uuid.uuid4())
        result = JarvisResult(task_id=task_id, profile_id=task.profile_id, status="COMPLETED", state_path=list(STATE_PATH), validation_dimensions=dict(VALIDATION_DIMENSIONS))
        targets = TASK_ROUTES.get(task.task_type, ["primary"])
        steps = await asyncio.gather(*[self._execute_target(t, task) for t in targets])
        result.steps = list(steps)
        success = sum(1 for s in steps if s.status == "success")
        fail = sum(1 for s in steps if s.status == "failed")
        result.critical_issues = fail
        if success == 0:
            result.status, result.verdict, result.pass_score = "FAILED", "FAIL", 0
        elif fail > 0:
            result.status, result.verdict, result.pass_score = "PARTIAL", "CONDITIONAL_PASS", max(40, int(88 * success / len(steps)))
        else:
            result.status, result.verdict, result.pass_score = "COMPLETED", "PASS", 88
        if self._event_bus:
            await self._event_bus.publish(EventTopic.SIMULATION_COMPLETED.value, {"jarvis_task_id": task_id, "status": result.status})
        return result

    async def _execute_target(self, target: str, task: JarvisTask) -> JarvisStepResult:
        start = time.monotonic()
        provider = self._get_provider(target)
        model = self._get_model(target)
        step_name = f"validate_{target}"
        if not self._openai.is_configured(target):
            return JarvisStepResult(step=step_name, target=target, provider=provider, model=model, status="skipped", output={"reason": f"Target {target} not configured"}, duration_ms=int((time.monotonic() - start) * 1000))
        try:
            sys_p = f"You are Jarvis orchestration. Validate {target} stage for '{task.task_type}'. Respond JSON: {{\"status\":\"ok|warn|fail\",\"findings\":[],\"recommendations\":[]}}"
            usr_c = str(task.payload.get("query", task.payload.get("topic", "")))[:2000]
            _, parsed = await self._openai.generate_json_for_target(target=target, system_prompt=sys_p, user_content=usr_c, max_tokens=500)
            return JarvisStepResult(step=step_name, target=target, provider=provider, model=model, status="success", output=parsed or {"status": "ok"}, duration_ms=int((time.monotonic() - start) * 1000))
        except Exception as exc:
            return JarvisStepResult(step=step_name, target=target, provider=provider, model=model, status="failed", error=str(exc)[:500], duration_ms=int((time.monotonic() - start) * 1000))

    def _get_provider(self, target: str) -> str:
        return getattr(self._settings, f"openai_{target}_provider", "openai") or "openai"

    def _get_model(self, target: str) -> str:
        return getattr(self._settings, f"resolved_openai_{target}_model", self._settings.openai_primary_model)

    async def test_target(self, target: str) -> dict[str, Any]:
        model = self._get_model(target)
        provider = self._get_provider(target)
        if not self._openai.is_configured(target):
            return {"target": target, "provider": provider, "model": model, "ok": False, "error": "Not configured"}
        try:
            result = await self._openai.test_connection(target)
            return {"target": target, "provider": provider, "model": model, "ok": result is not None, "output": str(result)}
        except Exception as exc:
            return {"target": target, "provider": provider, "model": model, "ok": False, "error": str(exc)[:500]}

    def get_profiles(self) -> dict[str, Any]:
        profiles: dict[str, Any] = {}
        for task_type, targets in TASK_ROUTES.items():
            profiles[task_type] = {t: {"provider": self._get_provider(t), "model": self._get_model(t), "configured": self._openai.is_configured(t)} for t in targets}
        return profiles
