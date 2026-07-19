import pytest

from planagent.services.debate.engines import HeuristicDebateAdapter
from planagent.services.debate.roles import BUILT_IN_DEBATE_ROLES, debate_round_sort_key


def test_heuristic_adapter_builds_a_sorted_full_panel() -> None:
    rounds = HeuristicDebateAdapter().build_full_panel(
        subject_name="Blue Shield",
        support_confidence=0.78,
        challenge_confidence=0.46,
        verdict="ACCEPTED",
        decisive_evidence=["evidence-1", "evidence-2"],
        winning_arguments=["Readiness remains supportable."],
        minority_opinion="Supply risk still needs monitoring.",
        conditions=None,
        focus="the proposed posture",
        role_claims=None,
        custom_agents=[],
    )

    assert {item["role"] for item in rounds} == set(BUILT_IN_DEBATE_ROLES)
    assert rounds == sorted(
        rounds,
        key=lambda item: debate_round_sort_key(item["round_number"], item["role"]),
    )
    assert rounds[-1]["role"] == "arbitrator"
    assert rounds[-1]["position"] == "SUPPORT"


def test_heuristic_adapter_uses_explicit_custom_agents() -> None:
    rounds = HeuristicDebateAdapter().build_full_panel(
        subject_name="Blue Shield",
        support_confidence=0.72,
        challenge_confidence=0.52,
        verdict="CONDITIONAL",
        decisive_evidence=["evidence-1"],
        winning_arguments=["The posture remains plausible."],
        minority_opinion="The logistics picture is incomplete.",
        conditions=["Refresh logistics evidence."],
        focus="the proposed posture",
        role_claims=None,
        custom_agents=[
            {
                "role_key": "custom_logistics",
                "name": "Logistics Specialist",
                "description": "Tests sustainment and replenishment assumptions.",
            }
        ],
    )

    custom_rounds = [item for item in rounds if item["role"] == "custom_logistics"]
    assert [item["round_number"] for item in custom_rounds] == [1, 3]
    assert custom_rounds[0]["arguments"][0]["claim"] == (
        "Logistics Specialist participated in the expert panel."
    )
    assert custom_rounds[0]["arguments"][0]["reasoning"] == (
        "Tests sustainment and replenishment assumptions."
    )


@pytest.mark.parametrize(
    ("verdict", "position"),
    [
        ("ACCEPTED", "SUPPORT"),
        ("REJECTED", "OPPOSE"),
        ("CONDITIONAL", "CONDITIONAL"),
    ],
)
def test_heuristic_adapter_maps_verdicts_to_arbitrator_positions(
    verdict: str,
    position: str,
) -> None:
    rounds = HeuristicDebateAdapter().build_full_panel(
        subject_name="Blue Shield",
        support_confidence=0.64,
        challenge_confidence=0.61,
        verdict=verdict,
        decisive_evidence=[],
        winning_arguments=[],
        minority_opinion=None,
        conditions=None,
        focus="the proposed posture",
        role_claims=None,
        custom_agents=[],
    )

    arbitrator = next(item for item in rounds if item["role"] == "arbitrator")
    assert arbitrator["position"] == position
