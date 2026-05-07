"""Shared fixtures for unit tests — no database or external services required."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from planagent.domain.api import SourceSeedInput
from planagent.config import Settings


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@pytest.fixture()
def settings():
    """Minimal Settings constructed without reading .env."""
    return Settings(_env_file=None)


@pytest.fixture()
def settings_with_openai_key(monkeypatch):
    """Settings with a fake OpenAI API key injected via env."""
    monkeypatch.setenv("PLANAGENT_OPENAI_SHARED_API_KEY", "sk-test-fake-key-12345")
    s = Settings(_env_file=None)
    yield s
    monkeypatch.delenv("PLANAGENT_OPENAI_SHARED_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# SourceSeedInput samples
# ---------------------------------------------------------------------------

_MINIMAL_ITEM_KWARGS = dict(
    source_type="rss",
    source_url="https://example.com/article",
    title="Test Article",
    content_text="Some content for testing.",
)


@pytest.fixture()
def minimal_seed():
    """SourceSeedInput with only required fields populated."""
    return SourceSeedInput(**_MINIMAL_ITEM_KWARGS)


@pytest.fixture()
def rich_seed():
    """SourceSeedInput with all optional fields populated (max confidence)."""
    return SourceSeedInput(
        source_type="rss",
        source_url="https://example.com/full-article",
        title="Complete Article With All Fields",
        content_text="A" * 2000,  # well over the 1500-char soft cap
        published_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        source_metadata={"author": "tester", "tags": ["unit"]},
    )


@pytest.fixture()
def empty_seed():
    """SourceSeedInput with empty strings — edge case for scoring."""
    return SourceSeedInput(
        source_type="",
        source_url="",
        title="",
        content_text="",
    )


@pytest.fixture()
def sample_claims():
    """Representative claim statements for classification tests."""
    return {
        "event": "Company X announced a new product launch",
        "signal": "Revenue increased 15% last quarter",
        "trend": "Adoption of AI tools is growing rapidly",
        "unclassified": "The weather is nice today",
    }


# ---------------------------------------------------------------------------
# Mock external services
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_openai_service():
    """Async-mock replacement for OpenAI service used in pipeline workers."""
    svc = AsyncMock()
    svc.is_configured.return_value = False
    svc.complete.return_value = '{"claims": [], "summary": "stub"}'
    return svc


@pytest.fixture()
def mock_db_session():
    """Lightweight mock DB session (no real connection)."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.scalars = AsyncMock()
    return session


@pytest.fixture()
def mock_redis():
    """In-memory-style mock for Redis interactions."""
    store: dict[str, str] = {}
    r = SimpleNamespace()
    r.get = AsyncMock(side_effect=lambda k: store.get(k))
    r.set = AsyncMock(side_effect=lambda k, v, **kw: store.__setitem__(k, v))
    r.setnx = AsyncMock(side_effect=lambda k, v: store.setdefault(k, v) is None)
    r.delete = AsyncMock(side_effect=lambda k: store.pop(k, None))
    r.exists = AsyncMock(side_effect=lambda k: k in store)
    return r
