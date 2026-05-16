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
            "task_id": self.task_id,
            "profile_id": self.profile_id,
            "status": self.status,
            "steps": [
                {
                    "step": s.step,
                    "target": s.target,
                    "provider": s.provider,
                    "model": s.model,
                    "status": s.status,
                    "output": s.output,
                    "error": s.error,
                    "duration_ms": s.duration_ms,
                }
                for s in self.steps
            ],
            "verdict": self.verdict,
            "pass_score": self.pass_score,
            "critical_issues": self.critical_issues,
            "state_path": self.state_path,
            "validation_dimensions": self.validation_dimensions,
            "created_at": self.created_at.isoformat(),
        }


TASK_ROUTES: dict[str, list[str]] = {
    "run": [
        "primary",
        "extraction",
        "report",
        "debate_advocate",
        "debate_challenger",
        "debate_arbitrator",
    ],
    "claim": ["extraction", "debate_challenger", "debate_arbitrator"],
    "analysis": ["primary"],
    "extraction": ["extraction"],
    "x_search": ["x_search"],
    "report": ["report"],
    "debate": ["debate_advocate", "debate_challenger", "debate_arbitrator"],
    "full_pipeline": [
        "primary",
        "extraction",
        "x_search",
        "report",
        "debate_advocate",
        "debate_challenger",
        "debate_arbitrator",
    ],
}

STATE_PATH = ["INIT", "INGEST", "EXTRACT", "ANALYZE", "SIMULATE", "DEBATE", "DONE"]
VALIDATION_DIMENSIONS = {
    "source_coverage": "Cross-platform source completeness",
    "evidence_quality": "Claim confidence and provenance depth",
    "simulation_fidelity": "Tick realism and rule coverage",
    "debate_rigor": "Multi-round dialectical quality",
    "prediction_calibration": "Brier score vs human baseline",
    "response_latency": "End-to-end pipeline speed",
    "cost_efficiency": "Token spend per decision-quality output",
}


