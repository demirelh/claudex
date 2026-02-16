"""Test backend selection and model compatibility."""

import os
import pytest
from unittest.mock import Mock, patch

from claudex.backends import BackendType, CopilotBackend, OpenAIBackend
from claudex.models import is_model_compatible, get_models_by_provider


def test_model_compatibility_openai():
    """OpenAI models are compatible with OpenAI backend."""
    assert is_model_compatible("gpt-4o", "OpenAI")
    assert is_model_compatible("gpt-5", "OpenAI")
    assert is_model_compatible("gpt-4.1", "OpenAI")
    assert is_model_compatible("4o", "OpenAI")  # alias


def test_model_incompatibility_openai():
    """Non-OpenAI models are not compatible with OpenAI backend."""
    assert not is_model_compatible("opus", "OpenAI")
    assert not is_model_compatible("sonnet", "OpenAI")
    assert not is_model_compatible("gemini", "OpenAI")
    assert not is_model_compatible("haiku", "OpenAI")


def test_model_compatibility_anthropic():
    """Anthropic models are compatible with Anthropic provider."""
    assert is_model_compatible("opus", "Anthropic")
    assert is_model_compatible("sonnet", "Anthropic")
    assert is_model_compatible("haiku", "Anthropic")
    assert is_model_compatible("opus-4.5", "Anthropic")


def test_unknown_model_incompatible():
    """Unknown models are considered incompatible."""
    assert not is_model_compatible("nonexistent-model", "OpenAI")
    assert not is_model_compatible("fake-model", "Anthropic")


def test_get_models_by_provider_openai():
    """Get OpenAI models only."""
    openai_models = get_models_by_provider("OpenAI")

    # Should include GPT models
    assert "gpt-4o" in openai_models
    assert "gpt-5" in openai_models
    assert "gpt-5-mini" in openai_models

    # Should not include Claude models
    assert "opus-4.6" not in openai_models
    assert "sonnet" not in openai_models

    # All returned models should be OpenAI
    for model in openai_models.values():
        assert model.provider == "OpenAI"


def test_get_models_by_provider_anthropic():
    """Get Anthropic models only."""
    anthropic_models = get_models_by_provider("Anthropic")

    # Should include Claude models
    assert "opus-4.6" in anthropic_models
    assert "sonnet" in anthropic_models
    assert "haiku" in anthropic_models

    # Should not include GPT models
    assert "gpt-4o" not in anthropic_models
    assert "gpt-5" not in anthropic_models

    # All returned models should be Anthropic
    for model in anthropic_models.values():
        assert model.provider == "Anthropic"


def test_get_models_by_provider_google():
    """Get Google models only."""
    google_models = get_models_by_provider("Google")

    # Should include Gemini
    assert "gemini" in google_models

    # All returned models should be Google
    for model in google_models.values():
        assert model.provider == "Google"


def test_copilot_backend_name():
    """Copilot backend has correct name."""
    with patch('claudex.backends.copilot.get_copilot_token'):
        mock_token = Mock()
        mock_token.token = "test-token"
        mock_token.expires_at = 9999999999
        mock_token.is_expired = False

        backend = CopilotBackend("github-token", mock_token)
        assert backend.name == "GitHub Copilot Business"
        assert backend.backend_type == BackendType.COPILOT


def test_openai_backend_name():
    """OpenAI backend has correct name."""
    backend = OpenAIBackend(api_key="test-key")
    assert backend.name == "OpenAI API"
    assert backend.backend_type == BackendType.OPENAI


def test_openai_backend_custom_base_url():
    """OpenAI backend with custom base URL shows in name."""
    backend = OpenAIBackend(api_key="test-key", base_url="https://custom.openai.com/v1")
    assert "custom.openai.com" in backend.name


def test_openai_backend_availability_with_key():
    """OpenAI backend is available when API key exists."""
    backend = OpenAIBackend(api_key="sk-test-key")
    assert backend.is_available()


def test_openai_backend_availability_without_key():
    """OpenAI backend is not available without API key."""
    backend = OpenAIBackend(api_key="")
    assert not backend.is_available()

    backend = OpenAIBackend(api_key=None)
    assert not backend.is_available()


def test_copilot_backend_availability():
    """Copilot backend availability based on token."""
    mock_token = Mock()
    mock_token.token = "test-token"
    mock_token.expires_at = 9999999999
    mock_token.is_expired = False

    backend = CopilotBackend("github-token", mock_token)
    assert backend.is_available()


def test_copilot_backend_unavailable_expired_token():
    """Copilot backend is not available with expired token."""
    mock_token = Mock()
    mock_token.token = "test-token"
    mock_token.expires_at = 0
    mock_token.is_expired = True

    backend = CopilotBackend("github-token", mock_token)
    assert not backend.is_available()


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set, skipping OpenAI integration test"
)
@pytest.mark.asyncio
async def test_openai_backend_stream_integration():
    """Test OpenAI backend streaming (integration test, skipped without API key)."""
    backend = OpenAIBackend()

    messages = [
        {"role": "user", "content": "Say 'test' and nothing else."}
    ]

    result = await backend.stream_chat_with_tools(
        messages=messages,
        model="gpt-4o-mini",
        max_tokens=10,
        temperature=0.0,
    )

    assert result.content
    assert "test" in result.content.lower()
    assert result.finish_reason in ["stop", "length"]
