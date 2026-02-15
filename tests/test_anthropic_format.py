"""Test Anthropic Messages API format translation.

These tests verify that the gateway correctly accepts Anthropic-format
requests (/v1/messages) and translates them to/from the OpenAI-compatible
GitHub Models backend.
"""

import pytest


@pytest.mark.integration
def test_anthropic_messages_basic(team_client):
    """Basic Anthropic Messages API request succeeds."""
    r = team_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet",
            "max_tokens": 50,
            "messages": [{"role": "user", "content": "Say exactly: hello"}],
        },
        headers={"anthropic-version": "2023-06-01"},
    )
    assert r.status_code == 200
    data = r.json()
    # Anthropic response format
    assert data.get("type") == "message"
    assert data.get("role") == "assistant"
    assert isinstance(data.get("content"), list)
    assert len(data["content"]) > 0
    assert data["content"][0]["type"] == "text"
    assert "usage" in data


@pytest.mark.integration
def test_anthropic_messages_with_system(team_client):
    """Anthropic request with system prompt is translated correctly."""
    r = team_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet",
            "max_tokens": 50,
            "system": "You always respond with exactly one word.",
            "messages": [{"role": "user", "content": "What color is the sky?"}],
        },
        headers={"anthropic-version": "2023-06-01"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["content"][0]["type"] == "text"


@pytest.mark.integration
def test_anthropic_messages_multi_turn(team_client):
    """Multi-turn conversation works in Anthropic format."""
    r = team_client.post(
        "/v1/messages",
        json={
            "model": "claude-haiku",
            "max_tokens": 50,
            "messages": [
                {"role": "user", "content": "Remember the number 42."},
                {"role": "assistant", "content": "I'll remember: 42."},
                {"role": "user", "content": "What number did I say?"},
            ],
        },
        headers={"anthropic-version": "2023-06-01"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "42" in data["content"][0]["text"]
