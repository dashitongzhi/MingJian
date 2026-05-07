import os

from pydantic import BaseModel, Field, model_validator


class OpenAITargetConfig(BaseModel):
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


class OpenAIConfig(BaseModel):
    shared_api_key: str | None = None
    shared_base_url: str | None = None
    timeout_seconds: float = 45.0
    primary: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    extraction: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    x_search: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    report: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    debate_advocate: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    debate_challenger: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)
    debate_arbitrator: OpenAITargetConfig = Field(default_factory=OpenAITargetConfig)

    @model_validator(mode="before")
    @classmethod
    def collect_flat_env_target_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        data = dict(data)
        shared_aliases = {
            "api_key": "shared_api_key",
            "base_url": "shared_base_url",
        }
        target_names = (
            "primary",
            "extraction",
            "x_search",
            "report",
            "debate_advocate",
            "debate_challenger",
            "debate_arbitrator",
        )
        field_names = ("model", "api_key", "base_url")

        for alias, field_name in shared_aliases.items():
            if alias in data and field_name not in data:
                data[field_name] = data.pop(alias)

        for target_name in target_names:
            target_data = data.get(target_name)
            if not isinstance(target_data, dict):
                target_data = {}
            else:
                target_data = dict(target_data)

            for field_name in field_names:
                flat_key = f"{target_name}_{field_name}"
                if flat_key in data:
                    target_data[field_name] = data.pop(flat_key)

            if target_data:
                data[target_name] = target_data

        return data


TARGET_NAMES = (
    "primary",
    "extraction",
    "x_search",
    "report",
    "debate_advocate",
    "debate_challenger",
    "debate_arbitrator",
)

TARGET_FALLBACKS: dict[str, dict[str, tuple[str, ...]]] = {
    "primary": {
        "model": ("primary",),
        "api_key": ("primary",),
        "base_url": ("primary",),
    },
    "extraction": {
        "model": ("extraction", "primary"),
        "api_key": ("extraction", "primary"),
        "base_url": ("extraction", "primary"),
    },
    "x_search": {
        "model": ("x_search", "extraction", "primary"),
        "api_key": ("x_search", "extraction", "primary"),
        "base_url": ("x_search", "extraction", "primary"),
    },
    "report": {
        "model": ("report", "primary"),
        "api_key": ("report", "primary"),
        "base_url": ("report", "primary"),
    },
    "debate_advocate": {
        "model": ("debate_advocate", "primary"),
        "api_key": ("debate_advocate", "primary"),
        "base_url": ("debate_advocate", "primary"),
    },
    "debate_challenger": {
        "model": ("debate_challenger", "extraction", "primary"),
        "api_key": ("debate_challenger", "extraction", "primary"),
        "base_url": ("debate_challenger", "extraction", "primary"),
    },
    "debate_arbitrator": {
        "model": ("debate_arbitrator", "report", "primary"),
        "api_key": ("debate_arbitrator", "report", "primary"),
        "base_url": ("debate_arbitrator", "report", "primary"),
    },
}

TARGET_MODEL_DEFAULTS: dict[str, str] = {
    "primary": "openai/gpt-5.2",
}


def _target_attr(openai_cfg: OpenAIConfig, target: str, field: str) -> str | None:
    return getattr(getattr(openai_cfg, target), field)


def resolve_model(openai_cfg: OpenAIConfig, target: str) -> str:
    chain = TARGET_FALLBACKS[target]["model"]
    for t in chain:
        val = _target_attr(openai_cfg, t, "model")
        if val:
            return val
    return TARGET_MODEL_DEFAULTS.get(target, TARGET_MODEL_DEFAULTS.get("primary", ""))


def resolve_api_key(openai_cfg: OpenAIConfig, target: str) -> str | None:
    chain = TARGET_FALLBACKS[target]["api_key"]
    for t in chain:
        val = _target_attr(openai_cfg, t, "api_key")
        if val:
            return val
    return openai_cfg.shared_api_key or None


def resolve_base_url(openai_cfg: OpenAIConfig, target: str) -> str | None:
    chain = TARGET_FALLBACKS[target]["base_url"]
    for t in chain:
        val = _target_attr(openai_cfg, t, "base_url")
        if val:
            return val
    return openai_cfg.shared_base_url or None


def _walk_chain_for_source(
    openai_cfg: OpenAIConfig,
    target: str,
    field: str,
) -> str | None:
    chain = TARGET_FALLBACKS[target][field]
    for t in chain:
        if t == "primary" and t != target:
            if _target_attr(openai_cfg, t, field):
                return t
            break
        if _target_attr(openai_cfg, t, field):
            return t
    return None


def _primary_api_key_source(openai_cfg: OpenAIConfig) -> str:
    if _target_attr(openai_cfg, "primary", "api_key"):
        return "PLANAGENT_OPENAI_PRIMARY_API_KEY"
    if openai_cfg.shared_api_key:
        if os.getenv("PLANAGENT_OPENAI_SHARED_API_KEY"):
            return "PLANAGENT_OPENAI_SHARED_API_KEY"
        return "PLANAGENT_OPENAI_API_KEY"
    if os.getenv("OPENAI_API_KEY"):
        return "OPENAI_API_KEY"
    return "unset"


def _primary_base_url_source(openai_cfg: OpenAIConfig) -> str:
    if _target_attr(openai_cfg, "primary", "base_url"):
        return "PLANAGENT_OPENAI_PRIMARY_BASE_URL"
    if openai_cfg.shared_base_url:
        if os.getenv("PLANAGENT_OPENAI_SHARED_BASE_URL"):
            return "PLANAGENT_OPENAI_SHARED_BASE_URL"
        return "PLANAGENT_OPENAI_BASE_URL"
    return "unset"


def model_source(openai_cfg: OpenAIConfig, target: str) -> str:
    src = _walk_chain_for_source(openai_cfg, target, "model")
    if src is None:
        return "PLANAGENT_OPENAI_PRIMARY_MODEL"
    if src == target:
        return f"PLANAGENT_OPENAI_{target.upper()}_MODEL"
    return model_source(openai_cfg, src)


def api_key_source(openai_cfg: OpenAIConfig, target: str) -> str:
    src = _walk_chain_for_source(openai_cfg, target, "api_key")
    if src is None:
        return _primary_api_key_source(openai_cfg)
    if src == target:
        return f"PLANAGENT_OPENAI_{target.upper()}_API_KEY"
    return api_key_source(openai_cfg, src)


def base_url_source(openai_cfg: OpenAIConfig, target: str) -> str:
    src = _walk_chain_for_source(openai_cfg, target, "base_url")
    if src is None:
        # No value in chain; fall back to primary's source logic
        if target != "primary":
            return base_url_source(openai_cfg, "primary")
        if openai_cfg.shared_base_url:
            if os.getenv("PLANAGENT_OPENAI_SHARED_BASE_URL"):
                return "PLANAGENT_OPENAI_SHARED_BASE_URL"
            return "PLANAGENT_OPENAI_BASE_URL"
        return "unset"
    if src == target:
        return f"PLANAGENT_OPENAI_{target.upper()}_BASE_URL"
    # Value found at a different target — recurse to resolve its source
    return base_url_source(openai_cfg, src)
