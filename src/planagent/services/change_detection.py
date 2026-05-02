from __future__ import annotations

import hashlib
import json
from typing import Any, TYPE_CHECKING

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
        stable_new_hash = new_hash or self.compute_content_hash(new_content_text)

        if old_hash is None:
            change_type = "new"
            significance = "high"
            diff_summary = "首次抓取"
        elif stable_new_hash == old_hash:
            change_type = "unchanged"
            significance = "none"
            diff_summary = None
        else:
            change_type = "updated"
            significance = self._compute_significance(
                old_hash=old_hash,
                new_hash=stable_new_hash,
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
            new_hash=stable_new_hash,
            change_type=change_type,
            significance=significance,
            diff_summary=diff_summary,
            changed_fields=self._detect_changed_fields(old_hash, stable_new_hash),
        )
        session.add(record)
        await session.flush()
        return record

    def compute_content_hash(
        self,
        content_text: str,
        sources: list[Any] | None = None,
    ) -> str:
        """计算稳定内容 hash。"""
        normalized = content_text.strip()
        if sources:
            sorted_sources = sorted(
                (self._source_as_dict(source) for source in sources),
                key=lambda source: (
                    str(source.get("source_type", "")),
                    str(source.get("url", "")),
                    str(source.get("title", "")),
                ),
            )
            normalized = json.dumps(
                sorted_sources,
                ensure_ascii=True,
                sort_keys=True,
                default=str,
            )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _source_as_dict(self, source: Any) -> dict[str, Any]:
        if isinstance(source, dict):
            return source
        if hasattr(source, "model_dump"):
            value = source.model_dump(mode="json")
            return value if isinstance(value, dict) else {}
        return {
            "source_type": getattr(source, "source_type", ""),
            "url": getattr(source, "url", ""),
            "title": getattr(source, "title", ""),
            "summary": getattr(source, "summary", ""),
            "published_at": getattr(source, "published_at", None),
            "metadata": getattr(source, "metadata", {}),
        }

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
