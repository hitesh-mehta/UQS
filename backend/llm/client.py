"""
Pluggable LLM Client for UQS.

Supported providers (set LLM_PROVIDER in .env):
  - google    → Google Gemini via google-generativeai SDK (DEFAULT for hackathon)
  - ollama    → Local Ollama models (Gemma, Mistral, LLaMA)
  - openai    → OpenAI GPT models
  - anthropic → Anthropic Claude models

For the NatWest Hackathon, we use Google Gemini 2.0 Flash (free tier):
  - 15 requests/min, 1M tokens/min, 1500 requests/day — sufficient for demo
  - No GPU required, low latency, excellent JSON instruction following
  - API key obtained from: https://aistudio.google.com/app/apikey

Swap providers at any time by changing LLM_PROVIDER in .env — no code changes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Optional

import httpx
from pydantic import BaseModel

from backend.config import settings

log = logging.getLogger("uqs.llm")


# ── Response Model ────────────────────────────────────────────────────────────

class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    latency_ms: float
    tokens_used: Optional[int] = None


# ── Base Client ───────────────────────────────────────────────────────────────

class BaseLLMClient:
    """Abstract base — all providers implement complete()."""

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        raise NotImplementedError


# ── Google Gemini Client ───────────────────────────────────────────────────────

class GeminiClient(BaseLLMClient):
    """
    Google Gemini client via the official google-generativeai SDK.

    Why Gemini for this hackathon:
    - Free tier: 15 RPM, 1M TPM, 1500 RPD — no billing required
    - Gemini 2.0 Flash: fast (~1-2s), low latency, strong JSON following
    - Supports system instructions natively (separate from user turn)
    - response_mime_type="application/json" forces clean JSON output

    NOTE: The SDK's generate_content() is synchronous, so we wrap it
    in asyncio.to_thread() to avoid blocking the FastAPI event loop.
    """

    def __init__(self):
        try:
            import google.generativeai as genai
            self._genai = genai
            # Configure the API key globally (SDK pattern)
            genai.configure(api_key=settings.google_api_key)
            log.info(f"Gemini client configured — model: {settings.llm_model}")
        except ImportError:
            raise RuntimeError(
                "Install the Google AI SDK: pip install google-generativeai"
            )
        self.model_name = settings.llm_model  # e.g. "gemini-2.0-flash"

    def _build_model(self, system_prompt: str, json_mode: bool, temperature: float, max_tokens: int):
        """Build a configured GenerativeModel instance."""
        generation_config = self._genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            # Force JSON output when requested — Gemini reliably respects this
            response_mime_type="application/json" if json_mode else "text/plain",
        )
        return self._genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system_prompt,  # System prompt as separate instruction
            generation_config=generation_config,
        )

    def _call_sync(self, model, user_message: str) -> Any:
        """Synchronous Gemini call — wrapped in asyncio.to_thread for async use."""
        return model.generate_content(user_message)

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        start = time.perf_counter()

        model = self._build_model(system_prompt, json_mode, temperature, max_tokens)

        log.debug(
            "Gemini request start: model=%s json_mode=%s temperature=%s max_tokens=%s user_chars=%s system_chars=%s",
            self.model_name,
            json_mode,
            temperature,
            max_tokens,
            len(user_message),
            len(system_prompt),
        )

        # Run in thread pool to prevent blocking the async event loop
        response = await asyncio.to_thread(self._call_sync, model, user_message)

        latency_ms = (time.perf_counter() - start) * 1000
        content = response.text or ""

        log.debug(
            "Gemini response received: provider=%s model=%s latency_ms=%.0f has_text=%s text_chars=%s preview=%r",
            "google",
            self.model_name,
            latency_ms,
            bool(content.strip()),
            len(content),
            content[:500],
        )

        # Count tokens from usage metadata if available
        tokens = None
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens = (
                response.usage_metadata.prompt_token_count
                + response.usage_metadata.candidates_token_count
            )

        log.debug(f"Gemini response — {latency_ms:.0f}ms, ~{tokens} tokens")
        return LLMResponse(
            content=content,
            model=self.model_name,
            provider="google",
            latency_ms=latency_ms,
            tokens_used=tokens,
        )


# ── Ollama Client ─────────────────────────────────────────────────────────────

class OllamaClient(BaseLLMClient):
    """
    Client for locally-running Ollama models (Gemma, Mistral, LLaMA, etc.)
    Requires: `ollama serve` + `ollama pull <model>`
    Good for: fully offline / air-gapped deployments.
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
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        latency_ms = (time.perf_counter() - start) * 1000
        return LLMResponse(
            content=data["message"]["content"],
            model=self.model,
            provider="ollama",
            latency_ms=latency_ms,
        )


