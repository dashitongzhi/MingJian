"""MCP Server 主入口。

将明鉴的核心能力暴露为 MCP 工具，通过 SSE 传输与外部 AI 客户端通信。

暴露的工具：
- submit_task — 提交决策任务（触发分析+辩论流程）
- get_debate_status — 查询辩论状态
- get_decision_result — 获取决策结果
- list_sources — 列出已配置数据源
- query_knowledge — 查询知识图谱
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select

from planagent.config import get_settings
from planagent.domain.enums import EventTopic, SimulationRunStatus
from planagent.domain.models import (
    DebateSessionRecord,
    DebateVerdictRecord,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    RawSourceItem,
    SimulationRun,
    UserDecision,
)
from planagent.mcp.config import MCPSettings
from planagent.mcp.protocol import MCPProtocolHandler, MCPTool, MCPToolParameter

logger = logging.getLogger(__name__)

router = APIRouter()

# ── MCP 协议处理器（模块级单例）──────────────────────────────────────

_mcp_handler: MCPProtocolHandler | None = None


def _get_mcp_settings() -> MCPSettings:
    return MCPSettings()


def _build_handler() -> MCPProtocolHandler:
    """构建并配置 MCP 协议处理器。"""
    mcp_settings = _get_mcp_settings()
    handler = MCPProtocolHandler(
        server_name=mcp_settings.server_name,
        server_version=mcp_settings.server_version,
        protocol_version=mcp_settings.protocol_version,
    )

    # ── 注册工具 ──────────────────────────────────────────────────────

    # 1. submit_task
    handler.register_tool(
        MCPTool(
            name="submit_task",
            description="提交决策任务。触发明鉴的数据采集、分析和辩论流程，返回任务 ID。",
            parameters=[
                MCPToolParameter(
                    name="query",
                    type="string",
                    description="决策问题或分析主题",
                    required=True,
                ),
                MCPToolParameter(
                    name="domain_id",
                    type="string",
                    description="领域标识（如 default、military、corporate）",
                    required=False,
                    default="default",
                ),
                MCPToolParameter(
                    name="source_types",
                    type="array",
                    description="指定数据源类型列表，为空则使用全部",
                    required=False,
                ),
            ],
        ),
        handler=handle_submit_task,
    )

    # 2. get_debate_status
    handler.register_tool(
        MCPTool(
            name="get_debate_status",
            description="查询辩论状态。根据辩论 ID 或关联的任务/模拟运行 ID 获取辩论进度。",
            parameters=[
                MCPToolParameter(
                    name="debate_id",
                    type="string",
                    description="辩论会话 ID",
                    required=False,
                ),
                MCPToolParameter(
                    name="run_id",
                    type="string",
                    description="关联的模拟运行 ID",
                    required=False,
                ),
                MCPToolParameter(
                    name="claim_id",
                    type="string",
                    description="关联的声明 ID",
                    required=False,
                ),
            ],
        ),
        handler=handle_get_debate_status,
    )

    # 3. get_decision_result
    handler.register_tool(
        MCPTool(
            name="get_decision_result",
            description="获取决策结果。返回辩论裁决、用户决策或模拟决策记录。",
            parameters=[
                MCPToolParameter(
                    name="run_id",
                    type="string",
                    description="模拟运行 ID",
                    required=False,
                ),
                MCPToolParameter(
                    name="debate_id",
                    type="string",
                    description="辩论会话 ID",
                    required=False,
                ),
                MCPToolParameter(
                    name="session_id",
                    type="string",
                    description="战略会话 ID（用户决策）",
                    required=False,
                ),
                MCPToolParameter(
                    name="limit",
                    type="integer",
                    description="返回条数上限",
                    required=False,
                    default=20,
                ),
            ],
        ),
        handler=handle_get_decision_result,
    )

    # 4. list_sources
    handler.register_tool(
        MCPTool(
            name="list_sources",
            description="列出已配置数据源。返回数据源类型、状态、健康度等信息。",
            parameters=[
                MCPToolParameter(
                    name="include_health",
                    type="boolean",
                    description="是否包含健康状态详情",
                    required=False,
                    default=True,
                ),
                MCPToolParameter(
                    name="source_type",
                    type="string",
                    description="按数据源类型过滤",
                    required=False,
                ),
            ],
        ),
        handler=handle_list_sources,
    )

    # 5. query_knowledge
    handler.register_tool(
        MCPTool(
            name="query_knowledge",
            description="查询知识图谱。按关键词搜索节点和关系，返回结构化知识。",
            parameters=[
                MCPToolParameter(
                    name="query",
                    type="string",
                    description="搜索关键词",
                    required=True,
                ),
                MCPToolParameter(
                    name="node_type",
                    type="string",
                    description="节点类型过滤（如 entity、event、concept）",
                    required=False,
                ),
                MCPToolParameter(
                    name="limit",
                    type="integer",
                    description="返回结果数量上限",
                    required=False,
                    default=20,
                ),
                MCPToolParameter(
                    name="include_edges",
                    type="boolean",
                    description="是否包含关联边",
                    required=False,
                    default=True,
                ),
            ],
        ),
        handler=handle_query_knowledge,
    )

    return handler


def get_mcp_handler() -> MCPProtocolHandler:
    """获取全局 MCP 协议处理器（延迟初始化）。"""
    global _mcp_handler
    if _mcp_handler is None:
        _mcp_handler = _build_handler()
    return _mcp_handler


# ── SSE 传输端点 ──────────────────────────────────────────────────────


@router.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request) -> StreamingResponse:
    """MCP SSE 传输 — 服务端事件流端点。

    客户端通过此端点建立 SSE 连接，服务器推送消息。
    客户端通过 POST /mcp/messages 发送请求。
    """
    import asyncio
    import uuid

    from starlette.responses import StreamingResponse

    session_id = str(uuid.uuid4())
    queue: asyncio.Queue[str] = asyncio.Queue()
    handler = get_mcp_handler()

    # 将队列注册到应用状态，供 messages 端点使用
    if not hasattr(request.app.state, "mcp_queues"):
        request.app.state.mcp_queues = {}
    request.app.state.mcp_queues[session_id] = queue

    logger.info("MCP SSE 连接建立: session=%s", session_id)

    async def event_stream():
        # 首先发送 endpoint 信息，告知客户端消息发送地址
        yield f"event: endpoint\ndata: /mcp/messages?session_id={session_id}\n\n"

        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"event: message\ndata: {message}\n\n"
                except asyncio.TimeoutError:
                    # 发送心跳保活
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            request.app.state.mcp_queues.pop(session_id, None)
            logger.info("MCP SSE 连接断开: session=%s", session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/mcp/messages")
async def mcp_messages_endpoint(
    request: Request,
    session_id: str | None = None,
) -> dict[str, Any]:
    """MCP SSE 传输 — 客户端消息接收端点。

    客户端通过 POST 请求发送 JSON-RPC 消息。
    响应通过 SSE 流推送回客户端。
    """
    if session_id is None:
        raise HTTPException(status_code=400, detail="缺少 session_id 参数")

    queues = getattr(request.app.state, "mcp_queues", None)
    if queues is None or session_id not in queues:
        raise HTTPException(status_code=404, detail="MCP 会话不存在")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="无效的 JSON 请求体")

    handler = get_mcp_handler()
    response = await handler.handle_message(body)

    if response is not None:
        queue = queues[session_id]
        await queue.put(json.dumps(response, ensure_ascii=False))

    return {"status": "ok"}


# ── Streamable HTTP 传输端点（MCP 2025-03-26+ 规范）───────────────────


@router.post("/mcp")
async def mcp_streamable_http_endpoint(request: Request) -> StreamingResponse:
    """MCP Streamable HTTP 传输端点。

    单一 POST 端点，请求和响应都在同一个 HTTP 连接中完成。
    对于非流式场景直接返回 JSON；对于流式场景返回 SSE。
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="无效的 JSON 请求体")

    handler = get_mcp_handler()

    # 检查是否请求流式响应
    accept = request.headers.get("accept", "")
    wants_stream = "text/event-stream" in accept

    if wants_stream:
        import asyncio

        async def stream_response():
            response = await handler.handle_message(body)
            if response is not None:
                yield f"data: {json.dumps(response, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    # 非流式：直接返回 JSON
    response = await handler.handle_message(body)
    if response is None:
        return {"status": "accepted"}
    return response


