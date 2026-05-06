"""MCP Server 配置模块。

通过环境变量控制 MCP Server 的启用状态和行为参数。
环境变量前缀：PLANAGENT_MCP_
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    """MCP Server 配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PLANAGENT_MCP_",
        extra="ignore",
    )

    # 是否启用 MCP Server
    enabled: bool = False

    # MCP Server 名称
    server_name: str = "MingJian MCP Server"

    # MCP Server 版本
    server_version: str = "0.1.0"

    # MCP 协议版本
    protocol_version: str = "2024-11-05"

    # 传输方式: "sse" 或 "streamable-http"
    transport: str = "sse"

    # 路由前缀
    route_prefix: str = "/mcp"

    # 最大并发连接数
    max_connections: int = 50

    # 请求超时（秒）
    request_timeout: float = 60.0

    # 是否启用工具调用日志
    log_tool_calls: bool = True
