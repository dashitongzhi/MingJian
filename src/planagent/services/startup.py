from __future__ import annotations

import json
from pathlib import Path
import re
import uuid
from typing import Any

from planagent.domain.api import StartupKPICardRead, StartupKPIPackRead
from planagent.domain.models import SimulationRun

AGENT_STARTUP_PRESET_ID = "agent_startup"
_EXAMPLE_ROOT = Path(__file__).resolve().parents[3] / "examples" / "agent_startup"
_SCENARIO_FILES = {
    "baseline": "baseline_simulation.json",
    "upside": "upside_simulation.json",
    "downside": "downside_simulation.json",
}


def load_agent_startup_ingest_payload() -> dict[str, Any]:
    return _load_json("evidence_ingest.json")


def load_agent_startup_simulation_payload(name: str) -> dict[str, Any]:
    filename = _SCENARIO_FILES.get(name)
    if filename is None:
        raise ValueError(f"Unsupported agent startup scenario: {name}.")
    return _load_json(filename)


def normalize_tenant_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or None


def ensure_tenant_id(value: str | None) -> str:
    normalized = normalize_tenant_id(value)
    if normalized:
        return normalized
    return f"agent-startup-{uuid.uuid4().hex[:8]}"


def startup_preset_config(tenant_id: str | None, preset_id: str | None) -> dict[str, str]:
    config: dict[str, str] = {}
    normalized_tenant = normalize_tenant_id(tenant_id)
    if normalized_tenant is not None:
        config["tenant_id"] = normalized_tenant
    if preset_id:
        config["preset_id"] = preset_id
    return config


def resolve_tenant_id(configuration: dict[str, Any] | None) -> str | None:
    if not configuration:
        return None
    return normalize_tenant_id(str(configuration.get("tenant_id"))) if configuration.get("tenant_id") else None


def resolve_preset_id(configuration: dict[str, Any] | None) -> str | None:
    if not configuration:
        return None
    preset_id = configuration.get("preset_id")
    return str(preset_id) if preset_id else None


def resolve_run_tenant_id(run: SimulationRun) -> str | None:
    return normalize_tenant_id(getattr(run, "tenant_id", None)) or resolve_tenant_id(run.configuration)


def resolve_run_preset_id(run: SimulationRun) -> str | None:
    return getattr(run, "preset_id", None) or resolve_preset_id(run.configuration)


def is_agent_startup_run(run: SimulationRun) -> bool:
    market = str(run.configuration.get("market", "")).strip().lower()
    return resolve_run_preset_id(run) == AGENT_STARTUP_PRESET_ID or market == "enterprise-agents"