# ── 工具处理函数 ──────────────────────────────────────────────────────


async def handle_submit_task(
    query: str,
    domain_id: str = "default",
    source_types: list[str] | None = None,
) -> dict[str, Any]:
    """提交决策任务。触发分析流程。"""
    from planagent.db import get_database

    db = get_database()
    async with db.session() as session:
        # 创建模拟运行记录作为任务载体
        run = SimulationRun(
            domain_id=domain_id,
            actor_template="mcp_task",
            tick_count=1,
            seed=0,
            status=SimulationRunStatus.PENDING.value,
            configuration={
                "query": query,
                "source_types": source_types or [],
                "trigger": "mcp",
            },
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        # 发布事件以触发异步处理
        try:
            from planagent.events.bus import build_event_bus

            settings = get_settings()
            bus = build_event_bus(settings)
            await bus.publish(
                EventTopic.SIMULATION_COMPLETED.value,
                {
                    "simulation_run_id": run.id,
                    "query": query,
                    "domain_id": domain_id,
                    "source_types": source_types or [],
                    "trigger": "mcp_submit_task",
                },
            )
            await bus.close()
        except Exception as exc:
            logger.warning("发布 MCP 任务事件失败: %s", exc)

        return {
            "task_id": run.id,
            "status": "submitted",
            "query": query,
            "domain_id": domain_id,
            "message": "决策任务已提交，可通过 get_debate_status 或 get_decision_result 查询进度。",
        }


async def handle_get_debate_status(
    debate_id: str | None = None,
    run_id: str | None = None,
    claim_id: str | None = None,
) -> dict[str, Any]:
    """查询辩论状态。"""
    from planagent.db import get_database

    if not debate_id and not run_id and not claim_id:
        return {"error": "至少提供 debate_id、run_id 或 claim_id 之一"}

    db = get_database()
    async with db.session() as session:
        query = select(DebateSessionRecord)

        if debate_id:
            query = query.where(DebateSessionRecord.id == debate_id)
        elif run_id:
            query = query.where(DebateSessionRecord.run_id == run_id)
        elif claim_id:
            query = query.where(DebateSessionRecord.claim_id == claim_id)

        query = query.order_by(DebateSessionRecord.created_at.desc()).limit(10)
        sessions = list((await session.scalars(query)).all())

        if not sessions:
            return {
                "found": False,
                "message": "未找到匹配的辩论会话",
                "query_params": {
                    "debate_id": debate_id,
                    "run_id": run_id,
                    "claim_id": claim_id,
                },
            }

        results = []
        for s in sessions:
            result = {
                "debate_id": s.id,
                "topic": s.topic,
                "status": s.status,
                "trigger_type": s.trigger_type,
                "run_id": s.run_id,
                "claim_id": s.claim_id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }

            # 获取裁决摘要
            if s.verdict:
                result["verdict"] = {
                    "verdict": s.verdict.verdict if hasattr(s.verdict, "verdict") else None,
                    "confidence": s.verdict.confidence if hasattr(s.verdict, "confidence") else None,
                    "conclusion_summary": s.verdict.conclusion_summary[:200] if hasattr(s.verdict, "conclusion_summary") and s.verdict.conclusion_summary else None,
                }

            results.append(result)

        return {
            "found": True,
            "count": len(results),
            "debates": results,
        }


async def handle_get_decision_result(
    run_id: str | None = None,
    debate_id: str | None = None,
    session_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """获取决策结果。"""
    from planagent.db import get_database

    if not run_id and not debate_id and not session_id:
        return {"error": "至少提供 run_id、debate_id 或 session_id 之一"}

    db = get_database()
    async with db.session() as session:
        results: dict[str, Any] = {"decisions": [], "verdicts": [], "user_decisions": []}

        # 查询模拟决策记录
        if run_id:
            from planagent.domain.models import DecisionRecordRecord

            query = (
                select(DecisionRecordRecord)
                .where(DecisionRecordRecord.run_id == run_id)
                .order_by(DecisionRecordRecord.tick, DecisionRecordRecord.sequence)
                .limit(limit)
            )
            records = list((await session.scalars(query)).all())
            for rec in records:
                results["decisions"].append({
                    "id": rec.id,
                    "tick": rec.tick,
                    "actor_id": rec.actor_id,
                    "action_id": rec.action_id,
                    "why_selected": rec.why_selected,
                    "decision_method": rec.decision_method,
                    "expected_effect": rec.expected_effect,
                })

        # 查询辩论裁决
        if debate_id:
            query = (
                select(DebateVerdictRecord)
                .where(DebateVerdictRecord.debate_id == debate_id)
            )
            verdicts = list((await session.scalars(query)).all())
            for v in verdicts:
                results["verdicts"].append({
                    "id": v.id,
                    "verdict": v.verdict,
                    "confidence": v.confidence,
                    "conclusion_summary": v.conclusion_summary,
                    "rounds_completed": v.rounds_completed,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                })

        # 查询用户决策
        if session_id:
            query = (
                select(UserDecision)
                .where(UserDecision.session_id == session_id)
                .order_by(UserDecision.created_at.desc())
                .limit(limit)
            )
            user_decisions = list((await session.scalars(query)).all())
            for d in user_decisions:
                results["user_decisions"].append({
                    "id": d.id,
                    "decision": d.decision,
                    "notes": d.notes,
                    "outcome": d.outcome,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                })

        # 如果请求的是辩论裁决且未提供 debate_id，尝试用 run_id 查找
        if run_id and not results["verdicts"]:
            debate_query = (
                select(DebateSessionRecord)
                .where(DebateSessionRecord.run_id == run_id)
                .order_by(DebateSessionRecord.created_at.desc())
                .limit(1)
            )
            debate = (await session.scalars(debate_query)).first()
            if debate and debate.verdict:
                results["verdicts"].append({
                    "debate_id": debate.id,
                    "verdict": debate.verdict.verdict if hasattr(debate.verdict, "verdict") else None,
                    "confidence": debate.verdict.confidence if hasattr(debate.verdict, "confidence") else None,
                    "conclusion_summary": debate.verdict.conclusion_summary if hasattr(debate.verdict, "conclusion_summary") else None,
                })

        total = sum(len(v) if isinstance(v, list) else 0 for v in results.values())
        results["total"] = total
        return results


async def handle_list_sources(
    include_health: bool = True,
    source_type: str | None = None,
) -> dict[str, Any]:
    """列出已配置数据源。"""
    from planagent.db import get_database
    from planagent.domain.models import SourceHealth
    from planagent.services.sources.registry import SourceRegistry

    settings = get_settings()
    sources: list[dict[str, Any]] = []

    # 从 SourceRegistry 获取所有注册的数据源
    try:
        registry = SourceRegistry(settings)
        for provider in registry.all_providers():
            info: dict[str, Any] = {
                "key": provider.key,
                "label": provider.label,
                "agent_name": provider.agent_name,
                "available": provider.is_available() is None,
            }
            if provider.is_available() is not None:
                info["unavailable_reason"] = provider.is_available()
            if source_type and provider.key != source_type:
                continue
            sources.append(info)
    except Exception as exc:
        logger.warning("获取数据源列表失败: %s", exc)

    # 从数据库获取数据源统计
    db = get_database()
    async with db.session() as session:
        stats_query = (
            select(
                RawSourceItem.source_type,
                func.count(RawSourceItem.id).label("count"),
            )
            .group_by(RawSourceItem.source_type)
        )
        rows = (await session.execute(stats_query)).all()
        source_counts = {row[0]: row[1] for row in rows}

        # 健康状态
        health_map: dict[str, Any] = {}
        if include_health:
            health_query = select(SourceHealth)
            health_records = list((await session.scalars(health_query)).all())
            for h in health_records:
                health_map[h.source_type] = {
                    "status": h.status,
                    "consecutive_failures": h.consecutive_failures,
                    "last_error": h.last_error,
                    "last_success_at": h.last_success_at.isoformat() if h.last_success_at else None,
                }

    # 合并信息
    result_sources: list[dict[str, Any]] = []
    for src in sources:
        key = src["key"]
        src["item_count"] = source_counts.get(key, 0)
        if include_health and key in health_map:
            src["health"] = health_map[key]
        result_sources.append(src)

    # 添加数据库中存在但 registry 中没有的来源
    for source_type, count in source_counts.items():
        if not any(s["key"] == source_type for s in result_sources):
            entry: dict[str, Any] = {
                "key": source_type,
                "label": source_type,
                "item_count": count,
                "available": True,
            }
            if include_health and source_type in health_map:
                entry["health"] = health_map[source_type]
            result_sources.append(entry)

    return {
        "total": len(result_sources),
        "sources": result_sources,
    }


async def handle_query_knowledge(
    query: str,
    node_type: str | None = None,
    limit: int = 20,
    include_edges: bool = True,
) -> dict[str, Any]:
    """查询知识图谱。"""
    from planagent.db import get_database

    db = get_database()
    async with db.session() as session:
        # 搜索节点 — 按 label 模糊匹配
        node_query = select(KnowledgeGraphNode).where(
            KnowledgeGraphNode.label.ilike(f"%{query}%")
        )
        if node_type:
            node_query = node_query.where(KnowledgeGraphNode.node_type == node_type)
        node_query = node_query.limit(limit)

        nodes = list((await session.scalars(node_query)).all())

        node_results = []
        node_keys: set[str] = set()
        for node in nodes:
            node_keys.add(node.node_key)
            node_results.append({
                "node_key": node.node_key,
                "label": node.label,
                "node_type": node.node_type,
                "source_table": node.source_table,
                "source_id": node.source_id,
                "metadata": node.node_metadata,
            })

        # 搜索关联边
        edge_results: list[dict[str, Any]] = []
        if include_edges and node_keys:
            edge_query = select(KnowledgeGraphEdge).where(
                or_(
                    KnowledgeGraphEdge.source_node_key.in_(list(node_keys)),
                    KnowledgeGraphEdge.target_node_key.in_(list(node_keys)),
                )
            ).limit(limit * 3)
            edges = list((await session.scalars(edge_query)).all())
            for edge in edges:
                edge_results.append({
                    "source": edge.source_node_key,
                    "target": edge.target_node_key,
                    "relation": edge.relation_type,
                    "metadata": edge.edge_metadata,
                })

        return {
            "query": query,
            "node_count": len(node_results),
            "edge_count": len(edge_results),
            "nodes": node_results,
            "edges": edge_results if include_edges else [],
        }
