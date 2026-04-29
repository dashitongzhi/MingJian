from __future__ import annotations

import json
from typing import Any
from planagent.services.providers.base import LLMResponse


class AnthropicProvider:
    provider_name = "anthropic"

    def __init__(self, api_key: str | None, timeout: float = 45.0) -> None:
        self._client = None
        if api_key:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)
            except ImportError:
                pass

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    async def generate_text(self, *, model: str, system_prompt: str, user_prompt: str, max_tokens: int = 1024, temperature: float = 0.3) -> LLMResponse | None:
        if not self._client:
            return None
        try:
            resp = await self._client.messages.create(model=model, system=system_prompt, messages=[{"role": "user", "content": user_prompt}], max_tokens=max_tokens, temperature=temperature)
            text = resp.content[0].text if resp.content else ""
            return LLMResponse(text=text, model=resp.model, response_id=resp.id, api_mode="anthropic.messages", usage={"prompt_tokens": resp.usage.input_tokens, "completion_tokens": resp.usage.output_tokens})
        except Exception:
            return None

    async def generate_json(self, *, model: str, system_prompt: str, user_prompt: str, schema: dict[str, Any] | None = None, max_tokens: int = 1024, temperature: float = 0.3) -> tuple[LLMResponse | None, dict[str, Any] | None]:
        if not self._client:
            return None, None
        try:
            json_inst = "\n\nRespond with valid JSON only."
            if schema:
                json_inst += f"\nSchema:\n{json.dumps(schema, indent=2)}"
            resp = await self._client.messages.create(model=model, system=system_prompt + json_inst, messages=[{"role": "user", "content": user_prompt}], max_tokens=max_tokens, temperature=temperature)
            text = resp.content[0].text if resp.content else "{}"
            clean = text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[-1]
            if clean.endswith("```"):
                clean = clean.rsplit("```", 1)[0]
            parsed = json.loads(clean.strip())
            r = LLMResponse(text=text, model=resp.model, response_id=resp.id, api_mode="anthropic.messages.json", usage={"prompt_tokens": resp.usage.input_tokens, "completion_tokens": resp.usage.output_tokens})
            return r, parsed if isinstance(parsed, dict) else None
        except Exception:
            return None, None

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
