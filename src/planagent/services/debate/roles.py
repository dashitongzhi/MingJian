from __future__ import annotations

from typing import Any

REGISTRY_TO_DEBATE_ROLE: dict[str, str] = {
    "advocate": "advocate",
    "challenger": "challenger",
    "arbitrator": "arbitrator",
    "evidence_assessor": "intel_analyst",
    "geopolitical": "geo_expert",
    "economic": "econ_analyst",
    "military": "military_strategist",
    "tech": "tech_foresight",
    "social": "social_impact",
    "strategist": "advocate",
    "risk_analyst": "challenger",
    "opportunist": "arbitrator",
}

DEBATE_TO_REGISTRY_ROLE: dict[str, str] = {
    "advocate": "advocate",
    "challenger": "challenger",
    "arbitrator": "arbitrator",
    "intel_analyst": "evidence_assessor",
    "geo_expert": "geopolitical",
    "econ_analyst": "economic",
    "military_strategist": "military",
    "tech_foresight": "tech",
    "social_impact": "social",
    "strategist": "advocate",
    "risk_analyst": "challenger",
    "opportunist": "arbitrator",
}

BUILT_IN_DEBATE_ROLES: tuple[str, ...] = (
    "advocate",
    "challenger",
    "arbitrator",
    "intel_analyst",
    "geo_expert",
    "econ_analyst",
    "military_strategist",
    "tech_foresight",
    "social_impact",
)

DEBATE_ROLE_DISPLAY: dict[str, str] = {
    "advocate": "战略支持者",
    "challenger": "风险挑战者",
    "arbitrator": "首席仲裁官",
    "intel_analyst": "情报分析师",
    "geo_expert": "地缘政治专家",
    "econ_analyst": "经济分析师",
    "military_strategist": "军事战略家",
    "tech_foresight": "技术前瞻者",
    "social_impact": "社会影响评估师",
    "strategist": "战略支持者",
    "risk_analyst": "风险挑战者",
    "opportunist": "首席仲裁官",
}

ROUND_ROLE_ORDER: dict[int, tuple[str, ...]] = {
    1: (
        "advocate",
        "strategist",
        "intel_analyst",
        "geo_expert",
        "econ_analyst",
        "military_strategist",
        "tech_foresight",
        "social_impact",
        "challenger",
        "risk_analyst",
        "arbitrator",
        "opportunist",
    ),
    2: (
        "challenger",
        "risk_analyst",
        "intel_analyst",
        "advocate",
        "strategist",
        "geo_expert",
        "econ_analyst",
        "military_strategist",
        "tech_foresight",
        "social_impact",
        "arbitrator",
        "opportunist",
    ),
    3: (
        "advocate",
        "strategist",
        "intel_analyst",
        "geo_expert",
        "econ_analyst",
        "military_strategist",
        "tech_foresight",
        "social_impact",
        "challenger",
        "risk_analyst",
        "arbitrator",
        "opportunist",
    ),
    4: (
        "arbitrator",
        "opportunist",
        "advocate",
        "challenger",
        "intel_analyst",
        "geo_expert",
        "econ_analyst",
        "military_strategist",
        "tech_foresight",
        "social_impact",
    ),
}


def canonical_debate_role(role: str) -> str:
    return REGISTRY_TO_DEBATE_ROLE.get(role, role)


def registry_role_for_debate(role: str) -> str:
    return DEBATE_TO_REGISTRY_ROLE.get(role, role)


def debate_role_label(role: str) -> str:
    return DEBATE_ROLE_DISPLAY.get(role, role.replace("_", " ").title())


def debate_round_sort_key(round_number: int, role: str) -> tuple[int, int, str]:
    order = ROUND_ROLE_ORDER.get(round_number, ROUND_ROLE_ORDER[1])
    try:
        role_index = order.index(role)
    except ValueError:
        role_index = 80 if role.startswith("custom_") else 90
    return (round_number, role_index, role)


def debate_record_sort_key(record: Any) -> tuple[int, int, str]:
    return debate_round_sort_key(int(record.round_number), str(record.role))
