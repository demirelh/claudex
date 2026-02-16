"""Backend abstraction for ClaudeX.

Supports multiple LLM API backends:
- Copilot: GitHub Copilot Business API
- OpenAI: OpenAI Chat Completions API
"""

from .base import Backend, BackendType
from .copilot import CopilotBackend
from .openai import OpenAIBackend

__all__ = [
    "Backend",
    "BackendType",
    "CopilotBackend",
    "OpenAIBackend",
]
