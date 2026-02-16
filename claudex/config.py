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
    # Plan mode settings
    plan_model: str = "opus"
    exec_model: str = "sonnet"
    plan_dir: str = "~/.config/claudex/plans"

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
