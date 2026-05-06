"""MCP 协议消息处理模块。

实现 MCP (Model Context Protocol) 2024-11-05 规范的核心消息处理逻辑。
参考规范：https://spec.modelcontextprotocol.io/

支持的方法：
- initialize / initialized — 握手
- tools/list — 列出可用工具
- tools/call — 调用工具
- ping — 心跳检测
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── MCP JSON-RPC 消息结构 ─────────────────────────────────────────────


@dataclass(frozen=True)
class MCPRequest:
    """MCP JSON-RPC 请求。"""

    jsonrpc: str = "2.0"
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    id: int | str | None = None


@dataclass
class MCPResponse:
    """MCP JSON-RPC 响应。"""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


@dataclass
class MCPNotification:
    """MCP JSON-RPC 通知（无 id）。"""

    jsonrpc: str = "2.0"
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)


# ── 工具定义 ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MCPToolParameter:
    """工具参数定义。"""

    name: str
    type: str
    description: str
    required: bool = False
    enum: list[str] | None = None
    default: Any = None


@dataclass(frozen=True)
class MCPTool:
    """MCP 工具定义。"""

    name: str
    description: str
    parameters: list[MCPToolParameter] = field(default_factory=list)

    def to_schema(self) -> dict[str, Any]:
        """转换为 MCP tools/list 返回格式。"""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {"type": param.type, "description": param.description}
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                **({"required": required} if required else {}),
            },
        }


# ── 协议处理器 ───────────────────────────────────────────────────────


class MCPProtocolHandler:
    """MCP 协议消息处理器。

    负责解析 JSON-RPC 消息、路由到对应的处理器、构造响应。
    """

    def __init__(
        self,
        server_name: str,
        server_version: str,
        protocol_version: str,
    ) -> None:
        self._server_name = server_name
        self._server_version = server_version
        self._protocol_version = protocol_version
        self._tools: dict[str, MCPTool] = {}
        self._tool_handlers: dict[str, Any] = {}
        self._initialized = False

    # ── 注册工具 ──────────────────────────────────────────────────────

    def register_tool(self, tool: MCPTool, handler: Any) -> None:
        """注册一个 MCP 工具及其处理函数。"""
        self._tools[tool.name] = tool
        self._tool_handlers[tool.name] = handler
        logger.debug("注册 MCP 工具: %s", tool.name)

    # ── 消息分发 ──────────────────────────────────────────────────────

    async def handle_message(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """处理一条 JSON-RPC 消息。

        返回响应字典（请求时返回响应，通知时返回 None）。
        """
        method = raw.get("method", "")
        msg_id = raw.get("id")
        params = raw.get("params", {})

        # 通知（无 id）不需要响应
        if msg_id is None and method:
            await self._handle_notification(method, params)
            return None

        # 请求（有 id）需要响应
        try:
            result = await self._dispatch(method, params)
            return MCPResponse(jsonrpc="2.0", id=msg_id, result=result).__dict__
        except MCPError as exc:
            return MCPResponse(
                jsonrpc="2.0",
                id=msg_id,
                error=exc.to_dict(),
            ).__dict__
        except Exception as exc:
            logger.exception("处理 MCP 消息异常: method=%s", method)
            return MCPResponse(
                jsonrpc="2.0",
                id=msg_id,
                error={"code": -32603, "message": f"内部错误: {exc}"},
            ).__dict__

    async def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """路由到具体方法处理器。"""
        if method == "initialize":
            return await self._handle_initialize(params)
        if method == "tools/list":
            return await self._handle_tools_list(params)
        if method == "tools/call":
            return await self._handle_tools_call(params)
        if method == "ping":
            return {}
        raise MCPError(code=-32601, message=f"未知方法: {method}")

    async def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        """处理通知消息（无需响应）。"""
        if method == "notifications/initialized":
            self._initialized = True
            logger.info("MCP 客户端已完成初始化握手")
        else:
            logger.debug("收到 MCP 通知: %s", method)

    # ── 方法实现 ──────────────────────────────────────────────────────

    async def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """处理 initialize 请求 — 返回服务器能力声明。"""
        return {
            "protocolVersion": self._protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
                "logging": {},
            },
            "serverInfo": {
                "name": self._server_name,
                "version": self._server_version,
            },
        }

    async def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """处理 tools/list 请求 — 返回所有注册工具的定义。"""
        tools = [tool.to_schema() for tool in self._tools.values()]
        return {"tools": tools}

    async def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """处理 tools/call 请求 — 调用指定工具。"""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in self._tool_handlers:
            raise MCPError(
                code=-32602,
                message=f"未知工具: {tool_name}",
            )

        handler = self._tool_handlers[tool_name]
        logger.info("MCP 工具调用: %s(%s)", tool_name, list(arguments.keys()))

        try:
            result = await handler(**arguments)
            # 确保返回标准 MCP content 格式
            if isinstance(result, dict) and "content" in result:
                return result
            return {
                "content": [
                    {
                        "type": "text",
                        "text": _serialize_result(result),
                    }
                ]
            }
        except TypeError as exc:
            raise MCPError(
                code=-32602,
                message=f"工具参数错误: {exc}",
            ) from exc


# ── 异常定义 ──────────────────────────────────────────────────────────


class MCPError(Exception):
    """MCP 协议错误。"""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        """转换为 JSON-RPC error 格式。"""
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err


# ── 辅助函数 ──────────────────────────────────────────────────────────


def _serialize_result(result: Any) -> str:
    """将工具返回值序列化为文本。"""
    if isinstance(result, str):
        return result
    try:
        import json

        return json.dumps(result, ensure_ascii=False, default=str, indent=2)
    except Exception:
        return str(result)
