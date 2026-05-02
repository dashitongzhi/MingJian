from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.domain.models import utc_now

if TYPE_CHECKING:
    from planagent.domain.models import SourceCursorState


class SourceStateService:
    """数据源游标状态管理——跟踪每个数据源的增量采集状态。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def get_or_create_state(
        self,
        session: AsyncSession,
        source_type: str,
        source_url_or_query: str,
        watch_rule_id: str | None = None,
        tenant_id: str | None = None,
        preset_id: str | None = None,
    ) -> SourceCursorState:
        """获取或创建数据源状态记录。"""
        SourceCursorStateModel = self._source_cursor_state_model()
        state = (
            await session.scalars(
                select(SourceCursorStateModel)
                .where(
                    SourceCursorStateModel.source_type == source_type,
                    SourceCursorStateModel.source_url_or_query == source_url_or_query,
                    SourceCursorStateModel.watch_rule_id == watch_rule_id,
                )
                .limit(1)
            )
        ).first()
        if state is not None:
            return state

        state = SourceCursorStateModel(
            watch_rule_id=watch_rule_id,
            source_type=source_type,
            source_url_or_query=source_url_or_query,
            tenant_id=tenant_id,
            preset_id=preset_id,
        )
        session.add(state)
        await session.flush()
        return state

    async def update_after_fetch(
        self,
        session: AsyncSession,
        state_id: str,
        success: bool,
        cursor: str | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
        content_hash: str | None = None,
        raw_source_item_id: str | None = None,
    ) -> None:
        """抓取成功/失败后更新游标状态。"""
        SourceCursorStateModel = self._source_cursor_state_model()
        state = await session.get(SourceCursorStateModel, state_id)
        if state is None:
            raise LookupError(f"Source cursor state {state_id} was not found.")

        now = utc_now()
        if success:
            if cursor is not None:
                state.cursor = cursor
            if etag is not None:
                state.etag = etag
            if last_modified is not None:
                state.last_modified = last_modified
            if content_hash is not None:
                state.last_seen_hash = content_hash
            if raw_source_item_id is not None:
                state.last_seen_raw_source_item_id = raw_source_item_id
            state.last_success_at = now
            state.consecutive_failures = 0
        else:
            state.consecutive_failures = int(state.consecutive_failures or 0) + 1
            state.last_failure_at = now

        state.updated_at = now
        await session.flush()

    async def should_fetch(
        self,
        session: AsyncSession,
        state: SourceCursorState,
        force_full_refresh_every: int = 24,
    ) -> bool:
        """判断是否需要抓取（基于小时级强制刷新间隔和上次失败状态）。"""
        _ = session
        last_success_at = self._normalize_datetime(state.last_success_at)
        last_failure_at = self._normalize_datetime(state.last_failure_at)

        if last_success_at is None and last_failure_at is None:
            return True

        if (
            last_failure_at is not None
            and (last_success_at is None or last_failure_at > last_success_at)
            and int(state.consecutive_failures or 0) < 5
        ):
            return True

        if last_success_at is None:
            return False

        return utc_now() - last_success_at >= timedelta(hours=force_full_refresh_every)

    async def reset_cursor(
        self,
        session: AsyncSession,
        watch_rule_id: str,
    ) -> int:
        """重置游标（强制下次全量抓取）。"""
        SourceCursorStateModel = self._source_cursor_state_model()
        states = list(
            (
                await session.scalars(
                    select(SourceCursorStateModel).where(
                        SourceCursorStateModel.watch_rule_id == watch_rule_id
                    )
                )
            ).all()
        )
        now = utc_now()
        for state in states:
            state.cursor = None
            state.etag = None
            state.last_modified = None
            state.last_seen_hash = None
            state.last_seen_raw_source_item_id = None
            state.updated_at = now

        from planagent.domain.models import WatchRule

        rule = await session.get(WatchRule, watch_rule_id)
        if rule is not None:
            rule.last_cursor_reset_at = now
            rule.next_poll_at = now
        await session.commit()
        return len(states)

    async def list_states(
        self,
        session: AsyncSession,
        watch_rule_id: str | None = None,
        source_type: str | None = None,
    ) -> list[SourceCursorState]:
        """列出数据源状态。"""
        SourceCursorStateModel = self._source_cursor_state_model()
        query = select(SourceCursorStateModel)
        if watch_rule_id is not None:
            query = query.where(SourceCursorStateModel.watch_rule_id == watch_rule_id)
        if source_type is not None:
            query = query.where(SourceCursorStateModel.source_type == source_type)
        query = query.order_by(SourceCursorStateModel.updated_at.desc())
        return list((await session.scalars(query)).all())

    def _normalize_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _source_cursor_state_model(self) -> type[SourceCursorState]:
        from planagent.domain.models import SourceCursorState

        return SourceCursorState
