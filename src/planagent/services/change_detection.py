from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings

if TYPE_CHECKING:
    from planagent.domain.models import SourceChangeRecord, SourceCursorState


class ChangeDetectionService:
    """变化检测——对比新旧数据源内容，判定变化类型和重要性。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def detect_change(
        self,
        session: AsyncSession,
        state: SourceCursorState,
        new_hash: str | None,
        new_content_text: str,
        new_title: str,
        new_raw_source_item_id: str | None,
    ) -> SourceChangeRecord:
        """检测数据源内容变化，创建变更记录。"""
        SourceChangeRecordModel = self._source_change_record_model()
        old_hash = state.last_seen_hash

        if old_hash is None:
            change_type = "new"
            significance = "high"
            diff_summary = "首次抓取"
        elif new_hash == old_hash:
            change_type = "unchanged"
            significance = "none"
            diff_summary = None
        else:
            change_type = "updated"
            significance = self._compute_significance(
                old_hash=old_hash,
                new_hash=new_hash,
                new_content_text=new_content_text,
                new_title=new_title,
            )
            diff_summary = self._compute_diff_summary(
                new_content_text=new_content_text,
                new_title=new_title,
            )

        record = SourceChangeRecordModel(
            source_state_id=state.id,
            watch_rule_id=state.watch_rule_id,
            old_raw_source_item_id=state.last_seen_raw_source_item_id,
            new_raw_source_item_id=new_raw_source_item_id,
            old_hash=old_hash,
            new_hash=new_hash,
            change_type=change_type,
            significance=significance,
            diff_summary=diff_summary,
            changed_fields=self._detect_changed_fields(old_hash, new_hash),
        )
        session.add(record)
        await session.flush()
        return record

    def _compute_significance(
        self,
        old_hash: str,
        new_hash: str | None,
        new_content_text: str,
        new_title: str,
    ) -> str:
        """计算变化重要性。"""
        _ = old_hash, new_hash, new_title
        content_length = len(new_content_text.strip())
        if content_length >= 2000:
            return "high"
        if content_length >= 400:
            return "medium"
        return "low"

    def _compute_diff_summary(self, new_content_text: str, new_title: str) -> str:
        """生成变化摘要。"""
        _ = new_content_text
        return f"内容更新: {new_title[:100]}"

    def _detect_changed_fields(self, old_hash: str | None, new_hash: str | None) -> dict:
        """检测变化的字段。"""
        if old_hash is None:
            return {"all": True}
        if old_hash == new_hash:
            return {}
        return {"content": True}

    def _source_change_record_model(self) -> type[SourceChangeRecord]:
        from planagent.domain.models import SourceChangeRecord

        return SourceChangeRecord
