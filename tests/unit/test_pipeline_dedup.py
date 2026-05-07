"""Unit tests for SHA256 dedup key generation in planagent.services.pipeline."""

from __future__ import annotations

import hashlib
import concurrent.futures

from planagent.domain.api import SourceSeedInput
from planagent.services.pipeline import build_dedupe_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(**overrides) -> SourceSeedInput:
    defaults = dict(
        source_type="rss",
        source_url="https://example.com/article",
        title="Test Title",
        content_text="Body content.",
    )
    defaults.update(overrides)
    return SourceSeedInput(**defaults)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDedupeKeyDeterminism:
    def test_same_input_produces_same_key(self):
        item = _make_item()
        assert build_dedupe_key(item) == build_dedupe_key(item)

    def test_returns_hex_string(self):
        key = build_dedupe_key(_make_item())
        assert len(key) == 64  # SHA-256 hex is always 64 chars
        assert all(c in "0123456789abcdef" for c in key)


# ---------------------------------------------------------------------------
# Different content → different keys
# ---------------------------------------------------------------------------

class TestDedupeKeyUniqueness:
    def test_different_url_gives_different_key(self):
        a = _make_item(source_url="https://example.com/a")
        b = _make_item(source_url="https://example.com/b")
        assert build_dedupe_key(a) != build_dedupe_key(b)

    def test_different_title_gives_different_key(self):
        a = _make_item(title="Title Alpha")
        b = _make_item(title="Title Beta")
        assert build_dedupe_key(a) != build_dedupe_key(b)

    def test_different_content_gives_different_key(self):
        a = _make_item(content_text="Content A")
        b = _make_item(content_text="Content B")
        assert build_dedupe_key(a) != build_dedupe_key(b)


# ---------------------------------------------------------------------------
# Normalisation invariants
# ---------------------------------------------------------------------------

class TestDedupeKeyNormalization:
    def test_url_trailing_slash_ignored(self):
        a = _make_item(source_url="https://example.com/path")
        b = _make_item(source_url="https://example.com/path/")
        assert build_dedupe_key(a) == build_dedupe_key(b)

    def test_url_scheme_case_insensitive(self):
        a = _make_item(source_url="HTTPS://example.com/article")
        b = _make_item(source_url="https://example.com/article")
        assert build_dedupe_key(a) == build_dedupe_key(b)

    def test_url_query_params_and_fragments_ignored(self):
        a = _make_item(source_url="https://example.com/article")
        b = _make_item(source_url="https://example.com/article?ref=twitter#top")
        assert build_dedupe_key(a) == build_dedupe_key(b)

    def test_title_whitespace_collapsed(self):
        a = _make_item(title="Hello   World")
        b = _make_item(title="Hello World")
        assert build_dedupe_key(a) == build_dedupe_key(b)

    def test_title_case_insensitive(self):
        a = _make_item(title="Hello World")
        b = _make_item(title="hello world")
        assert build_dedupe_key(a) == build_dedupe_key(b)

    def test_content_whitespace_collapsed_and_lowered(self):
        a = _make_item(content_text="Multiple   spaces   here")
        b = _make_item(content_text="multiple spaces here")
        assert build_dedupe_key(a) == build_dedupe_key(b)

    def test_content_truncated_at_512_chars(self):
        long_a = "x" * 600
        long_b = "x" * 512 + "y" * 88  # first 512 chars are identical
        a = _make_item(content_text=long_a)
        b = _make_item(content_text=long_b)
        assert build_dedupe_key(a) == build_dedupe_key(b)

    def test_content_shorter_than_512_uses_full_text(self):
        a = _make_item(content_text="short")
        b = _make_item(content_text="short!")
        assert build_dedupe_key(a) != build_dedupe_key(b)


# ---------------------------------------------------------------------------
# SHA256 correctness
# ---------------------------------------------------------------------------

class TestDedupeKeySHA256Correctness:
    def test_matches_manual_sha256(self):
        item = _make_item(
            source_url="https://example.com/article",
            title="Test Title",
            content_text="Body content.",
        )
        # Reproduce the normalisation the function does
        normalized = "https://example.com/article|test title|body content."
        expected = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        assert build_dedupe_key(item) == expected


# ---------------------------------------------------------------------------
# Concurrent determinism
# ---------------------------------------------------------------------------

class TestDedupeKeyConcurrency:
    def test_concurrent_calls_produce_same_key(self):
        item = _make_item()
        expected = build_dedupe_key(item)

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda _: build_dedupe_key(item), range(200)))

        assert all(key == expected for key in results)
