"""Test backend selection and model compatibility."""

import os
import pytest
from unittest.mock import Mock, patch

from claudex.backends import BackendType, CopilotBackend, OpenAIBackend
from claudex.models import (
    is_model_compatible,
    get_models_by_provider,
    get_default_model_for_provider,
)


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


def test_get_default_model_for_provider_openai():
    """Get default model for OpenAI provider."""
    default = get_default_model_for_provider("OpenAI")
    assert default == "gpt-4o"
    # Verify it's a valid model
    assert is_model_compatible(default, "OpenAI")


def test_get_default_model_for_provider_anthropic():
    """Get default model for Anthropic provider."""
    default = get_default_model_for_provider("Anthropic")
    assert default == "sonnet"
    # Verify it's a valid model
    assert is_model_compatible(default, "Anthropic")


def test_get_default_model_for_provider_google():
    """Get default model for Google provider."""
    default = get_default_model_for_provider("Google")
    assert default == "gemini"
    # Verify it's a valid model
    assert is_model_compatible(default, "Google")


def test_get_default_model_for_provider_unknown():
    """Get default model for unknown provider returns global default."""
    from claudex.models import DEFAULT_MODEL
    default = get_default_model_for_provider("UnknownProvider")
    assert default == DEFAULT_MODEL


def test_config_plan_model_copilot():
    """Config returns Copilot plan model by default."""
    from claudex.config import Config
    config = Config()
    plan_model = config.get_plan_model(BackendType.COPILOT)
    assert plan_model == "opus"


def test_config_plan_model_openai():
    """Config returns OpenAI plan model for OpenAI backend."""
    from claudex.config import Config
    config = Config()
    plan_model = config.get_plan_model(BackendType.OPENAI)
    assert plan_model == "gpt-5"
    # Verify it's a valid OpenAI model
    assert is_model_compatible(plan_model, "OpenAI")


def test_config_exec_model_copilot():
    """Config returns Copilot exec model by default."""
    from claudex.config import Config
    config = Config()
    exec_model = config.get_exec_model(BackendType.COPILOT)
    assert exec_model == "sonnet"


def test_config_exec_model_openai():
    """Config returns OpenAI exec model for OpenAI backend."""
    from claudex.config import Config
    config = Config()
    exec_model = config.get_exec_model(BackendType.OPENAI)
    assert exec_model == "gpt-5-mini"
    # Verify it's a valid OpenAI model
    assert is_model_compatible(exec_model, "OpenAI")


def test_config_plan_model_no_backend():
    """Config returns default plan model when backend is None."""
    from claudex.config import Config
    config = Config()
    plan_model = config.get_plan_model(None)
    assert plan_model == "opus"


def test_config_exec_model_no_backend():
    """Config returns default exec model when backend is None."""
    from claudex.config import Config
    config = Config()
    exec_model = config.get_exec_model(None)
    assert exec_model == "sonnet"


def test_openai_gpt5_uses_max_completion_tokens():
    """GPT-5 models should use max_completion_tokens parameter."""
    from claudex.backends.openai import _uses_max_completion_tokens

    # GPT-5 series should use max_completion_tokens
    assert _uses_max_completion_tokens("gpt-5")
    assert _uses_max_completion_tokens("gpt-5-mini")
    assert _uses_max_completion_tokens("gpt-5.1")
    assert _uses_max_completion_tokens("gpt-5.2")
    assert _uses_max_completion_tokens("gpt-5.1-codex")
    assert _uses_max_completion_tokens("GPT-5")  # case insensitive


def test_openai_gpt4_uses_max_tokens():
    """GPT-4 and older models should use max_tokens parameter."""
    from claudex.backends.openai import _uses_max_completion_tokens

    # GPT-4 and older should use max_tokens
    assert not _uses_max_completion_tokens("gpt-4o")
    assert not _uses_max_completion_tokens("gpt-4o-mini")
    assert not _uses_max_completion_tokens("gpt-4.1")
    assert not _uses_max_completion_tokens("gpt-4")
    assert not _uses_max_completion_tokens("gpt-3.5-turbo")
    assert not _uses_max_completion_tokens("GPT-4O")  # case insensitive


@pytest.mark.asyncio
async def test_openai_gpt5_omits_temperature():
    """GPT-5 models should omit temperature parameter (uses default 1.0)."""
    from unittest.mock import AsyncMock, patch, MagicMock

    backend = OpenAIBackend(api_key="test-key")

    # Mock the httpx client to intercept the request body
    captured_body = None

    class MockResponse:
        def __init__(self):
            self.status_code = 200

        async def aiter_lines(self):
            yield "data: [DONE]"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockClient:
        def stream(self, method, url, **kwargs):
            nonlocal captured_body
            captured_body = kwargs.get("json")
            return MockResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch('httpx.AsyncClient', return_value=MockClient()):
        messages = [{"role": "user", "content": "test"}]
        await backend.stream_chat_with_tools(
            messages=messages,
            model="gpt-5",
            max_tokens=1000,
            temperature=0.0,  # This should be omitted for GPT-5
        )

        # Verify temperature was NOT included for GPT-5
        assert captured_body is not None
        assert "temperature" not in captured_body
        assert "max_completion_tokens" in captured_body


@pytest.mark.asyncio
async def test_openai_gpt4_includes_temperature():
    """GPT-4 models should include temperature parameter."""
    from unittest.mock import AsyncMock, patch, MagicMock

    backend = OpenAIBackend(api_key="test-key")

    # Mock the httpx client to intercept the request body
    captured_body = None

    class MockResponse:
        def __init__(self):
            self.status_code = 200

        async def aiter_lines(self):
            yield "data: [DONE]"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockClient:
        def stream(self, method, url, **kwargs):
            nonlocal captured_body
            captured_body = kwargs.get("json")
            return MockResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch('httpx.AsyncClient', return_value=MockClient()):
        messages = [{"role": "user", "content": "test"}]
        await backend.stream_chat_with_tools(
            messages=messages,
            model="gpt-4o",
            max_tokens=1000,
            temperature=0.5,
        )

        # Verify temperature WAS included for GPT-4
        assert captured_body is not None
        assert "temperature" in captured_body
        assert captured_body["temperature"] == 0.5
        assert "max_tokens" in captured_body