def build_startup_kpi_pack(
    run: SimulationRun,
    initial_state: dict[str, Any],
    final_state: dict[str, Any],
    matched_rules: list[str],
) -> StartupKPIPackRead | None:
    if not is_agent_startup_run(run):
        return None

    delivery_velocity = float(final_state.get("delivery_velocity", initial_state.get("delivery_velocity", 1.0)))
    runway_weeks = float(final_state.get("runway_weeks", initial_state.get("runway_weeks", 0.0)))
    brand_index = float(final_state.get("brand_index", initial_state.get("brand_index", 0.0)))
    cash = float(final_state.get("cash", initial_state.get("cash", 0.0)))
    pipeline = float(final_state.get("pipeline", initial_state.get("pipeline", 1.0)))
    active_deployments = float(final_state.get("active_deployments", initial_state.get("active_deployments", 3.0)))
    implementation_capacity = float(
        final_state.get("implementation_capacity", initial_state.get("implementation_capacity", 3.0))
    )
    support_load = float(final_state.get("support_load", initial_state.get("support_load", 0.35)))
    reliability_debt = float(final_state.get("reliability_debt", initial_state.get("reliability_debt", 0.28)))
    gross_margin = float(final_state.get("gross_margin", initial_state.get("gross_margin", 0.62)))
    nrr = float(final_state.get("nrr", initial_state.get("nrr", 1.02)))
    churn_risk = float(final_state.get("churn_risk", initial_state.get("churn_risk", 0.12)))

    delivery_load = active_deployments / max(implementation_capacity, 1.0)
    throughput_factor = max(0.55, min(1.25, 1.15 - (0.35 * delivery_load) - (0.25 * support_load)))
    deployment_days = round(14 / max(delivery_velocity * throughput_factor, 0.45), 1)
    design_partner_capacity = max(
        1,
        min(
            5,
            int(
                round(
                    min(
                        max(pipeline * 2.5, 1.0),
                        implementation_capacity * max(0.55, 1 - support_load),
                    )
                )
            ),
        ),
    )
    roi_verified = "corp.roi_pull" in matched_rules
    reliability_posture = max(0.0, brand_index - (0.45 * reliability_debt) - (0.15 * support_load))

    cards = [
        StartupKPICardRead(
            metric_id="design_partner_capacity",
            label="Design Partner Capacity",
            value=design_partner_capacity,
            unit="partners",
            target="3-5 active design partners",
            status=_banded_status(design_partner_capacity, good=3, watch=2),
            insight=(
                "Current wedge strength suggests how many live design partners the team can support "
                "without overextending delivery."
            ),
        ),
        StartupKPICardRead(
            metric_id="roi_proof",
            label="ROI Proof",
            value="verified" if roi_verified else "not-yet-verified",
            unit=None,
            target="At least one hard ROI proof point",
            status="good" if roi_verified else "risk",
            insight=(
                "Validated ROI is the clearest signal that this startup can sell results instead of generic agent hype."
            ),
        ),
        StartupKPICardRead(
            metric_id="deployment_window",
            label="Deployment Window",
            value=deployment_days,
            unit="days",
            target="<=14 days",
            status="good" if deployment_days <= 14 else "watch" if deployment_days <= 18 else "risk",
            insight=(
                "This estimates how quickly a new enterprise customer can reach first production value "
                "at the current delivery pace."
            ),
        ),
        StartupKPICardRead(
            metric_id="reliability_posture",
            label="Reliability Posture",
            value=round(reliability_posture, 2),
            unit="index",
            target=">=0.80",
            status=_banded_status(reliability_posture, good=0.8, watch=0.68),
            insight=(
                "This blends market trust with reliability debt and support burden so the team can see whether growth is outrunning product quality."
            ),
        ),
        StartupKPICardRead(
            metric_id="runway_buffer",
            label="Runway Buffer",
            value=round(runway_weeks, 1),
            unit="weeks",
            target=">=52 weeks",
            status=_banded_status(runway_weeks, good=52, watch=40),
            insight=(
                "Runway is the guardrail for founder-led sales. Falling below a year raises pressure to expand too early."
            ),
        ),
        StartupKPICardRead(
            metric_id="delivery_load",
            label="Delivery Load",
            value=round(delivery_load, 2),
            unit="load",
            target="<=0.90",
            status="good" if delivery_load <= 0.9 else "watch" if delivery_load <= 1.1 else "risk",
            insight=(
                "This compares active deployments to implementation capacity so the team can spot overload before every customer turns into custom work."
            ),
        ),
        StartupKPICardRead(
            metric_id="retention_quality",
            label="Retention Quality",
            value=round(nrr, 2),
            unit="index",
            target=">=1.00",
            status=_banded_status(nrr, good=1.0, watch=0.95),
            insight=(
                "NRR is the best short-form read on whether reliability, adoption, and support quality are strong enough to earn expansion."
            ),
        ),
        StartupKPICardRead(
            metric_id="margin_health",
            label="Margin Health",
            value=round(gross_margin, 2),
            unit="ratio",
            target=">=0.60",
            status=_banded_status(gross_margin, good=0.6, watch=0.52),
            insight=(
                "Gross margin shows whether the current deployment and support model can scale without turning every deal into services-heavy work."
            ),
        ),
        StartupKPICardRead(
            metric_id="cash_position",
            label="Cash Position",
            value=round(cash, 1),
            unit="index",
            target=">=50",
            status=_banded_status(cash, good=50, watch=35),
            insight=(
                "Cash remains a leading indicator for whether the company can keep improving reliability before hiring."
            ),
        ),
        StartupKPICardRead(
            metric_id="renewal_risk",
            label="Renewal Risk",
            value=round(churn_risk, 2),
            unit="risk",
            target="<=0.14",
            status="good" if churn_risk <= 0.14 else "watch" if churn_risk <= 0.2 else "risk",
            insight=(
                "Churn risk rises when support load and reliability debt accumulate faster than the product is creating durable value for customers."
            ),
        ),
    ]

    return StartupKPIPackRead(
        preset_id=AGENT_STARTUP_PRESET_ID,
        tenant_id=resolve_run_tenant_id(run),
        cards=cards,
    )


def _load_json(filename: str) -> dict[str, Any]:
    with (_EXAMPLE_ROOT / filename).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _banded_status(value: float, *, good: float, watch: float) -> str:
    if value >= good:
        return "good"
    if value >= watch:
        return "watch"
    return "risk"
