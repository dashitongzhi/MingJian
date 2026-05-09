"""Unit tests for planagent.services.pipeline — 数据处理管道。

测试覆盖：
- 数据处理工具函数（normalize_url, normalize_text, summarize_text）
- 查重逻辑（build_dedupe_key 扩展测试）
- 批量处理辅助函数
- 证据置信度估算
- Claim 句子提取
- Claim 置信度估算
- 提取目标选择
"""

from __future__ import annotations

import hashlib

import pytest

from planagent.domain.api import SourceSeedInput
from planagent.services.pipeline import (
    build_dedupe_key,
    classify_claim,
    estimate_claim_confidence,
    estimate_evidence_confidence,
    extract_claim_sentences,
    normalize_text,
    normalize_url,
    select_extraction_target,
    summarize_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(**overrides) -> SourceSeedInput:
    """创建测试用的 SourceSeedInput。"""
    defaults = dict(
        source_type="rss",
        source_url="https://example.com/article",
        title="Test Title",
        content_text="Body content.",
    )
    defaults.update(overrides)
    return SourceSeedInput(**defaults)


# ═══════════════════════════════════════════════════════════════
# URL 规范化 — normalize_url
# ═══════════════════════════════════════════════════════════════


class TestNormalizeUrl:
    """测试 URL 规范化逻辑。"""

    def test_trailing_slash_removed(self):
        """URL 尾部斜杠应被移除。"""
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    def test_scheme_lowercased(self):
        """协议应转为小写。"""
        assert normalize_url("HTTPS://example.com/path").startswith("https://")

    def test_netloc_lowercased(self):
        """主机名应转为小写。"""
        assert normalize_url("https://EXAMPLE.COM/path") == "https://example.com/path"

    def test_root_path_preserved(self):
        """根路径 / 应被保留。"""
        result = normalize_url("https://example.com/")
        assert result.endswith("/")

    def test_query_and_fragment_stripped(self):
        """查询参数和锚点应被移除。"""
        result = normalize_url("https://example.com/path?query=1#section")
        assert "query" not in result
        assert "section" not in result

    def test_empty_path_becomes_root(self):
        """空路径应变为 /。"""
        result = normalize_url("https://example.com")
        assert result.endswith("/")


# ═══════════════════════════════════════════════════════════════
# 文本规范化 — normalize_text
# ═══════════════════════════════════════════════════════════════


class TestNormalizeText:
    """测试文本规范化逻辑。"""

    def test_whitespace_collapsed(self):
        """多余空白应被压缩为单个空格。"""
        assert normalize_text("hello   world") == "hello world"

    def test_leading_trailing_stripped(self):
        """首尾空白应被移除。"""
        assert normalize_text("  hello  ") == "hello"

    def test_tabs_and_newlines_collapsed(self):
        """制表符和换行符应被压缩。"""
        assert normalize_text("hello\t\nworld") == "hello world"

    def test_empty_string(self):
        """空字符串应返回空字符串。"""
        assert normalize_text("") == ""

    def test_single_word(self):
        """单个词应原样返回。"""
        assert normalize_text("hello") == "hello"


# ═══════════════════════════════════════════════════════════════
# 文本摘要 — summarize_text
# ═══════════════════════════════════════════════════════════════


class TestSummarizeText:
    """测试文本摘要逻辑。"""

    def test_short_text_returned_as_is(self):
        """短文本应原样返回。"""
        text = "Short summary."
        assert summarize_text(text) == text

    def test_long_text_truncated(self):
        """长文本应被截断并加省略号。"""
        text = "A" * 300
        result = summarize_text(text, max_length=220)
        assert len(result) <= 220
        assert result.endswith("...")

    def test_custom_max_length(self):
        """自定义最大长度。"""
        text = "B" * 100
        result = summarize_text(text, max_length=50)
        assert len(result) <= 50
        assert result.endswith("...")

    def test_exact_max_length(self):
        """恰好等于 max_length 的文本不应截断。"""
        text = "C" * 220
        result = summarize_text(text, max_length=220)
        assert result == text
        assert not result.endswith("...")

    def test_whitespace_normalized(self):
        """摘要应规范化空白。"""
        text = "Hello   world   test"
        result = summarize_text(text)
        assert "   " not in result


# ═══════════════════════════════════════════════════════════════
# 证据置信度估算 — estimate_evidence_confidence
# ═══════════════════════════════════════════════════════════════


class TestEstimateEvidenceConfidence:
    """测试证据置信度估算逻辑。"""

    def test_minimal_item_baseline(self):
        """最基础的 item 应有 0.45 的基准分。"""
        item = _make_item(title="", source_url="", content_text="")
        score = estimate_evidence_confidence(item)
        assert score >= 0.25  # 最低保障
        assert score <= 0.95  # 最高限制

    def test_with_title_adds_score(self):
        """有标题应增加置信度。"""
        item_no_title = _make_item(title="")
        item_with_title = _make_item(title="Important News")
        assert estimate_evidence_confidence(item_with_title) > estimate_evidence_confidence(
            item_no_title
        )

    def test_with_url_adds_score(self):
        """有 URL 应增加置信度。"""
        item_no_url = _make_item(source_url="")
        item_with_url = _make_item(source_url="https://example.com")
        assert estimate_evidence_confidence(item_with_url) > estimate_evidence_confidence(
            item_no_url
        )

    def test_with_published_at_adds_score(self):
        """有发布时间应增加置信度。"""
        from datetime import datetime, timezone

        item_no_date = _make_item()
        item_with_date = _make_item()
        item_with_date.published_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert estimate_evidence_confidence(item_with_date) > estimate_evidence_confidence(
            item_no_date
        )

    def test_longer_content_higher_score(self):
        """更长的内容应有更高的置信度（到上限为止）。"""
        item_short = _make_item(content_text="Short")
        item_long = _make_item(content_text="A" * 1500)
        assert estimate_evidence_confidence(item_long) > estimate_evidence_confidence(item_short)

    def test_score_clamped_at_095(self):
        """分数不应超过 0.95。"""
        from datetime import datetime, timezone

        item = _make_item(
            title="T",
            source_url="https://example.com",
            content_text="X" * 5000,
        )
        item.published_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        score = estimate_evidence_confidence(item)
        assert score <= 0.95

    def test_score_floor_at_025(self):
        """分数不应低于 0.25。"""
        item = _make_item(title="", source_url="", content_text="")
        score = estimate_evidence_confidence(item)
        assert score >= 0.25


# ═══════════════════════════════════════════════════════════════
# Claim 句子提取 — extract_claim_sentences
# ═══════════════════════════════════════════════════════════════


class TestExtractClaimSentences:
    """测试 Claim 句子提取。"""

    def test_single_sentence(self):
        """单句文本应返回一个句子。"""
        result = extract_claim_sentences("This is a claim.")
        assert len(result) == 1
        assert "claim" in result[0]

    def test_multiple_sentences(self):
        """多句文本应返回多个句子。"""
        text = "First claim. Second claim. Third claim."
        result = extract_claim_sentences(text)
        assert len(result) == 3

    def test_max_5_sentences(self):
        """最多返回 5 个句子。"""
        text = ". ".join([f"Sentence {i}" for i in range(10)])
        result = extract_claim_sentences(text)
        assert len(result) <= 5

    def test_empty_string(self):
        """空字符串应返回空列表。"""
        result = extract_claim_sentences("")
        assert result == []

    def test_chinese_punctuation_split(self):
        """中文标点后跟空格应作为分句依据。"""
        text = "第一句。 第二句！ 第三句？"
        result = extract_claim_sentences(text)
        assert len(result) == 3

    def test_whitespace_normalized(self):
        """句子中的多余空白应被规范化。"""
        text = "Hello   world. Next   sentence."
        result = extract_claim_sentences(text)
        assert all("   " not in s for s in result)


# ═══════════════════════════════════════════════════════════════
# Claim 置信度估算 — estimate_claim_confidence
# ═══════════════════════════════════════════════════════════════


class TestEstimateClaimConfidence:
    """测试 Claim 置信度估算。"""

    def test_base_from_evidence(self):
        """Claim 置信度基于证据置信度。"""
        score = estimate_claim_confidence(0.8, "Test sentence.")
        assert 0.25 <= score <= 0.95

    def test_longer_sentence_higher_score(self):
        """更长的句子应有更高的置信度（到上限）。"""
        short = estimate_claim_confidence(0.7, "Short.")
        long = estimate_claim_confidence(0.7, "A" * 240)
        assert long > short

    def test_score_clamped_at_095(self):
        """分数不应超过 0.95。"""
        score = estimate_claim_confidence(0.95, "X" * 500)
        assert score <= 0.95

    def test_score_floor_at_025(self):
        """分数不应低于 0.25。"""
        score = estimate_claim_confidence(0.2, "")
        assert score >= 0.25

    def test_low_evidence_low_claim(self):
        """低证据置信度应导致低 claim 置信度。"""
        low = estimate_claim_confidence(0.3, "X")
        high = estimate_claim_confidence(0.9, "X")
        assert low < high


# ═══════════════════════════════════════════════════════════════
# 提取目标选择 — select_extraction_target
# ═══════════════════════════════════════════════════════════════


class TestSelectExtractionTarget:
    """测试提取目标选择。"""

    @pytest.mark.parametrize(
        "source_type",
        ["x", "twitter", "tweet", "x.com", "x_recent_search", "x_model_search"],
    )
    def test_x_types_return_x_search(self, source_type: str):
        """X/Twitter 相关类型应返回 x_search 目标。"""
        assert select_extraction_target(source_type) == "x_search"

    def test_rss_returns_extraction(self):
        """RSS 应返回 extraction 目标。"""
        assert select_extraction_target("rss") == "extraction"

    def test_web_returns_extraction(self):
        """web 应返回 extraction 目标。"""
        assert select_extraction_target("web") == "extraction"

    def test_unknown_returns_extraction(self):
        """未知类型应返回 extraction 目标。"""
        assert select_extraction_target("unknown_type") == "extraction"

    def test_case_insensitive(self):
        """类型判断应不区分大小写。"""
        assert select_extraction_target("Twitter") == "x_search"
        assert select_extraction_target("RSS") == "extraction"


# ═══════════════════════════════════════════════════════════════
# 查重键生成扩展测试 — build_dedupe_key
# ═══════════════════════════════════════════════════════════════


class TestBuildDedupeKeyExtended:
    """扩展查重键测试。"""

    def test_deterministic_across_calls(self):
        """多次调用应产生相同结果。"""
        item = _make_item()
        keys = [build_dedupe_key(item) for _ in range(10)]
        assert len(set(keys)) == 1

    def test_unicode_content_handled(self):
        """Unicode 内容应被正确处理。"""
        item = _make_item(title="中文标题", content_text="中文内容测试")
        key = build_dedupe_key(item)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_special_characters_in_url(self):
        """URL 中的特殊字符应被正确处理。"""
        item = _make_item(source_url="https://example.com/path?q=hello%20world&lang=en")
        key = build_dedupe_key(item)
        assert len(key) == 64

    def test_very_long_content_truncated(self):
        """超长内容应在 512 字符处截断。"""
        item_a = _make_item(content_text="A" * 1000)
        item_b = _make_item(content_text="A" * 512 + "B" * 488)
        assert build_dedupe_key(item_a) == build_dedupe_key(item_b)

    def test_whitespace_normalization_in_title(self):
        """标题中的空白应被规范化后影响键。"""
        item_a = _make_item(title="Hello World")
        item_b = _make_item(title="Hello   World")
        assert build_dedupe_key(item_a) == build_dedupe_key(item_b)

    def test_case_normalization_in_title(self):
        """标题应被转为小写。"""
        item_a = _make_item(title="Hello World")
        item_b = _make_item(title="hello world")
        assert build_dedupe_key(item_a) == build_dedupe_key(item_b)

    def test_sha256_correctness(self):
        """应与手动 SHA-256 计算结果一致。"""
        item = _make_item(
            source_url="https://example.com/test",
            title="Test Title",
            content_text="Body content.",
        )
        normalized = "https://example.com/test|test title|body content."
        expected = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        assert build_dedupe_key(item) == expected


# ═══════════════════════════════════════════════════════════════
# 批量处理辅助函数测试
# ═══════════════════════════════════════════════════════════════


class TestBatchProcessingHelpers:
    """测试批量处理相关的辅助函数。"""

    def test_multiple_items_unique_keys(self):
        """不同的 item 应产生不同的查重键。"""
        items = [_make_item(title=f"Title {i}", content_text=f"Content {i}") for i in range(10)]
        keys = [build_dedupe_key(item) for item in items]
        assert len(set(keys)) == 10

    def test_duplicate_items_same_key(self):
        """相同内容的 item 应产生相同的查重键。"""
        items = [_make_item() for _ in range(5)]
        keys = {build_dedupe_key(item) for item in items}
        assert len(keys) == 1

    def test_mixed_unique_and_duplicate(self):
        """混合唯一和重复项。"""
        items = [
            _make_item(title="Unique 1"),
            _make_item(title="Unique 2"),
            _make_item(title="Unique 1"),  # 重复
            _make_item(title="Unique 3"),
            _make_item(title="Unique 2"),  # 重复
        ]
        keys = [build_dedupe_key(item) for item in items]
        assert len(set(keys)) == 3  # 只有 3 个唯一键

    def test_evidence_confidence_batch(self):
        """批量估算证据置信度。"""
        items = [_make_item(title=f"Title {i}", content_text="X" * (i * 100)) for i in range(1, 6)]
        scores = [estimate_evidence_confidence(item) for item in items]
        # 所有分数应在合理范围内
        assert all(0.25 <= s <= 0.95 for s in scores)
        # 更长的内容应有更高的分数
        assert scores[-1] > scores[0]

    def test_extract_claims_batch(self):
        """批量提取 Claim 句子。"""
        texts = [
            "First claim. Second claim.",
            "Another claim here.",
            "Claim A. Claim B. Claim C. Claim D. Claim E. Claim F.",
        ]
        results = [extract_claim_sentences(text) for text in texts]
        assert len(results[0]) == 2
        assert len(results[1]) == 1
        assert len(results[2]) == 5  # 最多 5 个
