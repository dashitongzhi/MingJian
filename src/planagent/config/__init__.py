from functools import lru_cache

from .main import Settings
from .openai import OpenAIConfig, OpenAITargetConfig

__all__ = ["Settings", "get_settings", "reset_settings_cache", "OpenAIConfig", "OpenAITargetConfig"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
