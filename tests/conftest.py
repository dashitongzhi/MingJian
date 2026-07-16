from __future__ import annotations

import pytest

from planagent.db import reset_database_cache


@pytest.fixture(autouse=True)
def release_cached_database_between_tests():
    """Prevent one test's cached SQLite engine from leaking into another test."""
    yield
    reset_database_cache()
