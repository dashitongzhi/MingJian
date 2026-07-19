"""Unit tests for debate enhancement features.

Covers: reliability scoring, bias/blind-spot detection, weighted consensus,
structured dissent, and token-budget management (wrap-up nudge / trim).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from planagent.services.debate.adjudication import DebateAdjudicationMixin
from planagent.services.debate.llm import (
    _inject_wrap_up_nudge,
    _trim_old_messages,
    _WRAP_UP_RATIO,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mixin() -> DebateAdjudicationMixin:
    """Return a bare DebateAdjudicationMixin instance."""
    return DebateAdjudicationMixin()


def _mock_session() -> AsyncMock:
    """Return a mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    return session


def _make_round(role: str, position: str, confidence: float, arguments: list[dict]) -> dict:
    return {
        "round_number": 1,
        "role": role,
        "position": position,
        "confidence": confidence,
        "arguments": arguments,
        "rebuttals": [],
        "concessions": [],
    }


# ===================================================================
# TestReliabilityScoring
# ===================================================================


class TestReliabilityScoring:
    """Tests for score_argument_reliability and related helpers."""

    @pytest.mark.asyncio
    async def test_score_argument_reliability_returns_valid_scores(self):
        """Each score should have reliability_score 1-5, bias_flags list,
        evidence_strength in {strong,moderate,weak,speculative}."""
        mixin = _make_mixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "advocate",
                "SUPPORT",
                0.85,
                [
                    {
                        "claim": "Revenue will grow significantly",
                        "reasoning": "Based on detailed market research showing upward trends in Q3 and Q4 with strong evidence from multiple analyst reports.",
                        "evidence_ids": ["ev1", "ev2"],
                        "strength": "STRONG",
                    },
                ],
            ),
            _make_round(
                "challenger",
                "OPPOSE",
                0.4,
                [
                    {
                        "claim": "Market is volatile",
                        "reasoning": "Short thought.",
                        "evidence_ids": [],
                        "strength": "WEAK",
                    },
                ],
            ),
        ]

        scores = await mixin.score_argument_reliability("debate-1", round_records, session)

        assert len(scores) == 2
        valid_evidence = {"strong", "moderate", "weak", "speculative"}
        for s in scores:
            assert 1 <= s.reliability_score <= 5
            assert isinstance(s.bias_flags, list)
            assert s.evidence_strength in valid_evidence
            assert isinstance(s.blind_spots, list)

    @pytest.mark.asyncio
    async def test_strong_evidence_no_bias_yields_high_score(self):
        """Strong evidence + no bias patterns → score should be high (4 or 5)."""
        mixin = _make_mixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "advocate",
                "SUPPORT",
                0.9,
                [
                    {
                        "claim": "Growth trajectory is robust",
                        "reasoning": "Multiple independent data sources confirm consistent upward momentum across segments with peer-reviewed analysis and statistical significance.",
                        "evidence_ids": ["ev1", "ev2", "ev3"],
                        "strength": "STRONG",
                    },
                ],
            ),
        ]

        scores = await mixin.score_argument_reliability("debate-1", round_records, session)
        assert scores[0].reliability_score >= 4

    @pytest.mark.asyncio
    async def test_bias_detection_flags_cherry_picking(self):
        """An argument with cherry-picking keywords should have
        'cherry_picking' in bias_flags."""
        mixin = _make_mixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "challenger",
                "OPPOSE",
                0.6,
                [
                    {
                        "claim": "For example, one case showed failure",
                        "reasoning": "In one study, a specific instance demonstrated that the approach fails under particular conditions and notably that pattern repeats in certain scenarios.",
                        "evidence_ids": [],
                        "strength": "WEAK",
                    },
                ],
            ),
        ]

        scores = await mixin.score_argument_reliability("debate-2", round_records, session)
        assert len(scores) == 1
        assert "cherry_picking" in scores[0].bias_flags

    @pytest.mark.asyncio
    async def test_confirmation_bias_detected(self):
        """Arguments using confirmation language should be flagged."""
        mixin = _make_mixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "advocate",
                "SUPPORT",
                0.8,
                [
                    {
                        "claim": "The data confirms our hypothesis",
                        "reasoning": "This clearly shows the expected outcome is undeniable and proves beyond doubt that the strategy works as planned.",
                        "evidence_ids": ["ev1"],
                        "strength": "MODERATE",
                    },
                ],
            ),
        ]

        scores = await mixin.score_argument_reliability("debate-3", round_records, session)
        assert "confirmation_bias" in scores[0].bias_flags

    @pytest.mark.asyncio
    async def test_excessive_pessimism_detected(self):
        """Catastrophic/doom language should flag excessive_pessimism."""
        mixin = _make_mixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "challenger",
                "OPPOSE",
                0.9,
                [
                    {
                        "claim": "This will be a catastrophic disaster",
                        "reasoning": "The project is doomed and faces irreversible damage that will cause total failure with no recovery possible from this collapse.",
                        "evidence_ids": [],
                        "strength": "SPECULATIVE",
                    },
                ],
            ),
        ]

        scores = await mixin.score_argument_reliability("debate-4", round_records, session)
        assert "excessive_pessimism" in scores[0].bias_flags

    @pytest.mark.asyncio
    async def test_low_score_for_speculative_no_evidence(self):
        """Speculative evidence + multiple biases + short reasoning → score 1."""
        mixin = _make_mixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "challenger",
                "OPPOSE",
                0.3,
                [
                    {
                        "claim": "This is inevitable",
                        "reasoning": "Doom.",
                        "evidence_ids": [],
                        "strength": "SPECULATIVE",
                    },
                ],
            ),
        ]

        scores = await mixin.score_argument_reliability("debate-5", round_records, session)
        # base=4 + speculative(-2) - confirmation_bias(-1) - excessive_pessimism(-1) - short_reasoning(-1) = -1 → clamped to 1
        assert scores[0].reliability_score == 1

    @pytest.mark.asyncio
    async def test_multiple_arguments_per_round(self):
        """Multiple arguments in one round should each produce a score."""
        mixin = _make_mixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "advocate",
                "SUPPORT",
                0.7,
                [
                    {
                        "claim": "Point A is strong",
                        "reasoning": "Detailed analysis across multiple dimensions supports this conclusion with data from recent studies and expert opinions.",
                        "evidence_ids": ["ev1", "ev2"],
                        "strength": "STRONG",
                    },
                    {
                        "claim": "Point B is moderate",
                        "reasoning": "Some data exists but is not conclusive and further investigation is needed to verify the claims being made here.",
                        "evidence_ids": ["ev3"],
                        "strength": "MODERATE",
                    },
                ],
            ),
        ]

        scores = await mixin.score_argument_reliability("debate-6", round_records, session)
        assert len(scores) == 2


