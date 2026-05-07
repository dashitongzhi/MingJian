"""Unit tests for classify_claim() keyword-based classifier."""

from __future__ import annotations

import pytest

from planagent.services.pipeline import classify_claim


# ---------------------------------------------------------------------------
# Event keywords
# ---------------------------------------------------------------------------

class TestClassifyEvent:
    @pytest.mark.parametrize(
        "statement",
        [
            "SpaceX announced a new launch schedule",
            "The government will deploy additional resources",
            "Company plans to ship the update next week",
            "Military strike reported near the border",
            "Apple to release the new iPhone model",
        ],
    )
    def test_event_keywords(self, statement: str):
        kind, sub = classify_claim(statement)
        assert kind == "event"
        assert sub == "notable_action"

    def test_event_keyword_case_insensitive(self):
        kind, sub = classify_claim("COMPANY ANNOUNCES record profits")
        assert kind == "event"


# ---------------------------------------------------------------------------
# Signal keywords
# ---------------------------------------------------------------------------

class TestClassifySignal:
    @pytest.mark.parametrize(
        "statement",
        [
            "Revenue increased 15% this quarter",
            "Temperatures will drop sharply tonight",
            "Stock price rise of 3 percent",
            "Employment decreased by 200k",
            "A 50% surge in demand",
        ],
    )
    def test_signal_keywords(self, statement: str):
        kind, sub = classify_claim(statement)
        assert kind == "signal"
        assert sub == "metric_shift"


# ---------------------------------------------------------------------------
# Trend keywords
# ---------------------------------------------------------------------------

class TestClassifyTrend:
    @pytest.mark.parametrize(
        "statement",
        [
            "Adoption of EVs is growing worldwide",
            "Market momentum continues to build",
            "A declining trend in fossil fuel usage",
            "Cloud computing shows strong momentum",
        ],
    )
    def test_trend_keywords(self, statement: str):
        kind, sub = classify_claim(statement)
        assert kind == "trend"
        assert sub == "trajectory"


# ---------------------------------------------------------------------------
# Unclassified
# ---------------------------------------------------------------------------

class TestClassifyUnclassified:
    def test_no_matching_keywords(self):
        kind, sub = classify_claim("The weather is pleasant today")
        assert kind is None
        assert sub == "unclassified"

    def test_empty_string(self):
        kind, sub = classify_claim("")
        assert kind is None
        assert sub == "unclassified"


# ---------------------------------------------------------------------------
# Priority / ordering
# ---------------------------------------------------------------------------

class TestClassifyPriority:
    def test_event_beats_signal_when_both_present(self):
        """Event keywords are checked first — a sentence with both should classify as event."""
        kind, sub = classify_claim("They announced a 20% increase in sales")
        assert kind == "event"

    def test_signal_beats_trend_when_both_present(self):
        kind, sub = classify_claim("Growing adoption drove a 5% rise in revenue")
        # "rise" is signal, "growing" is trend — signal is checked first
        assert kind == "signal"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestClassifyEdgeCases:
    def test_very_long_text(self):
        long = "Some neutral text. " * 10000
        kind, sub = classify_claim(long)
        assert kind is None
        assert sub == "unclassified"

    def test_special_characters(self):
        kind, sub = classify_claim("!!@#$^&*()_+-=[]{}|;':\",./<>?")
        assert kind is None
        assert sub == "unclassified"

    def test_unicode_text(self):
        kind, sub = classify_claim("该公司宣布了一项新计划")
        assert kind is None
        assert sub == "unclassified"

    def test_keyword_as_substring(self):
        """A word containing a keyword as substring (e.g. 'releasement') should still match."""
        kind, sub = classify_claim("The releasement of the document was surprising")
        assert kind == "event"  # 'release' is a substring of 'releasement'

    def test_whitespace_only(self):
        kind, sub = classify_claim("   \n\t  ")
        assert kind is None
        assert sub == "unclassified"
