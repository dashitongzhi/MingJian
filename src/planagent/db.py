from collections.abc import AsyncIterator
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from planagent.config import get_settings
from planagent.domain.models import Base


class Database:
    def __init__(
        self,
        database_url: str,
        sql_echo: bool,
        pool_size: int = 20,
        max_overflow: int = 10,
        pool_recycle: int = 300,
    ) -> None:
        engine_kwargs: dict = {"echo": sql_echo, "future": True}
        if "sqlite" not in database_url:
            engine_kwargs.update(
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_recycle=pool_recycle,
            )
        self.engine = create_async_engine(database_url, **engine_kwargs)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self._initialized = False
        self._init_lock = asyncio.Lock()

    @property
    def is_sqlite(self) -> bool:
        return self.engine.dialect.name == "sqlite"

    async def init_models(self) -> None:
        """仅负责表创建（create_all），不做结构变更。

        所有表结构变更（新增列、修改约束等）均通过 Alembic 迁移脚本统一管理。
        请运行 `alembic upgrade head` 来应用数据库迁移。
        """
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
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


_db_instance: Database | None = None
_db_lock = asyncio.Lock()


def get_database() -> Database:
    global _db_instance
    if _db_instance is None:
        settings = get_settings()
        # 使用结构化数据库配置子模型
        db_settings = settings.db
        _db_instance = Database(
            db_settings.url,
            db_settings.sql_echo,
            pool_size=db_settings.pool_size,
            max_overflow=db_settings.max_overflow,
            pool_recycle=db_settings.pool_recycle,
        )
    return _db_instance


def reset_database_cache() -> None:
    global _db_instance
    _db_instance = None


async def get_session() -> AsyncIterator[AsyncSession]:
    database = get_database()
    await database.ensure_initialized()
    async with database.session() as session:
        yield session
