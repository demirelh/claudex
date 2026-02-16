"""Copilot API client with streaming support and tool use.

Communicates with the GitHub Copilot Chat Completions API at
api.githubcopilot.com using the OpenAI-compatible format.
Supports function calling / tool use.
Auto-retries on transient network errors (connection drops, incomplete reads).
"""

import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

import httpx

from .auth import CopilotToken

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


@dataclass
class ToolCall:
    """Accumulated tool call from streaming response."""
    id: str = ""
    function_name: str = ""
    arguments_json: str = ""


@dataclass
class StreamResult:
    """Result of a streaming chat completion.

    May contain text content, tool calls, or both.
    """
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    # Token usage tracking
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # Timing
    time_to_first_token: float = 0.0
    total_time: float = 0.0
    # Whether the stream was interrupted but partial content was recovered
    partial: bool = False

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


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


# Transient network errors that are safe to retry
_RETRYABLE_ERRORS = (
    httpx.RemoteProtocolError,  # "peer closed connection without sending complete message body"
    httpx.LocalProtocolError,   # local protocol violation
    httpx.ReadError,            # read operation failed
    httpx.ConnectError,         # connection refused / reset
    httpx.CloseError,           # error closing connection
    httpx.StreamError,          # stream-level error
    httpx.TimeoutException,     # any timeout (read, connect, pool)
)


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is a transient network error worth retrying."""
    return isinstance(exc, _RETRYABLE_ERRORS)


async def stream_chat_with_tools(
    token: CopilotToken,
    messages: list[dict],
    model: str = "claude-sonnet-4",
    max_tokens: int = 16384,
    temperature: float = 0.0,
    top_p: float = 1.0,
    tools: Optional[list[dict]] = None,
    on_content_chunk=None,
) -> StreamResult:
    """Stream a chat completion, supporting both text and tool call responses.

    Args:
        token: Copilot session token.
        messages: List of chat messages (OpenAI format).
        model: Model identifier.
        max_tokens: Maximum response tokens.
        temperature: Sampling temperature.
        top_p: Nucleus sampling parameter.
        tools: Optional list of tool definitions (OpenAI format).
        on_content_chunk: Optional async/sync callback for each text chunk.
            Called as on_content_chunk(text: str) for live streaming to terminal.

    Returns:
        StreamResult with accumulated content and/or tool calls.
    """
    headers = {
        **BASE_HEADERS,
        "Authorization": f"Bearer {token.token}",
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

    import time
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


# Keep the simple streaming generator for backward compat
async def stream_chat(
    token: CopilotToken,
    messages: list[dict],
    model: str = "claude-sonnet-4",
    max_tokens: int = 16384,
    temperature: float = 0.0,
    top_p: float = 1.0,
) -> AsyncIterator[str]:
    """Stream a chat completion response (text only, no tool support).

    Yields text content chunks as they arrive via SSE.
    """
    def noop(chunk):
        pass

    result = await stream_chat_with_tools(
        token=token,
        messages=messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        tools=None,
        on_content_chunk=noop,
    )


async def chat_once(
    token: CopilotToken,
    messages: list[dict],
    model: str = "claude-sonnet-4",
    max_tokens: int = 16384,
    temperature: float = 0.0,
) -> str:
    """Non-streaming chat completion. Returns the full response text."""
    headers = {
        **BASE_HEADERS,
        "Authorization": f"Bearer {token.token}",
    }

    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(180.0, connect=15.0)
    ) as client:
        resp = await client.post(COPILOT_CHAT_URL, json=body, headers=headers)

        if resp.status_code == 401:
            raise PermissionError("Copilot token expired or invalid.")
        if resp.status_code == 403:
            raise PermissionError("Copilot access denied.")

        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
