"""Redis / 事件总线配置子模型。"""

from pydantic import BaseModel


class RedisSettings(BaseModel):
    """Redis 连接与事件总线配置。"""

    url: str
    event_bus_backend: str
    stream_maxlen: int
    stream_pending_idle_ms: int = 60000
    stream_retry_base_seconds: float = 1.0
