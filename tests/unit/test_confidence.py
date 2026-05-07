"""Unit tests for evidence and claim confidence scoring functions."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from planagent.domain.api import SourceSeedInput
from planagent.services.pipeline import estimate_evidence_confidence, estimate_claim_confidence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item(**overrides) -> SourceSeedInput:
    defaults = dict(
        source_type="rss",
        source_url="https://example.com/a",
        title="Title",
        content_text="x" * 1500,
        published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SourceSeedInput(**defaults)


# ===========================================================================
# estimate_evidence_confidence
# ===========================================================================

class TestEvidenceConfidence:
    def test_max_rich_item_scores_095(self):
        """All fields present + >=1500 chars of content → 0.45 + 0.10 + 0.10 + 0.05 + 0.25 = 0.95."""
        item = _item(content_text="x" * 2000)
        assert estimate_evidence_confidence(item) == pytest.approx(0.95)

    def test_base_only_scores_045(self):
        """All required fields present, but title/url empty → base 0.45 + content bonus."""
        item = _item(title="", source_url="", published_at=None, content_text="x")
        # 0.45 base + 0 content bonus (len("x")/1500 ≈ 0.00067) → ≈0.4507
        score = estimate_evidence_confidence(item)
        assert score == pytest.approx(0.45 + 1 / 1500, abs=0.001)

    def test_title_bonus(self):
        with_title = _item(title="Real Title", source_url="", published_at=None, content_text="")
        without = _item(title="", source_url="", published_at=None, content_text="")
        assert estimate_evidence_confidence(with_title) - estimate_evidence_confidence(without) == pytest.approx(0.10)

    def test_url_bonus(self):
        with_url = _item(source_url="https://x.com", title="", published_at=None, content_text="")
        without = _item(source_url="", title="", published_at=None, content_text="")
        assert estimate_evidence_confidence(with_url) - estimate_evidence_confidence(without) == pytest.approx(0.10)

    def test_published_at_bonus(self):
        with_date = _item(published_at=datetime(2025, 1, 1, tzinfo=timezone.utc), title="", source_url="", content_text="")
        without = _item(published_at=None, title="", source_url="", content_text="")
        assert estimate_evidence_confidence(with_date) - estimate_evidence_confidence(without) == pytest.approx(0.05)

    def test_content_length_scales_linearly(self):
        short = _item(title="", source_url="", published_at=None, content_text="x" * 150)
        long = _item(title="", source_url="", published_at=None, content_text="x" * 750)
        diff = estimate_evidence_confidence(long) - estimate_evidence_confidence(short)
        # short bonus = 150/1500=0.10, long bonus = min(750/1500, 0.25)=0.25 → diff=0.15
        assert diff == pytest.approx(0.15, abs=0.001)

    def test_content_bonus_capped_at_025(self):
        huge = _item(title="", source_url="", published_at=None, content_text="x" * 5000)
        at_cap = _item(title="", source_url="", published_at=None, content_text="x" * 1500)
        assert estimate_evidence_confidence(huge) == pytest.approx(estimate_evidence_confidence(at_cap))

    def test_lower_bound_025(self):
        """Empty strings, no bonuses → base 0.45 with tiny content → should stay >= 0.25."""
        item = _item(title="", source_url="", published_at=None, content_text="")
        score = estimate_evidence_confidence(item)
        assert score >= 0.25

    def test_upper_bound_095(self):
        item = _item(content_text="x" * 10000)
        assert estimate_evidence_confidence(item) <= 0.95

    def test_score_in_valid_range_for_random_input(self):
        """Sanity: score always between 0.25 and 0.95 for any valid input."""
        for content_len in [0, 1, 100, 500, 1500, 5000]:
            item = _item(content_text="x" * content_len)
            score = estimate_evidence_confidence(item)
            assert 0.25 <= score <= 0.95, f"Score {score} out of range for content_len={content_len}"


# ===========================================================================
# estimate_claim_confidence
# ===========================================================================

class TestClaimConfidence:
    def test_full_offset_with_long_sentence(self):
        """A sentence of 240+ chars fully offsets the -0.20 penalty."""
        ev = 0.70
        sentence = "x" * 300
        score = estimate_claim_confidence(ev, sentence)
        assert score == pytest.approx(0.70, abs=0.01)  # 0.70 - 0.20 + 0.20 = 0.70

    def test_no_offset_with_short_sentence(self):
        ev = 0.70
        sentence = "x"  # len=1 → bonus ≈ 1/240
        score = estimate_claim_confidence(ev, sentence)
        # 0.70 - 0.20 + 1/240 ≈ 0.504
        assert score == pytest.approx(0.70 - 0.20 + 1 / 240, abs=0.005)

    def test_sentence_length_scales_linearly(self):
        ev = 0.80
        short = estimate_claim_confidence(ev, "x" * 30)   # bonus = 30/240 = 0.125
        long = estimate_claim_confidence(ev, "x" * 90)    # bonus = 90/240 = 0.375, capped at 0.20
        # diff = (0.20 - 0.125) = 0.075
        assert long - short == pytest.approx(0.075, abs=0.005)

    def test_sentence_bonus_capped_at_020(self):
        ev = 0.80
        long_score = estimate_claim_confidence(ev, "x" * 500)
        cap_score = estimate_claim_confidence(ev, "x" * 240)
        assert long_score == pytest.approx(cap_score)

    def test_lower_bound_025(self):
        score = estimate_claim_confidence(0.25, "")
        assert score >= 0.25

    def test_upper_bound_095(self):
        score = estimate_claim_confidence(0.95, "x" * 500)
        assert score <= 0.95

    def test_low_evidence_confidence_clamped(self):
        """Even with very low evidence input, score stays >= 0.25."""
        score = estimate_claim_confidence(0.0, "")
        assert score >= 0.25

    def test_high_evidence_confidence_clamped(self):
        """Even with impossibly high evidence input, score stays <= 0.95."""
        score = estimate_claim_confidence(2.0, "x" * 1000)
        assert score <= 0.95

    def test_monotonic_in_evidence_confidence(self):
        """Higher evidence confidence → higher claim confidence (all else equal)."""
        sentence = "A moderate length sentence for testing purposes."
        low = estimate_claim_confidence(0.40, sentence)
        high = estimate_claim_confidence(0.80, sentence)
        assert high > low

    def test_monotonic_in_sentence_length(self):
        """Longer sentence → higher claim confidence (all else equal)."""
        ev = 0.60
        short = estimate_claim_confidence(ev, "short")
        long = estimate_claim_confidence(ev, "x" * 200)
        assert long > short