# ===================================================================
# TestBlindSpotDetection
# ===================================================================


class TestBlindSpotDetection:
    """Tests for detect_blind_spots."""

    def test_detect_blind_spots_flags_uncovered_dimensions(self):
        """If arguments only cover financial risks, other dimensions
        (technical, geopolitical, etc.) should be flagged."""
        mixin = _make_mixin()

        round_records = [
            _make_round(
                "advocate",
                "SUPPORT",
                0.8,
                [
                    {
                        "claim": "Revenue growth and budget allocation look healthy",
                        "reasoning": "The cost structure shows strong margin improvement with positive cash flow and good profit projections for the next fiscal year.",
                        "evidence_ids": [],
                        "strength": "MODERATE",
                    },
                ],
            ),
        ]

        blind_spots = mixin.detect_blind_spots(round_records)
        assert len(blind_spots) > 0
        # Financial dimension is covered by revenue/budget/cost/margin keywords
        # so it should NOT be in blind_spots
        assert not any("financial" in s.lower() for s in blind_spots)
        # Technical, geopolitical, etc. should be flagged
        assert any("technical" in s.lower() for s in blind_spots)
        assert any("geopolitical" in s.lower() for s in blind_spots)

    def test_no_blind_spots_when_all_covered(self):
        """When all dimensions are covered, no blind spots should be returned."""
        mixin = _make_mixin()

        # Construct arguments that touch every risk dimension keyword
        round_records = [
            _make_round(
                "advocate",
                "SUPPORT",
                0.7,
                [
                    {
                        "claim": "Financial budget revenue cost margin",
                        "reasoning": "Operational delivery velocity pipeline capacity efficiency "
                        "market share competition positioning growth "
                        "reliability infrastructure security "
                        "retention hiring morale burnout "
                        "sanctions alliance treaty "
                        "supply logistics transport inventory "
                        "surveillance reconnaissance intelligence "
                        "civilian humanitarian refugee "
                        "climate environment pollution sustainability carbon emission.",
                        "evidence_ids": [],
                        "strength": "MODERATE",
                    },
                ],
            ),
        ]

        blind_spots = mixin.detect_blind_spots(round_records)
        assert blind_spots == []

    def test_empty_rounds_no_blind_spots(self):
        """Empty round records → all dimensions flagged (no text at all)."""
        mixin = _make_mixin()
        blind_spots = mixin.detect_blind_spots([])
        assert len(blind_spots) > 0

    def test_multiple_rounds_aggregate_text(self):
        """Blind spots should aggregate across all rounds, not per-round."""
        mixin = _make_mixin()

        round_records = [
            _make_round(
                "advocate",
                "SUPPORT",
                0.8,
                [
                    {
                        "claim": "Budget and revenue are healthy",
                        "reasoning": "Cost and profit margin analysis shows good runway.",
                        "evidence_ids": [],
                        "strength": "MODERATE",
                    },
                ],
            ),
            _make_round(
                "strategist",
                "SUPPORT",
                0.7,
                [
                    {
                        "claim": "Market share growth and competition positioning",
                        "reasoning": "Expansion strategy with acquisition opportunities looks favorable.",
                        "evidence_ids": [],
                        "strength": "MODERATE",
                    },
                ],
            ),
        ]

        blind_spots = mixin.detect_blind_spots(round_records)
        # Financial and strategic are covered
        assert not any("financial" in s.lower() for s in blind_spots)
        assert not any("strategic" in s.lower() for s in blind_spots)
        # But technical, geopolitical, etc. are still missing
        assert any("technical" in s.lower() for s in blind_spots)


