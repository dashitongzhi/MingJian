from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from planagent.config.auth import AuthSettings
from planagent.config.database import DatabaseSettings
from planagent.config.minio import MinioSettings
from planagent.config.redis import RedisSettings


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PLANAGENT_",
        env_nested_delimiter="_",
        env_nested_max_split=1,
        extra="ignore",
    )

    app_name: str = "PlanAgent"
    env: str = "development"
    database_url: str = "postgresql+psycopg://planagent:planagent@localhost:5432/planagent"
    redis_url: str = "redis://localhost:6379/0"
    event_bus_backend: str = "redis"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 300
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "planagent"
    minio_secret_key: str = "planagent123"
    minio_secure: bool = False
    minio_bucket: str = "planagent-snapshots"
    source_snapshot_backend: str = "filesystem"
    source_snapshot_dir: Path = Field(default=Path("source_snapshots"))
    additional_rss_feeds: str = ""
    source_failure_degraded_threshold: int = 5
    backpressure_pending_threshold: int = 1000
    graph_embedding_dimensions: int = 64
    analysis_cache_enabled: bool = True
    inline_ingest_default: bool = True
    inline_simulation_default: bool = True
    api_cache_ttl_seconds: int = 300
    stream_maxlen: int = 10000
    x_bearer_token: str | None = None
    x_base_url: str = "https://api.x.com/2"
    linux_do_base_url: str = "https://linux.do"
    xhs_provider_base_url: str | None = None
    xhs_provider_api_key: str | None = None
    douyin_provider_base_url: str | None = None
    douyin_provider_api_key: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    debate_advocate_provider: str = "openai"
    debate_challenger_provider: str = "anthropic"
    debate_arbitrator_provider: str = "openai"
    accepted_claim_confidence: float = 0.70
    review_claim_confidence_floor: float = 0.45
    source_snapshot_retention_days: int = 90
    report_retention_days: int = 30
    default_corporate_ticks: int = 6
    default_military_ticks: int = 8
    worker_lease_seconds: int = 60
    worker_max_attempts: int = 3
    stream_consumer_block_ms: int = 5000
    stream_consumer_count: int = 10
    sql_echo: bool = False
    rules_dir: Path = Field(default=Path("rules"))

    # MCP Server 配置
    mcp_enabled: bool = False

    # Auth 配置
    auth_secret_key: str = ""

    # Notification 配置
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "planagent@localhost"
    webhook_urls: list[str] = Field(default_factory=list)

    # Export 配置
    export_dir: str = "exports"

    # --- 结构化子模型访问器 ---
    # 提供 settings.db / settings.redis / settings.auth / settings.storage
    # 向后兼容：原有的 settings.database_url 等顶级属性仍可直接访问

    @property
    def db(self) -> DatabaseSettings:
        """数据库配置结构化访问。"""
        return DatabaseSettings(
            url=self.database_url,
            pool_size=self.db_pool_size,
            max_overflow=self.db_max_overflow,
            pool_recycle=self.db_pool_recycle,
            sql_echo=self.sql_echo,
        )

    @property
    def redis(self) -> RedisSettings:
        """Redis 配置结构化访问。"""
        return RedisSettings(
            url=self.redis_url,
            event_bus_backend=self.event_bus_backend,
            stream_maxlen=self.stream_maxlen,
        )

    @property
    def auth(self) -> AuthSettings:
        """认证配置结构化访问。"""
        return AuthSettings(
            secret_key=self.auth_secret_key,
        )

    @property
    def storage(self) -> MinioSettings:
        """MinIO / 存储配置结构化访问。"""
        return MinioSettings(
            endpoint=self.minio_endpoint,
            access_key=self.minio_access_key,
            secret_key=self.minio_secret_key,
            secure=self.minio_secure,
            bucket=self.minio_bucket,
            snapshot_backend=self.source_snapshot_backend,
            snapshot_dir=self.source_snapshot_dir,
        )
