from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.config import Settings


class EvidenceWeightingService:
    """证据加权服务——基于来源可信度动态调整证据权重"""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def get_source_trust(
        self, session: AsyncSession, source_url: str
    ) -> float:
        """获取来源的可信度分数"""
        from planagent.domain.models import SourceTrustScore

        try:
            domain = urlparse(source_url).netloc
        except Exception:
            return 0.5

        score = (
            await session.scalars(
                select(SourceTrustScore)
                .where(SourceTrustScore.source_url_pattern == domain)
                .limit(1)
            )
        ).first()

        return score.trust_score if score else 0.5

    async def adjust_claim_confidence(
        self,
        session: AsyncSession,
        claim_confidence: float,
        source_url: str,
    ) -> float:
        """根据来源可信度调整Claim置信度"""
        trust = await self.get_source_trust(session, source_url)
        adjustment = 0.5 + 0.5 * trust
        return min(1.0, claim_confidence * adjustment)

    async def get_evidence_context(
        self, session: AsyncSession, evidence_ids: list[str]
    ) -> str:
        """为推演生成带可信度标注的证据上下文"""
        from planagent.domain.models import EvidenceItem

        parts = []
        for eid in evidence_ids[:20]:
            evidence = await session.get(EvidenceItem, eid)
            if not evidence:
                continue
            trust = await self.get_source_trust(session, evidence.source_url)
            trust_label = "🟢高可信" if trust >= 0.7 else "🟡中可信" if trust >= 0.4 else "🔴低可信"
            parts.append(
                f"[{trust_label} 来源可信度:{trust:.0%}] {evidence.title}: {evidence.summary[:200]}"
            )

        return "\n".join(parts)
