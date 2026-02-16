"""Model definitions for GitHub Copilot Business.

Defines available models, their API identifiers, and short aliases
for convenient model switching via /model command.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Model:
    """Model definition."""

    name: str  # Human display name
    id: str  # API model identifier
    provider: str  # Provider company
    description: str  # Short description


# -------------------------------------------------------------------------
# Models available through GitHub Copilot Business
# Discovered via https://api.githubcopilot.com/models
# -------------------------------------------------------------------------
MODELS: dict[str, Model] = {
    # --- Anthropic (Claude) ---
    "opus-4.6": Model(
        "Claude Opus 4.6",
        "claude-opus-4.6",
        "Anthropic",
        "Most capable Claude model — deep reasoning and analysis",
    ),
    "opus-4.5": Model(
        "Claude Opus 4.5",
        "claude-opus-4.5",
        "Anthropic",
        "Previous flagship — strong reasoning",
    ),
    "sonnet-4.5": Model(
        "Claude Sonnet 4.5",
        "claude-sonnet-4.5",
        "Anthropic",
        "Latest Sonnet — fast and highly capable",
    ),
    "sonnet": Model(
        "Claude Sonnet 4",
        "claude-sonnet-4",
        "Anthropic",
        "Fast and capable — great balance of speed and quality",
    ),
    "haiku": Model(
        "Claude Haiku 4.5",
        "claude-haiku-4.5",
        "Anthropic",
        "Fastest Claude — lightweight tasks",
    ),
    # --- Google ---
    "gemini": Model(
        "Gemini 2.5 Pro",
        "gemini-2.5-pro",
        "Google",
        "Google's most capable model",
    ),
    # --- OpenAI ---
    "gpt-5": Model(
        "GPT-5",
        "gpt-5",
        "OpenAI",
        "Latest GPT flagship model",
    ),
    "gpt-5-mini": Model(
        "GPT-5 Mini",
        "gpt-5-mini",
        "OpenAI",
        "Compact GPT-5 — faster and cheaper",
    ),
    "gpt-5.1": Model(
        "GPT-5.1",
        "gpt-5.1",
        "OpenAI",
        "GPT-5.1 series model",
    ),
    "gpt-5.2": Model(
        "GPT-5.2",
        "gpt-5.2",
        "OpenAI",
        "GPT-5.2 series model",
    ),
    "gpt-5.1-codex": Model(
        "GPT-5.1 Codex",
        "gpt-5.1-codex",
        "OpenAI",
        "GPT-5.1 optimized for coding",
    ),
    "gpt-5.2-codex": Model(
        "GPT-5.2 Codex",
        "gpt-5.2-codex",
        "OpenAI",
        "GPT-5.2 optimized for coding",
    ),
    "gpt-5.3-codex": Model(
        "GPT-5.3 Codex",
        "gpt-5.3-codex",
        "OpenAI",
        "GPT-5.3 optimized for coding",
    ),
    "gpt-4o": Model(
        "GPT-4o",
        "gpt-4o",
        "OpenAI",
        "Multimodal GPT-4 — fast and capable",
    ),
    "gpt-4o-mini": Model(
        "GPT-4o Mini",
        "gpt-4o-mini",
        "OpenAI",
        "Compact GPT-4o — lightweight tasks",
    ),
    "gpt-4.1": Model(
        "GPT-4.1",
        "gpt-4.1",
        "OpenAI",
        "GPT-4.1 series model",
    ),
}

# Short aliases for convenience
MODEL_ALIASES: dict[str, str] = {
    # Claude aliases
    "opus": "opus-4.6",
    "claude-opus": "opus-4.6",
    "claude-opus-4.6": "opus-4.6",
    "claude-opus-4.5": "opus-4.5",
    "sonnet-4": "sonnet",
    "claude-sonnet-4": "sonnet",
    "claude-sonnet": "sonnet",
    "claude-sonnet-4.5": "sonnet-4.5",
    "claude-haiku": "haiku",
    "claude-haiku-4.5": "haiku",
    # Google aliases
    "gemini-2.5-pro": "gemini",
    "gemini-pro": "gemini",
    # OpenAI aliases
    "5": "gpt-5",
    "5-mini": "gpt-5-mini",
    "4o": "gpt-4o",
    "4o-mini": "gpt-4o-mini",
    "4.1": "gpt-4.1",
    "codex": "gpt-5.3-codex",
}

DEFAULT_MODEL = "sonnet"


def resolve_model(name: str) -> Optional[Model]:
    """Resolve a model name or alias to a Model object.

    Args:
        name: Model name, alias, or API ID.

    Returns:
        Model object if found, None otherwise.
    """
    name = name.lower().strip()

    # Direct match
    if name in MODELS:
        return MODELS[name]

    # Alias match
    if name in MODEL_ALIASES:
        return MODELS[MODEL_ALIASES[name]]

    # Match by API ID
    for model in MODELS.values():
        if model.id.lower() == name:
            return model

    return None


def get_model_id(name: str) -> str:
    """Get the API model ID for a given name.

    Falls back to the raw name if no model is found,
    allowing users to specify arbitrary model IDs.
    """
    model = resolve_model(name)
    if model:
        return model.id
    return name


def get_canonical_key(name: str) -> str:
    """Get the canonical MODELS dict key for a name."""
    name = name.lower().strip()

    if name in MODELS:
        return name

    if name in MODEL_ALIASES:
        return MODEL_ALIASES[name]

    # Match by API ID
    for key, model in MODELS.items():
        if model.id.lower() == name:
            return key

    return name


def get_models_by_provider(provider: str) -> dict[str, Model]:
    """Get all models for a specific provider.

    Args:
        provider: Provider name (e.g., "OpenAI", "Anthropic", "Google").

    Returns:
        Dict of model key -> Model for the given provider.
    """
    return {
        key: model
        for key, model in MODELS.items()
        if model.provider == provider
    }


def is_model_compatible(model_key: str, provider: str) -> bool:
    """Check if a model is compatible with a backend provider.

    Args:
        model_key: Model key or alias.
        provider: Provider name (e.g., "OpenAI", "Anthropic").

    Returns:
        True if the model is from the given provider.
    """
    model = resolve_model(model_key)
    if not model:
        # Unknown model, can't determine compatibility
        return False
    return model.provider == provider