# ── OpenAI Client ─────────────────────────────────────────────────────────────

class OpenAIClient(BaseLLMClient):
    """OpenAI GPT client. Set LLM_PROVIDER=openai and LLM_MODEL=gpt-4o."""

    def __init__(self):
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        except ImportError:
            raise RuntimeError("Install 'openai': pip install openai")
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
    """Anthropic Claude client. Set LLM_PROVIDER=anthropic."""

    def __init__(self):
        try:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        except ImportError:
            raise RuntimeError("Install 'anthropic': pip install anthropic")
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
    """
    Returns the LLM client for the configured provider.
    Provider is set via LLM_PROVIDER in .env:
      google    → GeminiClient   (default for hackathon — free tier)
      ollama    → OllamaClient   (local, no internet needed)
      openai    → OpenAIClient   (cloud, paid)
      anthropic → AnthropicClient (cloud, paid)
    """
    provider = settings.llm_provider
    if provider == "google":
        return GeminiClient()
    elif provider == "ollama":
        return OllamaClient()
    elif provider == "openai":
        return OpenAIClient()
    elif provider == "anthropic":
        return AnthropicClient()
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{provider}'. Choose: google | ollama | openai | anthropic"
        )


# ── Convenience helper ────────────────────────────────────────────────────────

async def llm_json(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """
    Ask the configured LLM for a structured JSON response and parse it.

    - json_mode=True is passed to the provider (Gemini uses response_mime_type,
      Ollama uses format="json", OpenAI uses response_format)
    - Strips markdown code fences if the model wraps the JSON anyway
    - Returns parsed dict. Raises ValueError if response is not valid JSON.
    """
    client = get_llm_client()
    response = await client.complete(
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=temperature,
        json_mode=True,
    )
    raw = response.content.strip()

    log.debug(
        "llm_json raw content: provider=%s model=%s chars=%s preview=%r",
        response.provider,
        response.model,
        len(raw),
        raw[:500],
    )
    log.debug(
        "llm_json raw content full start provider=%s model=%s chars=%s",
        response.provider,
        response.model,
        len(raw),
    )
    log.debug("llm_json raw content full body:\n%s", raw)
    log.debug("llm_json raw content full end")

    log.debug(
        "llm_json parse attempt: provider=%s model=%s json_mode=%s raw_is_empty=%s",
        response.provider,
        response.model,
        True,
        not bool(raw.strip()),
    )

    # 1. Direct parse
    try:
        parsed = json.loads(raw)
        log.debug(
            "llm_json parsed direct: keys=%s",
            sorted(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__,
        )
        return parsed
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences (``` or ```json ... ```)
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1))
            log.debug(
                "llm_json parsed fenced: keys=%s",
                sorted(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__,
            )
            return parsed
        except json.JSONDecodeError:
            pass

    # 3. Extract first JSON object/array from the text
    obj_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if obj_match:
        try:
            parsed = json.loads(obj_match.group(0))
            log.debug(
                "llm_json parsed extracted: keys=%s",
                sorted(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__,
            )
            return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"LLM ({response.provider}/{response.model}) returned non-JSON. "
        f"First 300 chars: {raw[:300]}"
    )