# ===================================================================
# TestWeightedConsensus
# ===================================================================


class TestWeightedConsensus:
    """Tests for weighted_consensus."""

    def test_equal_weights_approximates_simple_threshold(self):
        """With equal weights, verdict should follow the same
        confidence comparison logic as the default adjudication."""
        mixin = _make_mixin()
        equal_weights = {"strategist": 1.0, "risk_analyst": 1.0, "opportunist": 0.5}

        # Support clearly wins
        verdict, conf = mixin.weighted_consensus(0.9, 0.3, equal_weights)
        assert verdict == "ACCEPTED"

        # Challenge clearly wins
        verdict, conf = mixin.weighted_consensus(0.3, 0.9, equal_weights)
        assert verdict == "REJECTED"

        # Close → conditional
        verdict, conf = mixin.weighted_consensus(0.6, 0.55, equal_weights)
        assert verdict == "CONDITIONAL"

    def test_expert_weight_shift(self):
        """Higher weight on the support side should push verdict
        toward ACCEPTED even with raw support slightly lower."""
        mixin = _make_mixin()

        # Heavy weight on support (strategist)
        heavy_support = {"strategist": 2.0, "risk_analyst": 0.5, "opportunist": 0.5}
        verdict, _ = mixin.weighted_consensus(0.6, 0.65, heavy_support)
        # Support: 0.6 * 2.0 = 1.2, challenge: 0.65 * 0.5 = 0.325
        assert verdict == "ACCEPTED"

        # Heavy weight on challenge (risk_analyst)
        heavy_challenge = {"strategist": 0.5, "risk_analyst": 2.0, "opportunist": 0.5}
        verdict, _ = mixin.weighted_consensus(0.7, 0.55, heavy_challenge)
        # Support: 0.7 * 0.5 = 0.35, challenge: 0.55 * 2.0 = 1.1
        assert verdict == "REJECTED"

    def test_zero_weights_handled_gracefully(self):
        """All-zero weights should not crash; verdict should still be computed."""
        mixin = _make_mixin()
        zero_weights = {"strategist": 0.0, "risk_analyst": 0.0, "opportunist": 0.0}

        verdict, conf = mixin.weighted_consensus(0.8, 0.7, zero_weights)
        assert verdict in ("ACCEPTED", "REJECTED", "CONDITIONAL")
        assert 0.0 <= conf <= 1.0

    def test_weighted_confidence_clamped(self):
        """weighted_confidence should always be clamped between 0 and 1."""
        mixin = _make_mixin()
        huge_weights = {"strategist": 5.0, "risk_analyst": 5.0, "opportunist": 5.0}

        _, conf = mixin.weighted_consensus(0.9, 0.8, huge_weights)
        assert 0.0 <= conf <= 1.0

    def test_conditional_when_both_low(self):
        """Both sides below 0.65 should yield CONDITIONAL."""
        mixin = _make_mixin()
        weights = {"strategist": 1.0, "risk_analyst": 1.0, "opportunist": 0.5}

        verdict, _ = mixin.weighted_consensus(0.4, 0.35, weights)
        assert verdict == "CONDITIONAL"


# ===================================================================
# TestStructuredDissent
# ===================================================================


