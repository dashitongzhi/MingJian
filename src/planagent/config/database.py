"""数据库配置子模型。"""

from pydantic import BaseModel


class DatabaseSettings(BaseModel):
    """数据库连接与连接池配置。

    从 BaseAppSettings 的扁平字段构造，提供结构化访问。
    """

    url: str
    pool_size: int
    max_overflow: int
    pool_recycle: int
    sql_echo: bool
