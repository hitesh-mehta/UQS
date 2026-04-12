"""
Pluggable LLM Client for UQS.
Supports: Ollama (Gemma/Mistral/LLaMA), OpenAI, Anthropic.
Swap providers by changing LLM_PROVIDER in .env — no code changes needed.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

import httpx
from pydantic import BaseModel

from backend.config import settings


# ── Response Model ────────────────────────────────────────────────────────────

class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    latency_ms: float
    tokens_used: Optional[int] = None


# ── Base Client ───────────────────────────────────────────────────────────────

class BaseLLMClient:
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        raise NotImplementedError


# ── Ollama Client ─────────────────────────────────────────────────────────────

class OllamaClient(BaseLLMClient):
    """
    Client for locally running Ollama models (Gemma, Mistral, LLaMA, etc.)
    Requires: ollama serve + ollama pull <model>
    """

    def __init__(self):
        self.base_url = settings.llm_base_url
        self.model = settings.llm_model

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        start = time.perf_counter()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = (time.perf_counter() - start) * 1000
        content = data["message"]["content"]
        return LLMResponse(
            content=content,
            model=self.model,
            provider="ollama",
            latency_ms=latency_ms,
        )


# ── OpenAI Client ─────────────────────────────────────────────────────────────

class OpenAIClient(BaseLLMClient):
    def __init__(self):
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        except ImportError:
            raise RuntimeError("Install 'openai' package: pip install openai")
        self.model = settings.llm_model

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        import time
        start = time.perf_counter()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)
        latency_ms = (time.perf_counter() - start) * 1000
        return LLMResponse(
            content=response.choices[0].message.content,
            model=self.model,
            provider="openai",
            latency_ms=latency_ms,
            tokens_used=response.usage.total_tokens if response.usage else None,
        )


# ── Anthropic Client ──────────────────────────────────────────────────────────

class AnthropicClient(BaseLLMClient):
    def __init__(self):
        try:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        except ImportError:
            raise RuntimeError("Install 'anthropic' package: pip install anthropic")
        self.model = settings.llm_model

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        import time
        start = time.perf_counter()
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        latency_ms = (time.perf_counter() - start) * 1000
        content = response.content[0].text if response.content else ""
        return LLMResponse(
            content=content,
            model=self.model,
            provider="anthropic",
            latency_ms=latency_ms,
            tokens_used=(response.usage.input_tokens + response.usage.output_tokens)
            if response.usage else None,
        )


# ── Factory ───────────────────────────────────────────────────────────────────

def get_llm_client() -> BaseLLMClient:
    """Returns the configured LLM client based on LLM_PROVIDER env var."""
    provider = settings.llm_provider
    if provider == "ollama":
        return OllamaClient()
    elif provider == "openai":
        return OpenAIClient()
    elif provider == "anthropic":
        return AnthropicClient()
    else:
        raise ValueError(f"Unsupported LLM provider: '{provider}'")


# ── Convenience helper ────────────────────────────────────────────────────────

async def llm_json(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """
    Ask the LLM for a JSON response and parse it automatically.
    Returns parsed dict. Raises ValueError if response is not valid JSON.
    """
    client = get_llm_client()
    response = await client.complete(
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=temperature,
        json_mode=True,
    )
    try:
        return json.loads(response.content)
    except json.JSONDecodeError as e:
        # Attempt to extract JSON from response if wrapped in markdown
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response.content, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise ValueError(f"LLM returned non-JSON response: {response.content[:200]}") from e
