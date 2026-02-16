"""Copilot API client with streaming support.

Communicates with the GitHub Copilot Chat Completions API at
api.githubcopilot.com using the OpenAI-compatible format.
"""

import json
import sys
from typing import AsyncIterator, Optional

import httpx

from .auth import CopilotToken

COPILOT_CHAT_URL = "https://api.githubcopilot.com/chat/completions"

# Headers that identify the client to the Copilot API.
# These mimic what the VS Code Copilot Chat extension sends.
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


async def stream_chat(
    token: CopilotToken,
    messages: list[dict],
    model: str = "claude-sonnet-4",
    max_tokens: int = 16384,
    temperature: float = 0.0,
    top_p: float = 1.0,
) -> AsyncIterator[str]:
    """Stream a chat completion response from the Copilot API.

    Yields text content chunks as they arrive via SSE.

    Args:
        token: Copilot session token.
        messages: List of chat messages (OpenAI format).
        model: Model identifier.
        max_tokens: Maximum response tokens.
        temperature: Sampling temperature.
        top_p: Nucleus sampling parameter.

    Yields:
        Text content chunks.

    Raises:
        CopilotAPIError: If the API returns an error.
        PermissionError: If auth fails (401/403).
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

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(180.0, connect=15.0)
    ) as client:
        async with client.stream(
            "POST", COPILOT_CHAT_URL, json=body, headers=headers
        ) as response:
            # Handle error responses
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
                # Try to get error details
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

            # Parse SSE stream
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data = line[6:]
                if data.strip() == "[DONE]":
                    return

                try:
                    chunk = json.loads(data)
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


async def chat_once(
    token: CopilotToken,
    messages: list[dict],
    model: str = "claude-sonnet-4",
    max_tokens: int = 16384,
    temperature: float = 0.0,
) -> str:
    """Non-streaming chat completion. Returns the full response text.

    Useful for single-shot queries or testing.
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
        "stream": False,
    }

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(180.0, connect=15.0)
    ) as client:
        response = await client.post(COPILOT_CHAT_URL, json=body, headers=headers)

        if response.status_code == 401:
            raise PermissionError("Copilot token expired or invalid.")
        if response.status_code == 403:
            raise PermissionError("Copilot access denied.")

        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
