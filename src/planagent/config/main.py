import os
import re

from pydantic import Field, model_validator

from .base import BaseAppSettings
from .openai import (
    OpenAIConfig,
    TARGET_NAMES,
    TARGET_MODEL_DEFAULTS,
    resolve_api_key,
    resolve_base_url,
    resolve_model,
    api_key_source,
    base_url_source,
    model_source,
)

_TARGET_FIELD_RE = re.compile(
    r"^(?:resolved_)?openai_(.+)_(model|api_key|base_url)$"
)


class Settings(BaseAppSettings):
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)

    @model_validator(mode="before")
    @classmethod
    def collect_flat_openai_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        data = dict(data)
        openai_data = data.get("openai")
        if not isinstance(openai_data, dict):
            openai_data = {}
        else:
            openai_data = dict(openai_data)

        shared_fields = {
            "openai_api_key": "shared_api_key",
            "openai_base_url": "shared_base_url",
            "openai_timeout_seconds": "timeout_seconds",
        }
        field_names = ("model", "api_key", "base_url")

        for flat_key, nested_key in shared_fields.items():
            if flat_key in data:
                openai_data[nested_key] = data.pop(flat_key)

        for target_name in TARGET_NAMES:
            target_data = openai_data.get(target_name)
            if not isinstance(target_data, dict):
                target_data = {}
            else:
                target_data = dict(target_data)

            for field_name in field_names:
                flat_key = f"openai_{target_name}_{field_name}"
                if flat_key in data:
                    target_data[field_name] = data.pop(flat_key)

            if target_data:
                openai_data[target_name] = target_data

        if openai_data:
            data["openai"] = openai_data
        else:
            data.setdefault("openai", {})

        return data

    def __getattr__(self, name: str):
        openai = object.__getattribute__(self, "openai")
        if openai is None:
            raise AttributeError(name)

        m = _TARGET_FIELD_RE.match(name)
        if m:
            target, field = m.group(1), m.group(2)
            if target in TARGET_NAMES:
                if name.startswith("resolved_"):
                    if field == "model":
                        return resolve_model(openai, target)
                    if field == "api_key":
                        return resolve_api_key(openai, target)
                    return resolve_base_url(openai, target)
                val = getattr(getattr(openai, target), field)
                if val is None and field == "model" and target in TARGET_MODEL_DEFAULTS:
                    return TARGET_MODEL_DEFAULTS[target]
                return val

        if name == "openai_api_key":
            return openai.shared_api_key
        if name == "openai_base_url":
            return openai.shared_base_url
        if name == "openai_timeout_seconds":
            return openai.timeout_seconds

        raise AttributeError(name)

    # --- Explicit properties (not delegable to __getattr__) ---

    @property
    def resolved_openai_api_key(self) -> str | None:
        return self.openai_api_key or os.getenv("OPENAI_API_KEY")

    @property
    def openai_enabled(self) -> bool:
        return bool(self.configured_openai_targets)

    @property
    def configured_openai_targets(self) -> list[str]:
        return [t for t in TARGET_NAMES if getattr(self, f"resolved_openai_{t}_api_key")]

    @property
    def resolved_x_bearer_token(self) -> str | None:
        return self.x_bearer_token or os.getenv("X_BEARER_TOKEN")

    @property
    def resolved_anthropic_api_key(self) -> str | None:
        return self.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")

    @property
    def x_enabled(self) -> bool:
        return bool(self.resolved_x_bearer_token or self.resolved_openai_x_search_api_key)

    def openai_model_source(self, target: str) -> str:
        return model_source(self.openai, target)

    def openai_api_key_source(self, target: str) -> str:
        return api_key_source(self.openai, target)

    def openai_base_url_source(self, target: str) -> str:
        return base_url_source(self.openai, target)
