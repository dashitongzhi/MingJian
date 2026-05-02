from collections.abc import AsyncIterator
import asyncio
from functools import lru_cache

from sqlalchemy import text
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
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            if self.is_sqlite:
                rows = (await connection.execute(text("PRAGMA table_info(decision_records)"))).all()
                column_names = {row[1] for row in rows}
                if rows and "decision_method" not in column_names:
                    # NOTE: 以下 ALTER TABLE 语句为向后兼容补丁，仅在旧数据库缺少列时执行。
                    # 正式环境请使用 Alembic migration 管理表结构变更。
                    await connection.execute(
                        text(
                            "ALTER TABLE decision_records "
                            "ADD COLUMN decision_method VARCHAR(32) NOT NULL DEFAULT 'rule_engine'"
                        )
                    )
                run_rows = (await connection.execute(text("PRAGMA table_info(simulation_runs)"))).all()
                run_column_names = {row[1] for row in run_rows}
                if run_rows and "military_use_mode" not in run_column_names:
                    # NOTE: 以下 ALTER TABLE 语句为向后兼容补丁，仅在旧数据库缺少列时执行。
                    # 正式环境请使用 Alembic migration 管理表结构变更。
                    await connection.execute(
                        text("ALTER TABLE simulation_runs ADD COLUMN military_use_mode VARCHAR(32)")
                    )
                watch_rows = (await connection.execute(text("PRAGMA table_info(watch_rules)"))).all()
                watch_column_names = {row[1] for row in watch_rows}
                watch_columns = {
                    "keywords": "JSON NOT NULL DEFAULT '[]'",
                    "exclude_keywords": "JSON NOT NULL DEFAULT '[]'",
                    "entity_tags": "JSON NOT NULL DEFAULT '[]'",
                    "trigger_threshold": "FLOAT NOT NULL DEFAULT 0.0",
                    "min_new_evidence_count": "INTEGER NOT NULL DEFAULT 1",
                    "importance_threshold": "FLOAT NOT NULL DEFAULT 0.0",
                    "incremental_enabled": "BOOLEAN NOT NULL DEFAULT 1",
                    "force_full_refresh_every_minutes": "INTEGER NOT NULL DEFAULT 1440",
                    "last_cursor_reset_at": "DATETIME",
                    "change_significance_threshold": "VARCHAR(32) NOT NULL DEFAULT 'medium'",
                }
                for column_name, ddl_type in watch_columns.items():
                    if watch_rows and column_name not in watch_column_names:
                        # NOTE: 以下 ALTER TABLE 语句为向后兼容补丁，仅在旧数据库缺少列时执行。
                        # 正式环境请使用 Alembic migration 管理表结构变更。
                        await connection.execute(
                            text(f"ALTER TABLE watch_rules ADD COLUMN {column_name} {ddl_type}")
                        )
                graph_rows = (await connection.execute(text("PRAGMA table_info(knowledge_graph_nodes)"))).all()
                graph_column_names = {row[1] for row in graph_rows}
                if graph_rows and "embedding" not in graph_column_names:
                    # NOTE: 以下 ALTER TABLE 语句为向后兼容补丁，仅在旧数据库缺少列时执行。
                    # 正式环境请使用 Alembic migration 管理表结构变更。
                    await connection.execute(
                        text("ALTER TABLE knowledge_graph_nodes ADD COLUMN embedding JSON NOT NULL DEFAULT '[]'")
                    )
                if graph_rows and "embedding_model" not in graph_column_names:
                    # NOTE: 以下 ALTER TABLE 语句为向后兼容补丁，仅在旧数据库缺少列时执行。
                    # 正式环境请使用 Alembic migration 管理表结构变更。
                    await connection.execute(
                        text("ALTER TABLE knowledge_graph_nodes ADD COLUMN embedding_model VARCHAR(120)")
                    )
                hypothesis_rows = (await connection.execute(text("PRAGMA table_info(hypotheses)"))).all()
                hypothesis_column_names = {row[1] for row in hypothesis_rows}
                if hypothesis_rows and "prediction_version_id" not in hypothesis_column_names:
                    # NOTE: 以下 ALTER TABLE 语句为向后兼容补丁，仅在旧数据库缺少列时执行。
                    # 正式环境请使用 Alembic migration 管理表结构变更。
                    await connection.execute(
                        text("ALTER TABLE hypotheses ADD COLUMN prediction_version_id VARCHAR(36)")
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
    return Database(
        url,
        settings.sql_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )


def reset_database_cache() -> None:
    get_database.cache_clear()


async def get_session() -> AsyncIterator[AsyncSession]:
    database = get_database()
    await database.ensure_initialized()
    async with database.session() as session:
        yield session