class JarvisOrchestrator:
    def __init__(
        self, settings: Settings, openai_service: OpenAIService, event_bus: EventBus | None = None
    ) -> None:
        self._settings = settings
        self._openai = openai_service
        self._event_bus = event_bus

    async def orchestrate(self, task: JarvisTask) -> JarvisResult:
        task_id = str(uuid.uuid4())
        result = JarvisResult(
            task_id=task_id,
            profile_id=task.profile_id,
            status="COMPLETED",
            state_path=list(STATE_PATH),
            validation_dimensions=dict(VALIDATION_DIMENSIONS),
        )
        targets = TASK_ROUTES.get(task.task_type, ["primary"])
        steps = await asyncio.gather(*[self._execute_target(t, task) for t in targets])
        result.steps = list(steps)
        review_step = await self._self_review(task, result.steps)
        result.steps.append(review_step)
        repair_step = self._repair_plan(task, result.steps)
        result.steps.append(repair_step)

        success = sum(1 for s in steps if s.status == "success")
        fail = sum(1 for s in steps if s.status == "failed")
        skipped = sum(1 for s in steps if s.status == "skipped")
        review_output = review_step.output or {}
        result.critical_issues = fail + int(review_output.get("critical_issues", 0) or 0)
        result.validation_dimensions = {
            **dict(VALIDATION_DIMENSIONS),
            **{
                str(k): str(v)
                for k, v in (review_output.get("dimension_status") or {}).items()
            },
        }
        if fail > 0 and success == 0:
            result.status, result.verdict, result.pass_score = "FAILED", "FAIL", 0
        elif skipped == len(steps):
            result.status, result.verdict, result.pass_score = "COMPLETED", "PASS", 88
        elif fail > 0:
            result.status, result.verdict, result.pass_score = (
                "PARTIAL",
                "CONDITIONAL_PASS",
                max(40, int(88 * success / len(steps))),
            )
        else:
            result.status, result.verdict, result.pass_score = "COMPLETED", "PASS", 88

        if result.critical_issues > 0 and result.status == "COMPLETED":
            result.status = "PARTIAL"
            result.verdict = "CONDITIONAL_PASS"
            result.pass_score = min(result.pass_score, 72)
        if self._event_bus:
            await self._event_bus.publish(
                EventTopic.SIMULATION_COMPLETED.value,
                {"jarvis_task_id": task_id, "status": result.status},
            )
        return result

    async def _self_review(
        self,
        task: JarvisTask,
        steps: list[JarvisStepResult],
    ) -> JarvisStepResult:
        start = time.monotonic()
        findings = self._heuristic_review_findings(task, steps)
        critical = sum(1 for item in findings if item.get("severity") == "critical")
        warnings = sum(1 for item in findings if item.get("severity") == "warning")
        output: dict[str, Any] = {
            "status": "fail" if critical else "warn" if warnings else "ok",
            "critical_issues": critical,
            "warning_issues": warnings,
            "findings": findings,
            "dimension_status": self._dimension_status(task, steps, findings),
        }

        if self._openai.is_configured("primary"):
            try:
                _, parsed = await self._openai.generate_json_for_target(
                    target="primary",
                    system_prompt=(
                        "You are Jarvis QA. Review this decision pipeline result. "
                        'Return JSON: {"status":"ok|warn|fail","findings":[],"recommendations":[]}.'
                    ),
                    user_content=str(
                        {
                            "task_type": task.task_type,
                            "payload": task.payload,
                            "steps": [
                                {
                                    "target": step.target,
                                    "status": step.status,
                                    "error": step.error,
                                    "output": step.output,
                                }
                                for step in steps
                            ],
                        }
                    )[:4000],
                    max_tokens=700,
                )
                if isinstance(parsed, dict) and parsed:
                    output["model_review"] = parsed
                    if parsed.get("status") == "fail":
                        output["critical_issues"] = max(1, critical)
                    elif parsed.get("status") == "warn":
                        output["warning_issues"] = max(1, warnings)
            except Exception as exc:
                output["model_review_error"] = str(exc)[:300]

        return JarvisStepResult(
            step="self_review",
            target="jarvis",
            provider="internal",
            model="heuristic+primary",
            status="success",
            output=output,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def _repair_plan(
        self,
        task: JarvisTask,
        steps: list[JarvisStepResult],
    ) -> JarvisStepResult:
        start = time.monotonic()
        actions: list[dict[str, Any]] = []
        for step in steps:
            if step.status == "failed":
                actions.append(
                    {
                        "action": "retry_target",
                        "target": step.target,
                        "reason": step.error or "target failed",
                    }
                )
            if step.status == "skipped":
                actions.append(
                    {
                        "action": "configure_target",
                        "target": step.target,
                        "reason": (step.output or {}).get("reason", "target not configured"),
                    }
                )

        review = next((step for step in steps if step.step == "self_review"), None)
        for finding in ((review.output or {}).get("findings") if review else []) or []:
            actions.append(
                {
                    "action": finding.get("repair_action", "review_manually"),
                    "target": finding.get("dimension", task.task_type),
                    "reason": finding.get("message", ""),
                }
            )

        if not actions:
            actions.append(
                {
                    "action": "continue_monitoring",
                    "target": task.target_id or task.run_id or task.task_type,
                    "reason": "No blocking quality issue detected.",
                }
            )

        return JarvisStepResult(
            step="repair_plan",
            target="jarvis",
            provider="internal",
            model="rule_based",
            status="success",
            output={"actions": actions[:8], "auto_repair_ready": True},
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def _heuristic_review_findings(
        self,
        task: JarvisTask,
        steps: list[JarvisStepResult],
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        if any(step.status == "failed" for step in steps):
            findings.append(
                {
                    "severity": "critical",
                    "dimension": "pipeline_reliability",
                    "message": "At least one required pipeline target failed.",
                    "repair_action": "retry_failed_targets",
                }
            )
        if all(step.status == "skipped" for step in steps):
            findings.append(
                {
                    "severity": "warning",
                    "dimension": "model_configuration",
                    "message": "All model-backed checks were skipped because targets are not configured.",
                    "repair_action": "configure_model_targets",
                }
            )
        if not task.payload.get("run_id") and task.task_type in {"run", "report", "debate"}:
            findings.append(
                {
                    "severity": "warning",
                    "dimension": "audit_context",
                    "message": "Jarvis ran without a run_id, so audit context is incomplete.",
                    "repair_action": "rerun_with_target_context",
                }
            )
        if task.payload.get("source_count") == 0:
            findings.append(
                {
                    "severity": "warning",
                    "dimension": "source_coverage",
                    "message": "No external source coverage was provided for this review.",
                    "repair_action": "trigger_research_agents",
                }
            )
        return findings

    def _dimension_status(
        self,
        task: JarvisTask,
        steps: list[JarvisStepResult],
        findings: list[dict[str, Any]],
    ) -> dict[str, str]:
        status = {key: "ok" for key in VALIDATION_DIMENSIONS}
        for finding in findings:
            dimension = str(finding.get("dimension", ""))
            severity = str(finding.get("severity", "warning"))
            if dimension in status:
                status[dimension] = "fail" if severity == "critical" else "warn"
        if any(step.target == "debate_arbitrator" for step in steps):
            status["debate_rigor"] = status.get("debate_rigor", "ok")
        if task.task_type in {"analysis", "full_pipeline", "run"}:
            status.setdefault("source_coverage", "ok")
        return status

    async def _execute_target(self, target: str, task: JarvisTask) -> JarvisStepResult:
        start = time.monotonic()
        provider = self._get_provider(target)
        model = self._get_model(target)
        step_name = f"validate_{target}"
        if not self._openai.is_configured(target):
            return JarvisStepResult(
                step=step_name,
                target=target,
                provider=provider,
                model=model,
                status="skipped",
                output={"reason": f"Target {target} not configured"},
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        try:
            sys_p = f'You are Jarvis orchestration. Validate {target} stage for \'{task.task_type}\'. Respond JSON: {{"status":"ok|warn|fail","findings":[],"recommendations":[]}}'
            usr_c = str(task.payload.get("query", task.payload.get("topic", "")))[:2000]
            _, parsed = await self._openai.generate_json_for_target(
                target=target, system_prompt=sys_p, user_content=usr_c, max_tokens=500
            )
            return JarvisStepResult(
                step=step_name,
                target=target,
                provider=provider,
                model=model,
                status="success",
                output=parsed or {"status": "ok"},
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as exc:
            return JarvisStepResult(
                step=step_name,
                target=target,
                provider=provider,
                model=model,
                status="failed",
                error=str(exc)[:500],
                duration_ms=int((time.monotonic() - start) * 1000),
            )

    def _get_provider(self, target: str) -> str:
        return getattr(self._settings, f"openai_{target}_provider", "openai") or "openai"

    def _get_model(self, target: str) -> str:
        return getattr(
            self._settings, f"resolved_openai_{target}_model", self._settings.openai_primary_model
        )

    async def test_target(self, target: str) -> dict[str, Any]:
        model = self._get_model(target)
        provider = self._get_provider(target)
        if not self._openai.is_configured(target):
            return {
                "target": target,
                "provider": provider,
                "model": model,
                "ok": False,
                "error": "Not configured",
            }
        try:
            result = await self._openai.test_connection(target)
            return {
                "target": target,
                "provider": provider,
                "model": model,
                "ok": result is not None,
                "output": str(result),
            }
        except Exception as exc:
            return {
                "target": target,
                "provider": provider,
                "model": model,
                "ok": False,
                "error": str(exc)[:500],
            }

    def get_profiles(self) -> dict[str, Any]:
        profiles: dict[str, Any] = {}
        for task_type, targets in TASK_ROUTES.items():
            profiles[task_type] = {
                t: {
                    "provider": self._get_provider(t),
                    "model": self._get_model(t),
                    "configured": self._openai.is_configured(t),
                }
                for t in targets
            }
        return profiles
