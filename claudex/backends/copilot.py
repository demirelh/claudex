"""GitHub Copilot backend implementation."""

import asyncio
import json
import sys
import time
from typing import Optional, Callable

import httpx

from ..auth import CopilotToken, ensure_auth, get_copilot_token
from .base import Backend, BackendType, StreamResult, ToolCall


COPILOT_CHAT_URL = "https://api.githubcopilot.com/chat/completions"

# Max retries for transient network errors during streaming
MAX_STREAM_RETRIES = 2
RETRY_DELAY_SECONDS = 1.5

# Headers that identify the client to the Copilot API.
BASE_HEADERS = {
    "Content-Type": "application/json",
    "Editor-Version": "vscode/1.96.0",
    "Editor-Plugin-Version": "copilot-chat/0.24.0",
    "Copilot-Integration-Id": "vscode-chat",
    "Openai-Intent": "conversation-panel",
    "User-Agent": "ClaudeX-CLI/0.1.0",
}


class CopilotAPIError(Exception):
    """Error from the Copilot API."""

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
            "Copilot token expired or invalid. Will refresh automatically."
        )
    if response.status_code == 403:
        raise PermissionError(
            "Copilot access denied. Check your subscription status."
        )
    if response.status_code == 429:
        raise CopilotAPIError(
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
        raise CopilotAPIError(400, f"Bad request: {msg}")
    if response.status_code >= 400:
        raise CopilotAPIError(
            response.status_code,
            f"Unexpected error (HTTP {response.status_code})",
        )


class CopilotBackend:
    """GitHub Copilot Business backend.

    Uses the existing Copilot authentication and API client.
    """

    def __init__(self, github_token: str, copilot_token: CopilotToken, debug: bool = False):
        self.github_token = github_token
        self.copilot_token = copilot_token
        self.debug = debug

    @property
    def name(self) -> str:
        return "GitHub Copilot Business"

    @property
    def backend_type(self) -> BackendType:
        return BackendType.COPILOT

    def is_available(self) -> bool:
        """Check if Copilot backend is available."""
        return self.copilot_token is not None and not self.copilot_token.is_expired

    def refresh_token_if_needed(self):
        """Refresh Copilot session token if expired."""
        if self.copilot_token and not self.copilot_token.is_expired:
            return
        assert self.github_token is not None
        self.copilot_token = get_copilot_token(self.github_token, debug=self.debug)

    async def stream_chat_with_tools(
        self,
        messages: list[dict],
        model: str = "claude-sonnet-4",
        max_tokens: int = 16384,
        temperature: float = 0.0,
        top_p: float = 1.0,
        tools: Optional[list[dict]] = None,
        on_content_chunk: Optional[Callable[[str], None]] = None,
    ) -> StreamResult:
        """Stream a chat completion with tool support via Copilot API."""
        headers = {
            **BASE_HEADERS,
            "Authorization": f"Bearer {self.copilot_token.token}",
        }

        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
            "n": 1,
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
                        "POST", COPILOT_CHAT_URL, json=body, headers=headers
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