class TestStructuredDissent:
    """Tests for generate_structured_dissent (DebateAdjudicationMixin)."""

    @pytest.mark.asyncio
    async def test_generate_from_challenger_rounds(self):
        """Challenger OPPOSE arguments should be extracted into claims."""
        mixin = DebateAdjudicationMixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "advocate",
                "SUPPORT",
                0.8,
                [
                    {
                        "claim": "Growth is strong",
                        "reasoning": "Data supports",
                        "evidence_ids": ["ev1"],
                        "strength": "STRONG",
                    },
                ],
            ),
            _make_round(
                "challenger",
                "OPPOSE",
                0.7,
                [
                    {
                        "claim": "Market saturation risk is real",
                        "reasoning": "Competition data suggests limited growth",
                        "evidence": [],
                        "evidence_ids": [],
                        "strength": "MODERATE",
                    },
                ],
            ),
        ]

        dissent = await mixin.generate_structured_dissent(
            debate_id="debate-10",
            round_records=round_records,
            dissenter_role="challenger",
            session=session,
        )

        assert len(dissent.claims) >= 1
        assert dissent.claims[0]["claim"] == "Market saturation risk is real"
        assert dissent.dissenter_role == "challenger"
        assert dissent.overall_dissent_strength > 0

    @pytest.mark.asyncio
    async def test_confidence_trajectory_tracking(self):
        """Per-round confidence values for the dissenter should be captured."""
        mixin = DebateAdjudicationMixin()
        session = _mock_session()

        round_records = [
            _make_round("challenger", "OPPOSE", 0.5, [{"claim": "First concern", "evidence": []}]),
            {
                "round_number": 2,
                "role": "challenger",
                "position": "OPPOSE",
                "confidence": 0.7,
                "arguments": [{"claim": "Second concern", "evidence": []}],
                "rebuttals": [],
                "concessions": [],
            },
            {
                "round_number": 3,
                "role": "challenger",
                "position": "OPPOSE",
                "confidence": 0.8,
                "arguments": [{"claim": "Third concern", "evidence": []}],
                "rebuttals": [],
                "concessions": [],
            },
        ]

        dissent = await mixin.generate_structured_dissent(
            debate_id="debate-11",
            round_records=round_records,
            dissenter_role="challenger",
            session=session,
        )

        assert dissent.confidence_trajectory == [0.5, 0.7, 0.8]

    @pytest.mark.asyncio
    async def test_evidence_gap_detection(self):
        """Arguments without evidence should be flagged as evidence gaps."""
        mixin = DebateAdjudicationMixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "challenger",
                "OPPOSE",
                0.6,
                [
                    {"claim": "Unsupported claim A", "evidence_ids": []},
                    {"claim": "Supported claim B", "evidence_ids": ["ev1"]},
                ],
            ),
        ]

        dissent = await mixin.generate_structured_dissent(
            debate_id="debate-12",
            round_records=round_records,
            dissenter_role="challenger",
            session=session,
        )

        # Unsupported claim should appear in evidence_gaps (prefixed with "Unsupported claim: ")
        assert any("Unsupported claim A" in gap for gap in dissent.evidence_gaps)
        # Supported claim should not
        assert not any("Supported claim B" in gap for gap in dissent.evidence_gaps)

    @pytest.mark.asyncio
    async def test_dissent_categories_categorized(self):
        """Claims should be assigned categories based on content keywords."""
        mixin = DebateAdjudicationMixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "challenger",
                "OPPOSE",
                0.7,
                [
                    {"claim": "The evidence quality is questionable", "evidence": ["ev1"]},
                    {"claim": "There is a risk of collapse", "evidence": []},
                    {"claim": "An alternative approach could work better", "evidence": ["ev2"]},
                    {"claim": "The assumption behind this is flawed", "evidence": []},
                ],
            ),
        ]

        dissent = await mixin.generate_structured_dissent(
            debate_id="debate-13",
            round_records=round_records,
            dissenter_role="challenger",
            session=session,
        )

        categories = {c["category"] for c in dissent.claims}
        assert "evidence_quality" in categories
        assert "risk" in categories
        assert "alternative" in categories
        assert "assumption_challenge" in categories

    @pytest.mark.asyncio
    async def test_no_claims_when_dissenter_supports(self):
        """If the dissenter role (non-challenger) only has SUPPORT rounds, no claims collected."""
        mixin = DebateAdjudicationMixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "advocate",
                "SUPPORT",
                0.7,
                [{"claim": "Actually supporting", "evidence": []}],
            ),
        ]

        dissent = await mixin.generate_structured_dissent(
            debate_id="debate-14",
            round_records=round_records,
            dissenter_role="advocate",
            session=session,
        )

        assert dissent.claims == []
        assert dissent.overall_dissent_strength == 0.0

    @pytest.mark.asyncio
    async def test_duplicate_claims_preserved(self):
        """All claims are preserved including duplicates (deduplication not applied)."""
        mixin = DebateAdjudicationMixin()
        session = _mock_session()

        round_records = [
            _make_round(
                "challenger",
                "OPPOSE",
                0.6,
                [
                    {"claim": "Duplicate concern", "evidence": []},
                    {"claim": "Duplicate concern", "evidence": []},
                    {"claim": "Unique concern", "evidence": []},
                ],
            ),
        ]

        dissent = await mixin.generate_structured_dissent(
            debate_id="debate-15",
            round_records=round_records,
            dissenter_role="challenger",
            session=session,
        )

        claim_texts = [c["claim"] for c in dissent.claims]
        assert len(claim_texts) == 3  # All claims preserved
        assert "Unique concern" in claim_texts


