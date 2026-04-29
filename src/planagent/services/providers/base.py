from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    response_id: str | None = None
    api_mode: str | None = None
    usage: dict[str, Any] | None = None


class LLMProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def is_configured(self) -> bool: ...

    async def generate_text(
        self, *, model: str, system_prompt: str, user_prompt: str,
        max_tokens: int = 1024, temperature: float = 0.3,
    ) -> LLMResponse | None: ...

    async def generate_json(
        self, *, model: str, system_prompt: str, user_prompt: str,
        schema: dict[str, Any] | None = None, max_tokens: int = 1024, temperature: float = 0.3,
    ) -> tuple[LLMResponse | None, dict[str, Any] | None]: ...

    async def close(self) -> None: ...
