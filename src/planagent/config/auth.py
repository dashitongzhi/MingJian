"""认证配置子模型。"""

from pydantic import BaseModel


class AuthSettings(BaseModel):
    """JWT / 认证相关配置。"""

    secret_key: str = ""
    token_expire_minutes: int = 60 * 24  # 默认 24 小时
