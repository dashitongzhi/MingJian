"""MinIO / 对象存储配置子模型。"""

from pathlib import Path

from pydantic import BaseModel, Field


class MinioSettings(BaseModel):
    """MinIO 对象存储配置。"""

    endpoint: str = "localhost:9000"
    access_key: str = "planagent"
    secret_key: str = "planagent123"
    secure: bool = False
    bucket: str = "planagent-snapshots"
    snapshot_backend: str = "filesystem"
    snapshot_dir: Path = Field(default=Path("source_snapshots"))
