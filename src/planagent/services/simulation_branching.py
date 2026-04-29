from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricPolicy:
    preferred_direction: str
    alert_threshold: float
    critical_threshold: float


_STATE_POLICIES: dict[str, dict[str, MetricPolicy]] = {
    "corporate": {
        "cash": MetricPolicy("increase", 50.0, 25.0),
        "runway_weeks": MetricPolicy("increase", 40.0, 24.0),
        "infra_cost_index": MetricPolicy("decrease", 1.05, 1.15),
        "delivery_velocity": MetricPolicy("increase", 0.95, 0.82),
        "brand_index": MetricPolicy("increase", 0.95, 0.88),
        "market_share": MetricPolicy("increase", 0.045, 0.03),
        "team_morale": MetricPolicy("increase", 0.98, 0.9),
        "pipeline": MetricPolicy("increase", 0.95, 0.72),
        "implementation_capacity": MetricPolicy("increase", 2.8, 2.0),
        "support_load": MetricPolicy("decrease", 0.52, 0.7),
        "reliability_debt": MetricPolicy("decrease", 0.35, 0.52),
        "gross_margin": MetricPolicy("increase", 0.6, 0.48),
        "nrr": MetricPolicy("increase", 1.0, 0.92),
        "churn_risk": MetricPolicy("decrease", 0.14, 0.24),
    },
    "military": {
        "readiness": MetricPolicy("increase", 0.88, 0.75),
        "ammo": MetricPolicy("increase", 0.8, 0.65),
        "fuel": MetricPolicy("increase", 0.8, 0.65),
        "isr_coverage": MetricPolicy("increase", 0.85, 0.7),
        "ew_control": MetricPolicy("increase", 0.82, 0.68),
        "air_defense": MetricPolicy("increase", 0.85, 0.72),
        "logistics_throughput": MetricPolicy("increase", 0.85, 0.72),
        "supply_network": MetricPolicy("increase", 0.8, 0.65),
        "mobility": MetricPolicy("increase", 0.82, 0.68),
        "command_cohesion": MetricPolicy("increase", 0.85, 0.72),
        "objective_control": MetricPolicy("increase", 0.58, 0.45),
        "recovery_capacity": MetricPolicy("increase", 0.7, 0.56),
        "civilian_risk": MetricPolicy("decrease", 0.45, 0.6),
        "escalation_index": MetricPolicy("decrease", 0.45, 0.62),
        "ally_support": MetricPolicy("increase", 0.65, 0.5),
        "attrition_rate": MetricPolicy("decrease", 0.24, 0.35),
        "information_advantage": MetricPolicy("increase", 0.85, 0.72),
        "enemy_readiness": MetricPolicy("decrease", 0.72, 0.86),
        "enemy_pressure": MetricPolicy("decrease", 0.58, 0.72),
    },
}


def score_branch_delta(
    domain_id: str,
    baseline_final_state: dict[str, float],
    branch_final_state: dict[str, float],
) -> float:
    score = 0.0
    for metric in tracked_branch_metrics(domain_id):
        if metric not in baseline_final_state and metric not in branch_final_state:
            continue
        baseline_end = float(baseline_final_state.get(metric, 0.0))
        scenario_end = float(branch_final_state.get(metric, 0.0))
        score += metric_compare_score(domain_id, metric, baseline_end, scenario_end)
    return score


def metric_compare_score(
    domain_id: str,
    metric: str,
    baseline_end: float,
    scenario_end: float,
) -> float:
    policy = _STATE_POLICIES.get(domain_id, {}).get(metric)
    raw_delta = scenario_end - baseline_end
    if policy is None:
        return raw_delta
    span = max(abs(policy.alert_threshold - policy.critical_threshold), 0.05)
    if policy.preferred_direction == "decrease":
        raw_delta = baseline_end - scenario_end
    return raw_delta / span


def summarize_branch_trajectory(
    domain_id: str,
    trajectory: list[dict[str, Any]],
) -> list[str]:
    ranked = sorted(
        trajectory,
        key=lambda item: abs(
            metric_compare_score(
                domain_id,
                str(item.get("metric")),
                float(item.get("baseline_end", 0.0)),
                float(item.get("scenario_end", 0.0)),
            )
        ),
        reverse=True,
    )
    summaries: list[str] = []
    for item in ranked[:3]:
        metric = str(item.get("metric"))
        baseline_end = float(item.get("baseline_end", 0.0))
        scenario_end = float(item.get("scenario_end", 0.0))
        delta = round(scenario_end - baseline_end, 4)
        outcome = metric_outcome_label(domain_id, metric, baseline_end, scenario_end)
        sign = "+" if delta >= 0 else ""
        summaries.append(
            f"{metric} moved from {baseline_end:.3f} to {scenario_end:.3f} ({sign}{delta:.3f}), which is {outcome} than baseline."
        )
    return summaries


def metric_outcome_label(
    domain_id: str,
    metric: str,
    baseline_end: float,
    scenario_end: float,
) -> str:
    score = metric_compare_score(domain_id, metric, baseline_end, scenario_end)
    if score > 0.08:
        return "better"
    if score < -0.08:
        return "worse"
    return "roughly flat"


def build_scenario_compare_summary(
    domain_id: str,
    branches: list[dict[str, Any]],
    best_branch_id: str | None,
    best_branch_score: float,
) -> list[str]:
    if not branches:
        return ["No scenario branches are available yet."]
    if best_branch_id is None or best_branch_score <= 0.08:
        return [
            f"No {domain_id} branch clearly beats the baseline yet; use debate to inspect tradeoffs before pivoting."
        ]
    best_branch = next((branch for branch in branches if branch["branch_id"] == best_branch_id), None)
    if best_branch is None:
        return [f"Branch comparison is available for {len(branches)} scenario(s)."]
    return [
        f"Branch {best_branch_id} is currently the strongest alternative with score {best_branch_score:.2f}.",
        *(best_branch.get("key_deltas", [])[:2]),
    ]


def build_branch_trajectory(
    domain_id: str,
    parent_final: dict[str, Any],
    branch_final: dict[str, Any],
) -> list[dict[str, Any]]:
    tracked = tracked_branch_metrics(domain_id)
    return [
        {
            "metric": metric,
            "baseline_end": float(parent_final.get(metric, 0.0)),
            "scenario_end": float(branch_final.get(metric, 0.0)),
        }
        for metric in tracked
        if metric in parent_final or metric in branch_final
    ]


def tracked_branch_metrics(domain_id: str) -> list[str]:
    if domain_id == "corporate":
        return [
            "runway_weeks",
            "delivery_velocity",
            "pipeline",
            "support_load",
            "reliability_debt",
            "gross_margin",
            "nrr",
            "churn_risk",
            "market_share",
        ]
    return [
        "readiness",
        "logistics_throughput",
        "supply_network",
        "objective_control",
        "recovery_capacity",
        "attrition_rate",
        "enemy_readiness",
        "enemy_pressure",
        "isr_coverage",
        "air_defense",
        "civilian_risk",
        "escalation_index",
    ]
