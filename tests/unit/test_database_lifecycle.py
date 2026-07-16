from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.pool import NullPool

import planagent.db as database_module
from planagent.db import Database, close_database, reset_database_cache


@pytest.mark.asyncio
async def test_database_cache_disposal_handles_reset_close_and_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    database = Database("sqlite+aiosqlite:///:memory:", sql_echo=False)
    database.dispose = AsyncMock()
    database_module._db_instance = database

    reset_database_cache()
    await close_database()
    await asyncio.sleep(0)

    database.dispose.assert_awaited_once_with()
    assert database_module._db_instance is None
    assert not database_module._pending_disposals

    database = Database("sqlite+aiosqlite:///:memory:", sql_echo=False)
    database.dispose = AsyncMock(side_effect=RuntimeError("dispose failed"))
    database_module._db_instance = database

    reset_database_cache()
    await close_database()
    await asyncio.sleep(0)

    assert "Failed to dispose a reset database engine" in caplog.text
    assert not database_module._pending_disposals
    caplog.clear()

    database = Database("sqlite+aiosqlite:///:memory:", sql_echo=False)
    database.dispose = AsyncMock()
    database_module._db_instance = database

    await close_database()

    database.dispose.assert_awaited_once_with()
    assert database_module._db_instance is None

    release = asyncio.Event()
    database = Database("sqlite+aiosqlite:///:memory:", sql_echo=False)

    async def delayed_dispose() -> None:
        await release.wait()

    database.dispose = AsyncMock(side_effect=delayed_dispose)
    database_module._db_instance = database
    reset_database_cache()
    close_task = asyncio.create_task(close_database())

    await asyncio.sleep(0)
    assert not close_task.done()
    release.set()
    await close_task

    database.dispose.assert_awaited_once_with()
    assert not database_module._pending_disposals


@pytest.mark.asyncio
async def test_file_sqlite_database_does_not_retain_idle_connections(tmp_path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'database.db'}", sql_echo=False)

    assert isinstance(database.engine.pool, NullPool)

    await database.dispose()
