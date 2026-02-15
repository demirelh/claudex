"""Test OpenAI Chat Completions format (direct passthrough to GitHub Models)."""

import pytest


@pytest.mark.integration
def test_openai_completions_basic(team_client):
    """Basic OpenAI Chat Completions request works."""
    r = team_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "Say exactly: pong"}],
            "max_tokens": 20,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "choices" in data
    assert len(data["choices"]) > 0
    assert "message" in data["choices"][0]
    assert data["choices"][0]["message"]["role"] == "assistant"


@pytest.mark.integration
def test_openai_completions_with_system(team_client):
    """System message is passed through correctly."""
    r = team_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [
                {"role": "system", "content": "You respond in German only."},
                {"role": "user", "content": "Hello, how are you?"},
            ],
            "max_tokens": 50,
        },
    )
    assert r.status_code == 200


@pytest.mark.integration
def test_model_routing(team_client):
    """Different model names route correctly."""
    for model in ["gpt-4.1-mini", "claude-haiku"]:
        r = team_client.post(
            "/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Say: ok"}],
                "max_tokens": 10,
            },
        )
        assert r.status_code == 200, f"Model {model} failed: {r.text}"
