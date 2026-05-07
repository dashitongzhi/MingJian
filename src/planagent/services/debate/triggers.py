from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from planagent.domain.api import DebateTriggerRequest
from planagent.domain.enums import EventTopic
from planagent.domain.models import EventArchive


class DebateTriggerMixin:
    @staticmethod
    def auto_detect_disagreement(
        agent_assessments: list[dict[str, Any]],
        confidence_threshold: float = 0.30,
    ) -> dict[str, Any]:
        """分析各 Agent 的初始评估，检测是否需要自动触发辩论。

        触发条件：
        1. 置信度差异 > confidence_threshold（默认30%）
        2. 立场对立（SUPPORT vs OPPOSE）

        Args:
            agent_assessments: 每个 Agent 的评估结果列表，格式:
                [{"role": str, "position": str, "confidence": float, "arguments": list}]
            confidence_threshold: 置信度差异阈值（默认0.30）

        Returns:
            {
                "should_trigger": bool,
                "trigger_reasons": list[str],
                "confidence_spread": float,
                "position_conflicts": list[dict],
                "disagreement_details": dict,
            }
        """
        if len(agent_assessments) < 2:
            return {
                "should_trigger": False,
                "trigger_reasons": [],
                "confidence_spread": 0.0,
                "position_conflicts": [],
                "disagreement_details": {},
            }

        trigger_reasons: list[str] = []
        position_conflicts: list[dict[str, Any]] = []

        # 1. 置信度差异检测
        confidences = [a.get("confidence", 0.5) for a in agent_assessments]
        confidence_spread = max(confidences) - min(confidences) if confidences else 0.0

        if confidence_spread > confidence_threshold:
            trigger_reasons.append(
                f"置信度差异 {confidence_spread:.1%} 超过阈值 {confidence_threshold:.0%}"
            )

        # 2. 立场对立检测
        support_agents = [
            a for a in agent_assessments if a.get("position", "").upper() == "SUPPORT"
        ]
        oppose_agents = [a for a in agent_assessments if a.get("position", "").upper() == "OPPOSE"]

        if support_agents and oppose_agents:
            trigger_reasons.append(
                f"立场对立：{len(support_agents)}个SUPPORT vs {len(oppose_agents)}个OPPOSE"
            )
            position_conflicts = [
                {
                    "support": [a["role"] for a in support_agents],
                    "oppose": [a["role"] for a in oppose_agents],
                    "support_avg_confidence": (
                        sum(a.get("confidence", 0.5) for a in support_agents) / len(support_agents)
                    ),
                    "oppose_avg_confidence": (
                        sum(a.get("confidence", 0.5) for a in oppose_agents) / len(oppose_agents)
                    ),
                }
            ]

        # 3. 跨域矛盾检测：同一领域不同角色的结论差异
        disagreement_details: dict[str, Any] = {
            "agent_positions": [
                {
                    "role": a.get("role", "unknown"),
                    "position": a.get("position", "CONDITIONAL"),
                    "confidence": a.get("confidence", 0.5),
                    "key_argument": (
                        a.get("arguments", [{}])[0].get("claim", "") if a.get("arguments") else ""
                    ),
                }
                for a in agent_assessments
            ],
        }

        should_trigger = len(trigger_reasons) > 0

        return {
            "should_trigger": should_trigger,
            "trigger_reasons": trigger_reasons,
            "confidence_spread": confidence_spread,
            "position_conflicts": position_conflicts,
            "disagreement_details": disagreement_details,
        }

    async def check_and_trigger_auto_debate(
        self,
        session: AsyncSession,
        run_id: str,
        topic: str,
        agent_assessments: list[dict[str, Any]],
        context_lines: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """检测分歧并自动触发辩论。

        如果检测到分歧，自动创建一个辩论会话并发布事件。
        返回辩论结果或 None（如果没有分歧）。
        """
        detection = self.auto_detect_disagreement(agent_assessments)

        if not detection["should_trigger"]:
            return None

        # 发布自动触发事件
        trigger_event_payload = {
            "run_id": run_id,
            "topic": topic,
            "trigger_reasons": detection["trigger_reasons"],
            "confidence_spread": detection["confidence_spread"],
            "position_conflicts": detection["position_conflicts"],
        }
        session.add(
            EventArchive(topic=EventTopic.DEBATE_AUTO_TRIGGER.value, payload=trigger_event_payload)
        )

        # 构造辩论请求
        payload = DebateTriggerRequest(
            run_id=run_id,
            topic=f"[自动触发] {topic}",
            trigger_type="auto_conflict_detection",
            target_type="run",
            context_lines=[
                *(context_lines or []),
                f"自动触发原因：{'; '.join(detection['trigger_reasons'])}",
                f"置信度分布：{detection['disagreement_details']}",
            ],
        )

        # 执行辩论
        debate_result = await self.trigger_debate(session, payload)
        await self.event_bus.publish(EventTopic.DEBATE_AUTO_TRIGGER.value, trigger_event_payload)

        return {
            "debate": debate_result,
            "detection": detection,
        }
