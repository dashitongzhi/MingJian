from functools import lru_cache

from .auth import AuthSettings
from .database import DatabaseSettings
from .main import Settings
from .minio import MinioSettings
from .openai import OpenAIConfig, OpenAITargetConfig
from .redis import RedisSettings

__all__ = [
    "AuthSettings",
    "DatabaseSettings",
    "MinioSettings",
    "OpenAIConfig",
    "OpenAITargetConfig",
    "RedisSettings",
    "Settings",
    "get_settings",
    "reset_settings_cache",
]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
