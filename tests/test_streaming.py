"""Test SSE streaming responses."""

import httpx
import pytest


@pytest.mark.integration
def test_openai_streaming(team_client, gateway_url, master_key):
    """OpenAI-format streaming returns SSE events."""
    key = master_key
    chunks = []

    with httpx.stream(
        "POST",
        f"{gateway_url}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "Count from 1 to 3."}],
            "max_tokens": 50,
            "stream": True,
        },
        timeout=30.0,
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: ") and line != "data: [DONE]":
                chunks.append(line)

    assert len(chunks) > 0, "No streaming chunks received"


@pytest.mark.integration
def test_anthropic_streaming(team_client, gateway_url, master_key):
    """Anthropic-format streaming returns SSE events."""
    key = master_key
    chunks = []

    with httpx.stream(
        "POST",
        f"{gateway_url}/v1/messages",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": "claude-haiku",
            "max_tokens": 50,
            "messages": [{"role": "user", "content": "Count from 1 to 3."}],
            "stream": True,
        },
        timeout=30.0,
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: "):
                chunks.append(line)

    assert len(chunks) > 0, "No streaming chunks received"
