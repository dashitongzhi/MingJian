from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.db import Database
from planagent.domain.models import RecommendationVersion, StrategicSession
from planagent.services.recommendations import RecommendationVersionService


@pytest.mark.asyncio
async def test_create_version_allocates_unique_numbers_concurrently(tmp_path: Path) -> None:
    database_path = tmp_path / "recommendation-versions.db"
    database = Database(
        f"sqlite+aiosqlite:///{database_path.resolve().as_posix()}",
        sql_echo=False,
    )
    service = RecommendationVersionService()
    strategic_session_id = "strategic-session-1"

    try:
        await database.init_models()
        async with database.session() as session:
            session.add(
                StrategicSession(
                    id=strategic_session_id,
                    name="Concurrent recommendation test",
                    topic="Should the team expand capacity?",
                    domain_id="corporate",
                )
            )
            await session.commit()

        first_session = database.session()
        second_session = database.session()
        try:
            # Both requests have already read the timeline before either one writes.
            # This is the race that a plain MAX(version_number) + 1 cannot serialize.
            for session in (first_session, second_session):
                current = await session.scalar(
                    select(func.max(RecommendationVersion.version_number)).where(
                        RecommendationVersion.session_id == strategic_session_id
                    )
                )
                assert current is None

            async def create(session: AsyncSession, summary: str) -> int:
                record = await service.create_version(
                    session,
                    session_id=strategic_session_id,
                    recommendation_summary=summary,
                    trigger_type="scheduled_refresh",
                )
                await session.commit()
                return record.version_number

            version_numbers = await asyncio.gather(
                create(first_session, "first"),
                create(second_session, "second"),
            )
        finally:
            await first_session.close()
            await second_session.close()

        assert sorted(version_numbers) == [1, 2]
        async with database.session() as session:
            records = list(
                (
                    await session.scalars(
                        select(RecommendationVersion)
                        .where(RecommendationVersion.session_id == strategic_session_id)
                        .order_by(RecommendationVersion.version_number.asc())
                    )
                ).all()
            )
        assert [record.version_number for record in records] == [1, 2]
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_database_rejects_duplicate_version_number_for_session(tmp_path: Path) -> None:
    database_path = tmp_path / "recommendation-version-constraint.db"
    database = Database(
        f"sqlite+aiosqlite:///{database_path.resolve().as_posix()}",
        sql_echo=False,
    )
    strategic_session_id = "strategic-session-constraint"

    try:
        await database.init_models()
        async with database.session() as session:
            session.add(
                StrategicSession(
                    id=strategic_session_id,
                    name="Recommendation constraint test",
                    topic="Should duplicate versions be accepted?",
                    domain_id="corporate",
                )
            )
            session.add_all(
                [
                    RecommendationVersion(
                        session_id=strategic_session_id,
                        version_number=1,
                        trigger_type="initial_result",
                        recommendation_summary="first",
                    ),
                    RecommendationVersion(
                        session_id=strategic_session_id,
                        version_number=1,
                        trigger_type="scheduled_refresh",
                        recommendation_summary="duplicate",
                    ),
                ]
            )

            with pytest.raises(IntegrityError):
                await session.commit()
    finally:
        await database.dispose()
