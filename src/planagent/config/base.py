from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
