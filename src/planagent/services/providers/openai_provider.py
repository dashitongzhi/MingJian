from __future__ import annotations

import json
from typing import Any
from openai import AsyncOpenAI
from planagent.services.providers.base import LLMResponse


class OpenAIProvider:
    provider_name = "openai"

    def __init__(self, api_key: str | None, base_url: str | None = None, timeout: float = 45.0) -> None:
        self._client: AsyncOpenAI | None = None
        if api_key:
            kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = AsyncOpenAI(**kwargs)

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    async def generate_text(self, *, model: str, system_prompt: str, user_prompt: str, max_tokens: int = 1024, temperature: float = 0.3) -> LLMResponse | None:
        if not self._client:
            return None
        try:
            resp = await self._client.chat.completions.create(
                model=model, max_tokens=max_tokens, temperature=temperature,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            )
            c = resp.choices[0]
            return LLMResponse(text=c.message.content or "", model=resp.model, response_id=resp.id, api_mode="chat.completions", usage=resp.usage.model_dump() if resp.usage else None)
        except Exception:
            return None

    async def generate_json(self, *, model: str, system_prompt: str, user_prompt: str, schema: dict[str, Any] | None = None, max_tokens: int = 1024, temperature: float = 0.3) -> tuple[LLMResponse | None, dict[str, Any] | None]:
        if not self._client:
            return None, None
        try:
            resp = await self._client.chat.completions.create(
                model=model, max_tokens=max_tokens, temperature=temperature,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or "{}"
            parsed = json.loads(text)
            r = LLMResponse(text=text, model=resp.model, response_id=resp.id, api_mode="chat.completions.json", usage=resp.usage.model_dump() if resp.usage else None)
            return r, parsed if isinstance(parsed, dict) else None
        except Exception:
            return None, None

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
