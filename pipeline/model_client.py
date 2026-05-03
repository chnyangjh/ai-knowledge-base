"""Unified LLM calling client with multi-provider support.

This module provides a single interface for interacting with different LLM
providers (DeepSeek, Qwen, OpenAI) via OpenAI-compatible APIs. It includes
retry logic, token estimation, cost calculation, and a convenience quick_chat
function.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_PROVIDER_ENDPOINTS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "openai": "https://api.openai.com/v1",
}

_DEFAULT_MODELS: dict[str, str] = {
    "deepseek": "deepseek-chat",
    "qwen": "qwen-plus",
    "openai": "gpt-4o-mini",
}

_PRICE_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "qwen-plus": (0.80, 2.00),
    "qwen-turbo": (0.30, 0.60),
    "qwen-max": (2.40, 9.60),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-3.5-turbo": (0.50, 1.50),
}

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 2.0
DEFAULT_TIMEOUT = 60.0
DEFAULT_PROVIDER = "deepseek"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Usage:
    """Token usage statistics for a single LLM API call.

    Attributes:
        prompt_tokens: Number of tokens in the input prompt.
        completion_tokens: Number of tokens in the generated response.
        total_tokens: Sum of prompt and completion tokens.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """Unified response from any LLM provider.

    Attributes:
        content: The text content of the assistant message.
        model: The model identifier that was used.
        usage: Token usage statistics for this call.
        finish_reason: The reason the model stopped generating (e.g. "stop").
    """

    content: str
    model: str = ""
    usage: Usage = field(default_factory=Usage)
    finish_reason: str = ""


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    All concrete providers must implement ``build_payload`` and return
    the correct endpoint URL (``endpoint_url`` property).
    """

    @property
    @abstractmethod
    def endpoint_url(self) -> str:
        """Base URL for the provider's chat completions endpoint."""
        ...

    @abstractmethod
    def build_payload(
        self,
        messages: list[dict[str, str]],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build the JSON payload for a chat completion request.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            model: The model identifier to use.
            max_tokens: Maximum number of tokens to generate.
            temperature: Sampling temperature (0.0 - 2.0).
            **kwargs: Additional provider-specific parameters.

        Returns:
            A JSON-serializable dictionary representing the request payload.
        """
        ...


# ---------------------------------------------------------------------------
# OpenAI-compatible provider
# ---------------------------------------------------------------------------


class OpenAICompatibleProvider(LLMProvider):
    """Provider for any API that follows the OpenAI chat completions format.

    Supports DeepSeek, Qwen (DashScope), and OpenAI out of the box.
    Additional providers can be registered by extending
    ``_PROVIDER_ENDPOINTS`` and ``_DEFAULT_MODELS``.

    Args:
        provider_name: One of ``deepseek``, ``qwen``, ``openai``.
        api_key: API key for the provider. Reads from environment variable
            ``{PROVIDER}_API_KEY`` if not supplied.
        endpoint: Explicit custom endpoint URL. When omitted the default
            endpoint for *provider_name* is used.
    """

    def __init__(
        self,
        provider_name: str = DEFAULT_PROVIDER,
        api_key: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self.provider_name = provider_name.lower()

        self.api_key = api_key or os.environ.get(
            f"{self.provider_name.upper()}_API_KEY"
        )
        if not self.api_key:
            raise ValueError(
                f"API key not found for provider '{self.provider_name}'. "
                f"Set {self.provider_name.upper()}_API_KEY environment variable."
            )

        self._custom_endpoint = endpoint

    @property
    def endpoint_url(self) -> str:
        if self._custom_endpoint:
            return self._custom_endpoint.rstrip("/")
        base = _PROVIDER_ENDPOINTS.get(self.provider_name)
        if base is None:
            raise ValueError(f"Unknown provider: {self.provider_name}")
        return base

    def build_payload(
        self,
        messages: list[dict[str, str]],
        model: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        payload.update(kwargs)
        return payload


# ---------------------------------------------------------------------------
# Default provider factory
# ---------------------------------------------------------------------------


def _get_default_model(provider: str) -> str:
    """Resolve the default model for the given provider.

    Args:
        provider: Provider name (lowercase).

    Returns:
        The default model name, or ``"unknown"`` if the provider is not
        recognised.
    """
    return _DEFAULT_MODELS.get(provider, "unknown")


def _get_provider(provider_name: str | None = None) -> OpenAICompatibleProvider:
    """Factory that creates a provider instance from configuration.

    Args:
        provider_name: Override the provider. Reads ``LLM_PROVIDER`` env
            variable when *None*.

    Returns:
        A configured ``OpenAICompatibleProvider``.
    """
    name = (provider_name or os.environ.get("LLM_PROVIDER", DEFAULT_PROVIDER)).lower()
    return OpenAICompatibleProvider(provider_name=name)


# ---------------------------------------------------------------------------
# Core API call
# ---------------------------------------------------------------------------


def _parse_response(data: dict[str, Any], model: str) -> LLMResponse:
    """Extract content and usage from an OpenAI-compatible API response.

    Args:
        data: Parsed JSON response body.
        model: Model identifier used for the request.

    Returns:
        A populated ``LLMResponse``.
    """
    choice = data["choices"][0]
    content = choice["message"]["content"]
    finish_reason = choice.get("finish_reason", "")

    usage_data = data.get("usage", {})
    usage = Usage(
        prompt_tokens=usage_data.get("prompt_tokens", 0),
        completion_tokens=usage_data.get("completion_tokens", 0),
        total_tokens=usage_data.get("total_tokens", 0),
    )

    return LLMResponse(
        content=content,
        model=model,
        usage=usage,
        finish_reason=finish_reason,
    )


def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    provider: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    timeout: float = DEFAULT_TIMEOUT,
    **kwargs: Any,
) -> LLMResponse:
    """Send a chat completion request to the configured LLM provider.

    Args:
        messages: A list of message dicts, each with ``role`` and ``content``.
        model: Model name override. Uses the provider default when omitted.
        provider: Provider name override (``deepseek``, ``qwen``, ``openai``).
        max_tokens: Maximum tokens in the generated response.
        temperature: Sampling temperature between 0.0 and 2.0.
        timeout: HTTP request timeout in seconds.
        **kwargs: Additional parameters forwarded to the API.

    Returns:
        An ``LLMResponse`` containing the assistant reply and usage stats.

    Raises:
        httpx.HTTPError: On HTTP-level failures.
        KeyError: If the API response structure is unexpected.
        ValueError: If the provider or API key is misconfigured.
    """
    client = _get_provider(provider)
    model = model or _DEFAULT_MODELS.get(client.provider_name, "unknown")
    payload = client.build_payload(
        messages, model, max_tokens=max_tokens, temperature=temperature, **kwargs
    )

    headers = {
        "Authorization": f"Bearer {client.api_key}",
        "Content-Type": "application/json",
    }

    url = f"{client.endpoint_url}/chat/completions"
    logger.debug("Calling %s with model=%s", url, model)

    response = httpx.post(
        url,
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    result = _parse_response(data, model)
    logger.info(
        "chat completion: model=%s, tokens=%d(prompt)+%d(completion)=%d",
        model,
        result.usage.prompt_tokens,
        result.usage.completion_tokens,
        result.usage.total_tokens,
    )
    return result


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------


def chat_with_retry(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    provider: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    **kwargs: Any,
) -> LLMResponse:
    """Chat completion with automatic retry on transient failures.

    Uses exponential backoff: delay = ``backoff_base ** attempt`` seconds.

    Args:
        messages: A list of message dicts, each with ``role`` and ``content``.
        model: Model name override.
        provider: Provider name override.
        max_tokens: Maximum tokens in the generated response.
        temperature: Sampling temperature.
        timeout: HTTP request timeout in seconds.
        max_retries: Maximum number of retry attempts.
        backoff_base: Base multiplier for exponential backoff.
        **kwargs: Additional parameters forwarded to the API.

    Returns:
        An ``LLMResponse`` containing the assistant reply and usage stats.

    Raises:
        httpx.HTTPError: When all retries are exhausted.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return chat(
                messages,
                model=model,
                provider=provider,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                **kwargs,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exception = exc
            if attempt < max_retries:
                delay = backoff_base**attempt
                logger.warning(
                    "LLM call attempt %d/%d failed: %s. Retrying in %.1fs...",
                    attempt + 1,
                    max_retries + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500 and attempt < max_retries:
                delay = backoff_base**attempt
                logger.warning(
                    "Server error %d, attempt %d/%d. Retrying in %.1fs...",
                    exc.response.status_code,
                    attempt + 1,
                    max_retries + 1,
                    delay,
                )
                last_exception = exc
                time.sleep(delay)
            else:
                raise

    logger.error("All %d attempts failed.", max_retries + 1)
    raise last_exception  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Token estimation helpers
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a string.

    Uses a heuristic of ~4 characters per token for English text and
    ~1.5 characters per token for Chinese text. This is a rough estimate
    and should not be used for precise billing calculations.

    Args:
        text: The input string.

    Returns:
        Estimated token count (always >= 1 for non-empty strings).
    """
    if not text:
        return 0

    en_chars = 0
    cn_chars = 0

    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f":
            cn_chars += 1
        else:
            en_chars += 1

    tokens = en_chars / 4.0 + cn_chars / 1.5
    return max(1, round(tokens))


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    """Estimate total tokens across all messages.

    This sums the estimated token count for each message's ``content``,
    which is a rough approximation (it does not model the chat template
    overhead that real tokenizers apply).

    Args:
        messages: List of message dicts with ``content`` keys.

    Returns:
        Estimated total token count.
    """
    total = 0
    for msg in messages:
        total += estimate_tokens(msg.get("content", ""))
    return total


def estimate_cost(
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    *,
    model: str | None = None,
    provider: str | None = None,
) -> float:
    """Estimate the USD cost of an API call based on token usage.

    When the actual token counts are not available (e.g. before a call)
    pass *prompt_tokens* and *completion_tokens* as estimates.

    Args:
        prompt_tokens: Number of input (prompt) tokens, or 0.
        completion_tokens: Number of output (completion) tokens, or 0.
        model: Model name used for pricing lookup.
        provider: Provider name, used to resolve the default model when
            *model* is not given.

    Returns:
        Estimated cost in USD.
    """
    prompt = prompt_tokens or 0
    completion = completion_tokens or 0

    if model is None:
        resolved_provider = (
            provider or os.environ.get("LLM_PROVIDER", DEFAULT_PROVIDER)
        ).lower()
        model = _DEFAULT_MODELS.get(resolved_provider, "unknown")

    input_price, output_price = _PRICE_PER_1M_TOKENS.get(model, (0.0, 0.0))
    cost = (prompt / 1_000_000) * input_price + (completion / 1_000_000) * output_price
    return cost


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def quick_chat(
    prompt: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    system: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    timeout: float = DEFAULT_TIMEOUT,
    with_retry: bool = True,
) -> LLMResponse:
    """One-line convenience function for calling an LLM.

    Builds the message list from a user *prompt* and optional *system*
    message, then calls ``chat_with_retry`` (or ``chat`` when
    *with_retry* is ``False``).

    Args:
        prompt: The user message text.
        model: Model name override.
        provider: Provider name override.
        system: Optional system-level instruction.
        max_tokens: Maximum tokens in the generated response.
        temperature: Sampling temperature.
        timeout: HTTP request timeout in seconds.
        with_retry: Enable automatic retry (default ``True``).

    Returns:
        An ``LLMResponse`` with the assistant reply and usage stats.

    Examples:
        >>> response = quick_chat("你好，请介绍一下自己")
        >>> print(response.content)
        你好！我是 DeepSeek 的 AI 助手...
    """
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    if with_retry:
        return chat_with_retry(
            messages,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
    return chat(
        messages,
        model=model,
        provider=provider,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Self-test (run with: python -m pipeline.model_client)
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    provider_name = os.environ.get("LLM_PROVIDER", DEFAULT_PROVIDER)
    api_key = os.environ.get(f"{provider_name.upper()}_API_KEY")

    if not api_key:
        logger.warning(
            "No API key found for '%s'. " "Set %s_API_KEY to run the live test.",
            provider_name,
            provider_name.upper(),
        )
        logger.info("Running offline tests only...")

        # --- Token estimation tests ---
        assert estimate_tokens("") == 0
        assert estimate_tokens("hello") >= 1
        assert estimate_tokens("你好世界") >= 1
        logger.info("Token estimation: OK")

        # --- Cost estimation tests ---
        cost = estimate_cost(
            prompt_tokens=1000, completion_tokens=500, model="gpt-4o-mini"
        )
        assert cost >= 0.0
        logger.info("Cost estimation (gpt-4o-mini, 1k in + 0.5k out): $%.6f", cost)

        # --- Factory tests ---
        try:
            client = OpenAICompatibleProvider(provider_name=provider_name)
            assert client.provider_name == provider_name
            assert client.endpoint_url
            payload = client.build_payload(
                [{"role": "user", "content": "Hi"}], "test-model"
            )
            assert payload["model"] == "test-model"
            assert payload["messages"][0]["role"] == "user"
            logger.info("Provider factory: OK")
        except ValueError:
            logger.info(
                "Provider factory: SKIPPED (no API key for '%s')", provider_name
            )

        # --- Response parsing tests ---
        sample = {
            "choices": [
                {
                    "message": {"content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
        resp = _parse_response(sample, "test-model")
        assert resp.content == "Hello!"
        assert resp.usage.prompt_tokens == 10
        assert resp.usage.completion_tokens == 5
        assert resp.usage.total_tokens == 15
        assert resp.finish_reason == "stop"
        logger.info("Response parsing: OK")

        logger.info("All offline tests passed.")
    else:
        logger.info("Running live test with provider '%s'...", provider_name)
        response = quick_chat("用中文说一下 你好世界")
        print(f"\n--- Response ---\n{response.content}\n")
        print(f"Model: {response.model}")
        print(f"Tokens: {response.usage.total_tokens}")
        cost = estimate_cost(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            model=response.model,
        )
        print(f"Estimated cost: ${cost:.6f}")
        print(
            f"\nFull response:\n{json.dumps(response.__dict__, default=str, indent=2)}"
        )

        logger.info("Live test completed successfully.")
