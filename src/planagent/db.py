from collections.abc import AsyncIterator
import asyncio
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from planagent.config import get_settings
from planagent.domain.models import Base


class Database:
    def __init__(self, database_url: str, sql_echo: bool) -> None:
        self.engine = create_async_engine(database_url, echo=sql_echo, future=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def init_models(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            if self.engine.dialect.name == "sqlite":
                rows = (await connection.execute(text("PRAGMA table_info(decision_records)"))).all()
                column_names = {row[1] for row in rows}
                if rows and "decision_method" not in column_names:
                    await connection.execute(
                        text(
                            "ALTER TABLE decision_records "
                            "ADD COLUMN decision_method VARCHAR(32) NOT NULL DEFAULT 'rule_engine'"
                        )
                    )
                graph_rows = (await connection.execute(text("PRAGMA table_info(knowledge_graph_nodes)"))).all()
                graph_column_names = {row[1] for row in graph_rows}
                if graph_rows and "embedding" not in graph_column_names:
                    await connection.execute(
                        text("ALTER TABLE knowledge_graph_nodes ADD COLUMN embedding JSON NOT NULL DEFAULT '[]'")
                    )
                if graph_rows and "embedding_model" not in graph_column_names:
                    await connection.execute(
                        text("ALTER TABLE knowledge_graph_nodes ADD COLUMN embedding_model VARCHAR(120)")
                    )
        self._initialized = True

    async def ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if not self._initialized:
                await self.init_models()

    async def dispose(self) -> None:
        await self.engine.dispose()

    def session(self) -> AsyncSession:
        return self.session_factory()


@lru_cache
def get_database(database_url: str | None = None) -> Database:
    settings = get_settings()
    url = database_url or settings.database_url
    return Database(url, settings.sql_echo)


def reset_database_cache() -> None:
    get_database.cache_clear()


async def get_session() -> AsyncIterator[AsyncSession]:
    database = get_database()
    await database.ensure_initialized()
    async with database.session() as session:
        yield session
