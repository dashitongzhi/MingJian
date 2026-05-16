from __future__ import annotations

import hashlib
import json
from typing import Any, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings
from planagent.services.openai_client import resolve_openclaw_model_selector
from planagent.services.providers.openai_provider import OpenAIProvider

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
            old_content_text = await self._load_old_content(
                session,
                state.last_seen_raw_source_item_id,
            )
            semantic_summary = await self._compute_semantic_diff_summary(
                topic=new_title,
                old_content=old_content_text or f"上一版本内容哈希：{old_hash}",
                new_content=new_content_text,
            )
            significance = await self._compute_significance(
                old_hash=old_hash,
                new_hash=stable_new_hash,
                old_content_text=old_content_text,
                new_content_text=new_content_text,
                new_title=new_title,
                semantic_summary=semantic_summary,
            )
            diff_summary = semantic_summary or self._compute_diff_summary(
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

    async def _compute_significance(
        self,
        old_hash: str,
        new_hash: str | None,
        old_content_text: str,
        new_content_text: str,
        new_title: str,
        semantic_summary: str | None = None,
    ) -> str:
        """计算变化重要性。"""
        _ = new_hash
        old_content = old_content_text or f"上一版本内容哈希：{old_hash}"
        try:
            return await self._assess_significance_llm(
                topic=new_title,
                old_content=old_content,
                new_content=new_content_text,
                semantic_summary=semantic_summary,
            )
        except Exception:
            return self._compute_significance_by_heuristics(new_content_text, semantic_summary)

    async def _assess_significance_llm(
        self,
        topic: str,
        old_content: str,
        new_content: str,
        semantic_summary: str | None = None,
    ) -> str:
        """使用 LLM 评估变化的语义重要性。"""
        provider = OpenAIProvider(
            api_key=self.settings.resolved_openai_extraction_api_key,
            base_url=self.settings.resolved_openai_extraction_base_url,
            timeout=self.settings.openai_timeout_seconds,
        )
        try:
            response = await provider.generate_text(
                model=resolve_openclaw_model_selector(
                    self.settings.resolved_openai_extraction_model
                ),
                system_prompt="你是一个情报分析师。请严格按要求输出。",
                user_prompt=(
                    f'你是一个情报分析师。请评估以下关于"{topic}"的内容变更的重要程度。\n'
                    f"旧内容摘要：{old_content[:500]}\n"
                    f"新内容摘要：{new_content[:500]}\n"
                    f"初步变化摘要：{(semantic_summary or '')[:300]}\n"
                    "请判断：这个变更是否包含重大新信息、关键数据变化、或立场转变？\n"
                    "只回复一个词：high / medium / low"
                ),
                max_tokens=8,
                temperature=0.0,
            )
            if response is None:
                raise RuntimeError("LLM significance assessment returned no response.")

            significance = response.text.strip().lower().strip("`。.,;: \n\t")
            if significance in {"high", "medium", "low"}:
                return significance

            first_word = significance.split(maxsplit=1)[0] if significance else ""
            if first_word in {"high", "medium", "low"}:
                return first_word
            raise ValueError(f"Invalid LLM significance value: {response.text[:100]}")
        finally:
            await provider.close()

    async def _compute_semantic_diff_summary(
        self,
        topic: str,
        old_content: str,
        new_content: str,
    ) -> str | None:
        """Generate a short semantic change summary for downstream debate/recommendations."""
        if not new_content.strip():
            return None
        provider = OpenAIProvider(
            api_key=self.settings.resolved_openai_extraction_api_key,
            base_url=self.settings.resolved_openai_extraction_base_url,
            timeout=self.settings.openai_timeout_seconds,
        )
        try:
            response = await provider.generate_text(
                model=resolve_openclaw_model_selector(
                    self.settings.resolved_openai_extraction_model
                ),
                system_prompt="你是一个情报变更摘要器。请输出一句中文摘要。",
                user_prompt=(
                    f'主题："{topic}"\n'
                    f"旧内容：{old_content[:700]}\n"
                    f"新内容：{new_content[:900]}\n"
                    "用一句话说明语义上发生了什么变化，包含影响对象和可能决策含义；不要超过80字。"
                ),
                max_tokens=120,
                temperature=0.0,
            )
            if response is None:
                return None
            summary = " ".join(response.text.strip().split())
            return summary[:240] or None
        except Exception:
            return self._heuristic_semantic_summary(new_content)
        finally:
            await provider.close()

    def _compute_significance_by_heuristics(
        self,
        new_content_text: str,
        semantic_summary: str | None,
    ) -> str:
        """Fallback semantic heuristic for burst/change severity."""
        text = f"{semantic_summary or ''}\n{new_content_text}".lower()
        high_terms = [
            "突发",
            "重大",
            "紧急",
            "中断",
            "禁令",
            "制裁",
            "攻击",
            "事故",
            "爆发",
            "crisis",
            "ban",
            "sanction",
            "attack",
            "outage",
            "breach",
            "lawsuit",
        ]
        medium_terms = [
            "更新",
            "调整",
            "增长",
            "下降",
            "延迟",
            "发布",
            "融资",
            "contract",
            "launch",
            "delay",
            "growth",
        ]
        if any(term in text for term in high_terms):
            return "high"
        if any(term in text for term in medium_terms):
            return "medium"
        content_length = len(new_content_text.strip())
        if content_length >= 2000:
            return "high"
        if content_length >= 400:
            return "medium"
        return "low"

    def _heuristic_semantic_summary(self, new_content_text: str) -> str | None:
        cleaned = " ".join(new_content_text.strip().split())
        if not cleaned:
            return None
        return f"检测到新内容更新：{cleaned[:120]}"

    async def _load_old_content(
        self,
        session: AsyncSession,
        old_raw_source_item_id: str | None,
    ) -> str:
        """读取上一次原始内容，用于 LLM 比较。"""
        if not old_raw_source_item_id:
            return ""

        from planagent.domain.models import RawSourceItem

        raw_item = await session.get(RawSourceItem, old_raw_source_item_id)
        return raw_item.content_text if raw_item is not None else ""

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
