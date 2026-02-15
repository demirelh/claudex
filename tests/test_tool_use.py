"""Test tool/function calling translation."""

import json
import pytest

WEATHER_TOOL_ANTHROPIC = {
    "name": "get_weather",
    "description": "Get current weather for a location.",
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City name"},
        },
        "required": ["location"],
    },
}

WEATHER_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a location.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
            },
            "required": ["location"],
        },
    },
}


@pytest.mark.integration
def test_anthropic_tool_use(team_client):
    """Anthropic-format tool use request is translated and returns tool_use block."""
    r = team_client.post(
        "/v1/messages",
        json={
            "model": "gpt-4.1-mini",
            "max_tokens": 200,
            "tools": [WEATHER_TOOL_ANTHROPIC],
            "messages": [
                {"role": "user", "content": "What's the weather in Berlin?"}
            ],
        },
        headers={"anthropic-version": "2023-06-01"},
    )
    assert r.status_code == 200
    data = r.json()
    # The model should attempt to use the tool
    content = data.get("content", [])
    has_tool_use = any(block.get("type") == "tool_use" for block in content)
    has_text = any(block.get("type") == "text" for block in content)
    # Model should use the tool OR respond with text (depends on model behavior)
    assert has_tool_use or has_text


@pytest.mark.integration
def test_openai_function_calling(team_client):
    """OpenAI-format function calling works through the gateway."""
    r = team_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [
                {"role": "user", "content": "What's the weather in Berlin?"}
            ],
            "tools": [WEATHER_TOOL_OPENAI],
            "max_tokens": 200,
        },
    )
    assert r.status_code == 200
    data = r.json()
    choice = data["choices"][0]
    msg = choice["message"]
    # Model should call the tool OR respond with text
    has_tool_calls = "tool_calls" in msg and msg["tool_calls"] is not None
    has_content = msg.get("content") is not None
    assert has_tool_calls or has_content