# ===================================================================
# TestTokenBudget
# ===================================================================


class TestTokenBudget:
    """Tests for _inject_wrap_up_nudge and _trim_old_messages."""

    def test_wrap_up_nudge_triggered_above_threshold(self):
        """When used tokens > 80% of budget, a nudge message should be injected."""
        messages: list[dict] = []
        budget = 1000
        used = 850  # > 80% of 1000

        _inject_wrap_up_nudge(messages, used, budget)

        assert len(messages) == 1
        assert messages[0]["role"] == "system"
        assert "Token" in messages[0]["content"] or "Token" in messages[0]["content"]

    def test_wrap_up_nudge_not_triggered_below_threshold(self):
        """Below 80% threshold, no nudge should be injected."""
        messages: list[dict] = []
        budget = 1000
        used = 700  # < 80% of 1000

        _inject_wrap_up_nudge(messages, used, budget)

        assert len(messages) == 0

    def test_wrap_up_nudge_at_exact_threshold(self):
        """Exactly at threshold (used == budget * 0.8) should NOT trigger
        since the condition is `>` not `>=`."""
        messages: list[dict] = []
        budget = 1000
        used = int(budget * _WRAP_UP_RATIO)  # exactly 800

        _inject_wrap_up_nudge(messages, used, budget)

        assert len(messages) == 0

    def test_wrap_up_nudge_just_above_threshold(self):
        """One token above threshold should trigger."""
        messages: list[dict] = []
        budget = 1000
        used = int(budget * _WRAP_UP_RATIO) + 1

        _inject_wrap_up_nudge(messages, used, budget)

        assert len(messages) == 1

    def test_trim_old_messages_replaces_with_placeholder(self):
        """Old messages beyond keep count should be replaced with structure-preserving placeholders."""
        messages = [
            {
                "round_number": i,
                "role": "advocate",
                "position": "SUPPORT",
                "confidence": 0.7,
                "arguments": [f"arg-{i}"],
                "rebuttals": [],
                "concessions": [],
            }
            for i in range(10)
        ]

        trimmed = _trim_old_messages(messages, keep=3)

        assert len(trimmed) == 10
        # First 7 should be placeholders with preserved structure but cleared arguments
        for i in range(7):
            assert trimmed[i]["round_number"] == i
            assert trimmed[i]["role"] == "advocate"
            assert trimmed[i]["arguments"] == []
        # Last 3 should be original messages unchanged
        assert trimmed[7]["arguments"] == ["arg-7"]
        assert trimmed[8]["arguments"] == ["arg-8"]
        assert trimmed[9]["arguments"] == ["arg-9"]

    def test_trim_no_change_when_within_keep(self):
        """If message count <= keep, messages returned unchanged."""
        messages = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]

        trimmed = _trim_old_messages(messages, keep=3)

        assert trimmed is messages
        assert len(trimmed) == 2

    def test_trim_exactly_at_keep(self):
        """Exactly at keep count → no trimming."""
        messages = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]

        trimmed = _trim_old_messages(messages, keep=3)

        assert trimmed is messages

    def test_trim_preserves_order(self):
        """Trimmed messages should maintain original order."""
        messages = [{"role": "user", "content": f"m{i}"} for i in range(6)]

        trimmed = _trim_old_messages(messages, keep=2)

        # First 4 are placeholders, last 2 are original
        assert trimmed[-2]["content"] == "m4"
        assert trimmed[-1]["content"] == "m5"
