from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.enums import EventTopic
from planagent.domain.models import DebateStructuredDissent, EventArchive


class DebateRevisionMixin:
    @staticmethod
    def detect_overturned_arguments(
        rounds: list[dict[str, Any]],
        overturn_threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """分析辩论轮次，检测被有效推翻的论点。

        被推翻的判定标准：
        1. 某 Agent 在修订轮中的置信度显著下降（> overturn_threshold）
        2. 某 Agent 明确放弃（❌放弃）了之前的论点
        3. 某 Agent 的立场从 SUPPORT 变为 OPPOSE/CONDITIONAL（或反之）

        Args:
            rounds: 辩论轮次列表
            overturn_threshold: 置信度下降阈值

        Returns:
            被推翻的论点列表，每项包含:
            [{"role": str, "original_confidence": float, "revised_confidence": float,
              "overturned_claims": list[str], "revision_needed": bool}]
        """
        if not rounds:
            return []

        # 按角色分组轮次
        rounds_by_role: dict[str, list[dict[str, Any]]] = {}
        for r in rounds:
            role = r.get("role", "unknown")
            rounds_by_role.setdefault(role, []).append(r)

        overturned: list[dict[str, Any]] = []

        for role, role_rounds in rounds_by_role.items():
            if len(role_rounds) < 2:
                continue

            # 按轮次排序
            role_rounds.sort(key=lambda x: x.get("round_number", 0))
            first_round = role_rounds[0]
            last_round = role_rounds[-1]

            first_conf = float(first_round.get("confidence", 0.5))
            last_conf = float(last_round.get("confidence", 0.5))
            conf_drop = first_conf - last_conf

            # 检测置信度显著下降
            confidence_overturned = conf_drop > overturn_threshold

            # 检测明确放弃的论点
            overturned_claims: list[str] = []
            for concession in last_round.get("concessions", []):
                reason = concession.get("reason", "")
                if reason:
                    overturned_claims.append(reason)

            # 检测立场翻转
            first_position = first_round.get("position", "CONDITIONAL").upper()
            last_position = last_round.get("position", "CONDITIONAL").upper()
            position_flipped = (first_position == "SUPPORT" and last_position == "OPPOSE") or (
                first_position == "OPPOSE" and last_position == "SUPPORT"
            )

            if confidence_overturned or overturned_claims or position_flipped:
                overturned.append(
                    {
                        "role": role,
                        "original_confidence": first_conf,
                        "revised_confidence": last_conf,
                        "confidence_drop": conf_drop,
                        "position_flipped": position_flipped,
                        "original_position": first_position,
                        "revised_position": last_position,
                        "overturned_claims": overturned_claims,
                        "revision_needed": True,
                    }
                )

        return overturned

    def generate_revision_prompt(
        self,
        role: str,
        original_position: str,
        revised_position: str,
        overturned_claims: list[str],
        confidence_drop: float,
    ) -> str:
        """为被推翻的 Agent 生成修订提示。

        该提示在下一轮辩论中注入，要求 Agent 重新评估。
        """
        claims_text = (
            "\n".join(f"- {c}" for c in overturned_claims)
            if overturned_claims
            else "（无明确放弃记录）"
        )

        return (
            f"【立场修订通知】\n"
            f"你（{role}）在之前的辩论中被有效推翻：\n"
            f"- 原始立场: {original_position} → 修订后: {revised_position}\n"
            f"- 置信度变化: {confidence_drop:.1%} 下降\n"
            f"- 被推翻/放弃的论点:\n{claims_text}\n\n"
            f"请执行以下修订操作：\n"
            f"1. 重新审视你的核心论点，评估哪些仍然成立\n"
            f"2. 对被推翻的论点，要么提供新的反驳证据，要么正式承认并解释原因\n"
            f"3. 补充新的证据或推理来支撑仍然成立的部分\n"
            f"4. 明确更新你的置信度和立场\n"
            f"5. 如果确实需要改变立场，请诚实地做出调整\n\n"
            f"你的目标不是固守，而是在压力测试中让分析更加精确可靠。"
        )

    # ------------------------------------------------------------------
    # Structured minority dissent
    # ------------------------------------------------------------------

    _DISSENT_CATEGORIES: dict[str, str] = {
        "risk": "风险识别",
        "evidence_quality": "证据质量",
        "alternative": "替代方案",
        "assumption_challenge": "假设质疑",
    }

    def _categorise_claim(self, text: str) -> str:
        """Heuristic: pick the most likely dissent category for *text*."""
        lower = text.lower()
        # Order matters — first match wins
        if any(kw in lower for kw in ("risk", "danger", "风险", "危害", "威胁")):
            return "risk"
        if any(kw in lower for kw in ("evidence", "数据", "来源", "source", "cite", "证据")):
            return "evidence_quality"
        if any(kw in lower for kw in ("alternative", "替代", "方案", "option", "建议")):
            return "alternative"
        if any(kw in lower for kw in ("assume", "假设", "premise", "前提")):
            return "assumption_challenge"
        # Default fallback: assumption_challenge is the most general
        return "assumption_challenge"

    def _extract_topic_keywords(self, rounds: list[dict[str, Any]]) -> list[str]:
        """Extract salient keywords from debate topic / round summaries."""
        seen: set[str] = set()
        keywords: list[str] = []
        for r in rounds:
            text = r.get("topic", "") or r.get("summary", "") or ""
            for word in text.split():
                w = word.strip("，。、；：""''（）《》【】,.:;!?()[]{}")
                if len(w) >= 2 and w not in seen:
                    seen.add(w)
                    keywords.append(w)
        return keywords

    async def generate_structured_dissent(
        self,
        debate_id: str,
        round_records: list[dict[str, Any]],
        dissenter_role: str,
        db: AsyncSession,
    ) -> DebateStructuredDissent:
        """Build a structured dissent object from debate round records.

        Collects OPPOSE/challenger arguments into categorised claims,
        extracts evidence gaps, tracks confidence trajectory, and
        recommends monitoring items.
        """

        # 1. Collect challenger / OPPOSE arguments across rounds
        claims: list[dict[str, Any]] = []
        seen_claims: set[str] = set()
        evidence_gaps: list[str] = []
        confidence_trajectory: list[float] = []

        for rec in round_records:
            role = rec.get("role", "")
            position = (rec.get("position", "") or "").upper()

            # Track confidence trajectory for the dissenter
            if role == dissenter_role:
                conf = float(rec.get("confidence", 0.5))
                confidence_trajectory.append(conf)

            # Only collect challenger / OPPOSE arguments
            if role != dissenter_role or position not in ("OPPOSE", "CONDITIONAL"):
                continue

            arguments = rec.get("arguments", []) or []
            for arg in arguments:
                claim_text = arg if isinstance(arg, str) else arg.get("claim", str(arg))
                if claim_text in seen_claims:
                    continue
                seen_claims.add(claim_text)

                # Gather evidence attached to the argument
                evidence: list[str] = []
                if isinstance(arg, dict):
                    evidence = arg.get("evidence", []) or []

                claim_confidence = float(rec.get("confidence", 0.5))
                category = self._categorise_claim(claim_text)

                claims.append({
                    "claim": claim_text,
                    "evidence": evidence,
                    "confidence": claim_confidence,
                    "category": category,
                })

                if not evidence:
                    evidence_gaps.append(claim_text)

        # 2. Generate monitoring recommendations from topic keywords
        topic_keywords = self._extract_topic_keywords(round_records)
        recommended_monitoring: list[str] = []
        for kw in topic_keywords[:10]:
            recommended_monitoring.append(f"持续追踪「{kw}」相关新证据与进展")

        # 3. Overall dissent strength: average confidence of claims
        overall_dissent_strength = (
            sum(c["confidence"] for c in claims) / len(claims) if claims else 0.0
        )

        return DebateStructuredDissent(
            debate_id=debate_id,
            dissenter_role=dissenter_role,
            claims=claims,
            evidence_gaps=evidence_gaps,
            confidence_trajectory=confidence_trajectory,
            recommended_monitoring=recommended_monitoring,
            overall_dissent_strength=overall_dissent_strength,
        )

    async def persist_structured_dissent(
        self,
        dissent: DebateStructuredDissent,
        db: AsyncSession,
    ) -> None:
        """Persist a structured dissent object to the database."""
        db.add(dissent)
        await db.flush()

    async def check_and_apply_revisions(
        self,
        session: AsyncSession,
        debate_id: str,
        rounds: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """在辩论完成后检查是否需要立场修订，生成修订记录。

        修订记录保存到辩论历史中（EventArchive）。
        返回修订记录列表。
        """
        overturned = self.detect_overturned_arguments(rounds)

        # Persist structured dissent for the primary dissenter
        if overturned:
            # Pick the dissenter: the OPPOSE role with the largest confidence drop
            dissenter = max(overturned, key=lambda o: o.get("confidence_drop", 0.0))
            dissent_obj = await self.generate_structured_dissent(
                debate_id=debate_id,
                round_records=rounds,
                dissenter_role=dissenter["role"],
                db=session,
            )
            await self.persist_structured_dissent(dissent_obj, session)

        if not overturned:
            return []

        revision_records: list[dict[str, Any]] = []

        for item in overturned:
            revision_prompt = self.generate_revision_prompt(
                role=item["role"],
                original_position=item["original_position"],
                revised_position=item["revised_position"],
                overturned_claims=item["overturned_claims"],
                confidence_drop=item["confidence_drop"],
            )

            revision_record = {
                "debate_id": debate_id,
                "role": item["role"],
                "original_confidence": item["original_confidence"],
                "revised_confidence": item["revised_confidence"],
                "confidence_drop": item["confidence_drop"],
                "position_flipped": item["position_flipped"],
                "original_position": item["original_position"],
                "revised_position": item["revised_position"],
                "overturned_claims": item["overturned_claims"],
                "revision_prompt": revision_prompt,
            }
            revision_records.append(revision_record)

            # 保存修订事件到事件归档
            session.add(
                EventArchive(
                    topic=EventTopic.DEBATE_REVISION.value,
                    payload={
                        "debate_id": debate_id,
                        "role": item["role"],
                        "confidence_drop": item["confidence_drop"],
                        "position_flipped": item["position_flipped"],
                        "overturned_claims_count": len(item["overturned_claims"]),
                    },
                )
            )

        await self.event_bus.publish(
            EventTopic.DEBATE_REVISION.value,
            {
                "debate_id": debate_id,
                "revisions_count": len(revision_records),
                "revised_roles": [r["role"] for r in revision_records],
            },
        )

        return revision_records
