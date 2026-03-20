from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from planagent.config import get_settings
from planagent.domain.models import Base


class Database:
    def __init__(self, database_url: str, sql_echo: bool) -> None:
        self.engine = create_async_engine(database_url, echo=sql_echo, future=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init_models(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

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
    async with database.session() as session:
        yield session
