"""OpenAI API backend implementation."""

import asyncio
import json
import os
import sys
import time
from typing import Optional, Callable

import httpx

from .base import Backend, BackendType, StreamResult, ToolCall


# Default OpenAI API URL (can be overridden via OPENAI_BASE_URL)
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

# Max retries for transient network errors during streaming
MAX_STREAM_RETRIES = 2
RETRY_DELAY_SECONDS = 1.5


class OpenAIAPIError(Exception):
    """Error from the OpenAI API."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


# Transient network errors that are safe to retry
_RETRYABLE_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.LocalProtocolError,
    httpx.ReadError,
    httpx.ConnectError,
    httpx.CloseError,
    httpx.StreamError,
    httpx.TimeoutException,
)


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is a transient network error worth retrying."""
    return isinstance(exc, _RETRYABLE_ERRORS)


async def _handle_error_response(response) -> None:
    """Handle HTTP error responses from the API."""
    if response.status_code == 401:
        raise PermissionError(
            "OpenAI API key is invalid or expired. Check your OPENAI_API_KEY."
        )
    if response.status_code == 403:
        raise PermissionError(
            "OpenAI API access denied. Check your API key permissions."
        )
    if response.status_code == 429:
        raise OpenAIAPIError(
            429, "Rate limited. Please wait a moment and try again."
        )
    if response.status_code == 400:
        body_text = ""
        async for chunk in response.aiter_bytes():
            body_text += chunk.decode("utf-8", errors="replace")
        try:
            error_data = json.loads(body_text)
            msg = error_data.get("error", {}).get("message", body_text[:200])
        except json.JSONDecodeError:
            msg = body_text[:200]
        raise OpenAIAPIError(400, f"Bad request: {msg}")
    if response.status_code >= 400:
        raise OpenAIAPIError(
            response.status_code,
            f"Unexpected error (HTTP {response.status_code})",
        )


class OpenAIBackend:
    """OpenAI API backend.

    Connects directly to OpenAI's Chat Completions API using OPENAI_API_KEY.
    Supports custom base URL via OPENAI_BASE_URL for OpenAI-compatible endpoints.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)
        # Ensure base_url doesn't have trailing slash
        self.base_url = self.base_url.rstrip("/")
        self.chat_url = f"{self.base_url}/chat/completions"

    @property
    def name(self) -> str:
        # Show custom base URL if it's not the default
        if self.base_url != DEFAULT_OPENAI_BASE_URL:
            return f"OpenAI API ({self.base_url})"
        return "OpenAI API"

    @property
    def backend_type(self) -> BackendType:
        return BackendType.OPENAI

    def is_available(self) -> bool:
        """Check if OpenAI backend is available (API key exists)."""
        return bool(self.api_key)

    async def stream_chat_with_tools(
        self,
        messages: list[dict],
        model: str = "gpt-4o",
        max_tokens: int = 16384,
        temperature: float = 0.0,
        top_p: float = 1.0,
        tools: Optional[list[dict]] = None,
        on_content_chunk: Optional[Callable[[str], None]] = None,
    ) -> StreamResult:
        """Stream a chat completion with tool support via OpenAI API."""
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable."
            )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
        }

        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        result = StreamResult()
        # Accumulate tool calls by index
        tool_calls_by_index: dict[int, ToolCall] = {}
        first_token_received = False

        start_time = time.monotonic()

        # Callback wrapper that logs retries to stderr
        def _on_retry(attempt: int, exc: Exception, partial_content: str):
            """Notify the user about a retry (via on_content_chunk or stderr)."""
            partial_len = len(partial_content)
            msg = (
                f"\n  ⟳ Connection lost ({type(exc).__name__}), "
                f"retrying ({attempt}/{MAX_STREAM_RETRIES})..."
            )
            if partial_len:
                msg += f" ({partial_len} chars preserved)"
            msg += "\n"
            if on_content_chunk:
                on_content_chunk(msg)
            else:
                sys.stderr.write(msg)

        last_error: Optional[Exception] = None
        stream_completed = False

        for attempt in range(MAX_STREAM_RETRIES + 1):
            if attempt > 0:
                # Wait before retry
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                # For continuation: if we had partial content, append it to
                # messages so the model can continue from where it left off
                if result.content:
                    continuation_messages = list(messages) + [
                        {"role": "assistant", "content": result.content},
                        {"role": "user", "content": "Continue from where you left off. Do not repeat what you already said."},
                    ]
                else:
                    continuation_messages = messages
                # Reset result for this attempt but keep partial content
                partial_content = result.content
                result = StreamResult()
                result.content = partial_content
                tool_calls_by_index = {}
                first_token_received = bool(partial_content)

            try:
                current_messages = messages if attempt == 0 else continuation_messages

                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(180.0, connect=15.0)
                ) as client:
                    async with client.stream(
                        "POST", self.chat_url, json=body, headers=headers
                    ) as response:
                        await _handle_error_response(response)

                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue

                            data = line[6:]
                            if data.strip() == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data)

                                # Track usage if present
                                usage = chunk.get("usage")
                                if usage:
                                    result.prompt_tokens = usage.get("prompt_tokens", 0)
                                    result.completion_tokens = usage.get("completion_tokens", 0)
                                    result.total_tokens = usage.get("total_tokens", 0)

                                choices = chunk.get("choices", [])
                                if not choices:
                                    continue

                                choice = choices[0]
                                delta = choice.get("delta", {})
                                finish = choice.get("finish_reason")

                                if finish:
                                    result.finish_reason = finish

                                # --- Text content ---
                                content = delta.get("content")
                                if content:
                                    if not first_token_received:
                                        first_token_received = True
                                        result.time_to_first_token = time.monotonic() - start_time
                                    result.content += content
                                    if on_content_chunk:
                                        on_content_chunk(content)

                                # --- Tool calls ---
                                tc_deltas = delta.get("tool_calls", [])
                                for tc_delta in tc_deltas:
                                    if not first_token_received:
                                        first_token_received = True
                                        result.time_to_first_token = time.monotonic() - start_time

                                    idx = tc_delta.get("index", 0)

                                    if idx not in tool_calls_by_index:
                                        tool_calls_by_index[idx] = ToolCall()

                                    tc = tool_calls_by_index[idx]

                                    if "id" in tc_delta and tc_delta["id"]:
                                        tc.id = tc_delta["id"]

                                    fn = tc_delta.get("function", {})
                                    if fn.get("name"):
                                        tc.function_name = fn["name"]
                                    if fn.get("arguments"):
                                        tc.arguments_json += fn["arguments"]

                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue

                # Success — break out of retry loop
                last_error = None
                stream_completed = True
                break

            except Exception as exc:
                if _is_retryable(exc) and attempt < MAX_STREAM_RETRIES:
                    last_error = exc
                    _on_retry(attempt + 1, exc, result.content)
                    continue
                # Non-retryable or exhausted retries
                # If we have partial content, return it instead of raising
                if result.content:
                    result.partial = True
                    break
                raise

        # Collect accumulated tool calls
        if tool_calls_by_index:
            result.tool_calls = [
                tool_calls_by_index[i]
                for i in sorted(tool_calls_by_index.keys())
            ]

        result.total_time = time.monotonic() - start_time
        return result
