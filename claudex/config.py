"""Configuration management for ClaudeX CLI.

Stores user preferences in ~/.config/claudex/config.json.
"""

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".config" / "claudex"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class Config:
    """User configuration."""

    default_model: str = "sonnet"
    temperature: float = 0.0
    max_tokens: int = 16384
    system_prompt: Optional[str] = None
    # Plan mode settings - default (Copilot backend)
    plan_model: str = "opus"
    exec_model: str = "sonnet"
    # Plan mode settings - OpenAI backend
    plan_model_openai: str = "gpt-5"
    exec_model_openai: str = "gpt-5-mini"
    plan_dir: str = "~/.config/claudex/plans"
    # Tool iteration limits per backend
    max_tool_iterations: int = 25
    max_tool_iterations_openai: int = 50

    def get_plan_model(self, backend_type=None) -> str:
        """Get plan model based on backend type.

        Args:
            backend_type: BackendType enum value (or None for default)

        Returns:
            Model key for planning mode.
        """
        # Import here to avoid circular dependency
        from .backends import BackendType

        if backend_type == BackendType.OPENAI:
            return self.plan_model_openai
        return self.plan_model

    def get_exec_model(self, backend_type=None) -> str:
        """Get exec model based on backend type.

        Args:
            backend_type: BackendType enum value (or None for default)

        Returns:
            Model key for execution mode.
        """
        # Import here to avoid circular dependency
        from .backends import BackendType

        if backend_type == BackendType.OPENAI:
            return self.exec_model_openai
        return self.exec_model

    def get_max_tool_iterations(self, backend_type=None) -> int:
        """Get max tool iterations based on backend type.

        Args:
            backend_type: BackendType enum value (or None for default)

        Returns:
            Max tool iterations limit for the backend.
        """
        # Import here to avoid circular dependency
        from .backends import BackendType

        if backend_type == BackendType.OPENAI:
            return self.max_tool_iterations_openai
        return self.max_tool_iterations

    def save(self):
        """Persist config to disk."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n")

    @classmethod
    def load(cls) -> "Config":
        """Load config from disk, or return defaults."""
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text())
                # Only use known fields
                known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**known)
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()
