"""ClaudeX — Interactive CLI for GitHub Copilot Business models.

Provides a Claude Code-like terminal experience using your
GitHub Copilot Business subscription to access Claude Opus, Sonnet,
GPT-4o, and other models.

Usage:
    claudex                    # Start interactive REPL (default: sonnet)
    claudex --model opus       # Start with Claude Opus 4
    claudex --model gpt-4o     # Start with GPT-4o
    claudex -m o4-mini         # Start with o4-mini
    claudex --list-models      # List available models
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style as PTStyle

from . import __version__
from .auth import ensure_auth, get_copilot_token, clear_cached_token, CopilotToken
from .client import stream_chat, CopilotAPIError
from .config import Config, CONFIG_DIR
from .models import (
    MODELS,
    MODEL_ALIASES,
    DEFAULT_MODEL,
    resolve_model,
    get_model_id,
    get_canonical_key,
)

# ---------------------------------------------------------------------------
# Rich console theme
# ---------------------------------------------------------------------------
theme = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red bold",
        "model": "magenta bold",
        "prompt": "green bold",
        "dim": "dim",
        "command": "cyan",
    }
)
console = Console(theme=theme)

# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------
HELP_TEXT = """
[bold]Commands:[/bold]
  [command]/model[/command] <name>    Switch model (e.g. opus, sonnet, gpt-4o, o4-mini)
  [command]/models[/command]         List all available models
  [command]/system[/command] <msg>   Set system prompt for this session
  [command]/clear[/command]          Clear conversation history
  [command]/config[/command]         Show current configuration
  [command]/save[/command]           Save current settings as defaults
  [command]/logout[/command]         Clear cached GitHub token
  [command]/help[/command]           Show this help
  [command]/quit[/command]           Exit  [dim](or Ctrl+D / Ctrl+C)[/dim]

[bold]Tips:[/bold]
  • Conversation history is kept for the session (use /clear to reset)
  • Copilot tokens auto-refresh when they expire (~30 min)
  • Set GITHUB_TOKEN env var to skip interactive login
"""

# ---------------------------------------------------------------------------
# Prompt toolkit style
# ---------------------------------------------------------------------------
PT_STYLE = PTStyle.from_dict(
    {
        "prompt": "#00cc66 bold",
    }
)


class ClaudeXCLI:
    """Interactive CLI session."""

    def __init__(self, model: Optional[str] = None):
        self.config = Config.load()
        self.messages: list[dict] = []
        self.current_model = model or self.config.default_model
        self.system_prompt = self.config.system_prompt
        self.github_token: Optional[str] = None
        self.copilot_token: Optional[CopilotToken] = None

    def _refresh_token_if_needed(self):
        """Refresh Copilot session token if expired."""
        if self.copilot_token and not self.copilot_token.is_expired:
            return
        assert self.github_token is not None
        self.copilot_token = get_copilot_token(self.github_token)

    def _build_messages(self) -> list[dict]:
        """Build the full message list including system prompt."""
        msgs = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        msgs.extend(self.messages)
        return msgs

    def _handle_command(self, cmd: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        parts = cmd.strip().split(None, 1)
        command = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if command in ("/quit", "/exit", "/q"):
            raise EOFError()

        elif command == "/help":
            console.print(HELP_TEXT)

        elif command == "/model":
            if not arg:
                model = resolve_model(self.current_model)
                name = model.name if model else self.current_model
                model_id = model.id if model else self.current_model
                console.print(f"  Current: [model]{name}[/model] ({model_id})")
                return True

            resolved = resolve_model(arg)
            if resolved:
                self.current_model = get_canonical_key(arg)
                console.print(
                    f"  Switched to [model]{resolved.name}[/model] ({resolved.id})"
                )
            else:
                # Allow raw model IDs as passthrough
                self.current_model = arg.strip()
                console.print(
                    f"  Model set to [model]{arg.strip()}[/model] [dim](custom ID)[/dim]"
                )

        elif command == "/models":
            table = Table(
                title="Available Models",
                show_lines=False,
                padding=(0, 2),
                title_style="bold",
            )
            table.add_column("Alias", style="cyan bold")
            table.add_column("Model", style="white")
            table.add_column("Provider", style="dim")
            table.add_column("Description", style="dim")

            for alias, model in MODELS.items():
                marker = " [green]●[/green]" if alias == self.current_model else ""
                table.add_row(
                    alias + marker,
                    model.name,
                    model.provider,
                    model.description,
                )
            console.print()
            console.print(table)
            console.print()
            aliases_str = ", ".join(
                f"[dim]{k}[/dim]→[cyan]{v}[/cyan]" for k, v in MODEL_ALIASES.items()
            )
            console.print(f"  Aliases: {aliases_str}")
            console.print()

        elif command == "/system":
            if not arg:
                if self.system_prompt:
                    console.print(f"  System: {self.system_prompt[:200]}")
                else:
                    console.print(
                        "  No system prompt set. Use [command]/system <message>[/command]"
                    )
            elif arg.lower() in ("clear", "reset", "none"):
                self.system_prompt = None
                console.print("  System prompt cleared.")
            else:
                self.system_prompt = arg
                console.print("  System prompt updated.")

        elif command in ("/clear", "/reset"):
            self.messages.clear()
            console.print("  Conversation cleared.")

        elif command == "/config":
            model = resolve_model(self.current_model)
            model_name = model.name if model else self.current_model
            console.print(f"  Model:       [model]{model_name}[/model]")
            console.print(f"  Temperature: {self.config.temperature}")
            console.print(f"  Max tokens:  {self.config.max_tokens}")
            sp = self.system_prompt or "[dim](none)[/dim]"
            console.print(f"  System:      {sp[:80]}")

        elif command == "/save":
            self.config.default_model = self.current_model
            self.config.system_prompt = self.system_prompt
            self.config.save()
            console.print("  Settings saved to ~/.config/claudex/config.json")

        elif command == "/logout":
            clear_cached_token()
            console.print("  Cached token cleared. Run again to re-authenticate.")

        else:
            console.print(
                f"  [warning]Unknown command: {command}[/warning]  "
                f"Type [command]/help[/command] for available commands."
            )

        return True

    async def _send_message(self, user_input: str):
        """Send a message and stream the response."""
        self.messages.append({"role": "user", "content": user_input})

        try:
            self._refresh_token_if_needed()
        except SystemExit as e:
            console.print(f"\n  [error]{e}[/error]")
            self.messages.pop()
            return
        except Exception as e:
            console.print(f"\n  [error]Token refresh failed: {e}[/error]")
            self.messages.pop()
            return

        model_id = get_model_id(self.current_model)
        full_response: list[str] = []

        console.print()
        try:
            async for chunk in stream_chat(
                token=self.copilot_token,
                messages=self._build_messages(),
                model=model_id,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            ):
                sys.stdout.write(chunk)
                sys.stdout.flush()
                full_response.append(chunk)

        except KeyboardInterrupt:
            console.print("\n  [warning]Response cancelled[/warning]")

        except PermissionError as e:
            console.print(f"\n  [error]{e}[/error]")
            # Invalidate token so it refreshes on next try
            self.copilot_token = None
            self.messages.pop()
            return

        except CopilotAPIError as e:
            console.print(f"\n  [error]{e}[/error]")
            self.messages.pop()
            return

        except Exception as e:
            console.print(f"\n  [error]Error: {e}[/error]")
            self.messages.pop()
            return

        response_text = "".join(full_response)
        if response_text:
            print()  # Newline after streamed text
            self.messages.append(
                {"role": "assistant", "content": response_text}
            )
        console.print()

    def run(self):
        """Main sync REPL loop."""
        # --- Banner ---
        model = resolve_model(self.current_model)
        model_display = model.name if model else self.current_model

        console.print()
        console.print(
            Panel(
                f"[bold white]ClaudeX[/bold white]  [dim]v{__version__}[/dim]\n"
                f"[dim]GitHub Copilot Business[/dim] · [model]{model_display}[/model]",
                border_style="bright_blue",
                padding=(0, 2),
            )
        )
        console.print(
            "  Type [command]/help[/command] for commands, "
            "[command]/quit[/command] to exit.\n"
        )

        # --- Authenticate ---
        try:
            self.github_token, self.copilot_token = ensure_auth(console)
        except SystemExit as e:
            console.print(f"  [error]{e}[/error]")
            return
        except Exception as e:
            console.print(f"  [error]Authentication failed: {e}[/error]")
            return

        resolved = resolve_model(self.current_model)
        if resolved:
            console.print(
                f"  [success]✓[/success] Authenticated — [model]{resolved.name}[/model]\n"
            )
        else:
            console.print(
                f"  [success]✓[/success] Authenticated — [model]{self.current_model}[/model]\n"
            )

        # --- REPL ---
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        session = PromptSession(
            history=FileHistory(str(CONFIG_DIR / "history")),
        )

        while True:
            try:
                user_input = session.prompt(
                    [("class:prompt", "› ")],
                    style=PT_STYLE,
                )
            except (EOFError, KeyboardInterrupt):
                console.print("\n  [dim]Goodbye![/dim]")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            # Handle slash commands
            if user_input.startswith("/"):
                try:
                    self._handle_command(user_input)
                except EOFError:
                    console.print("  [dim]Goodbye![/dim]")
                    break
                continue

            # Send message and stream response
            try:
                asyncio.run(self._send_message(user_input))
            except KeyboardInterrupt:
                console.print("\n  [warning]Cancelled[/warning]")
                continue


def list_models():
    """Print available models and exit."""
    table = Table(
        title="ClaudeX — Available Models",
        show_lines=False,
        padding=(0, 2),
        title_style="bold",
    )
    table.add_column("Alias", style="cyan bold")
    table.add_column("Model", style="white")
    table.add_column("Provider", style="dim")
    table.add_column("API ID", style="dim")
    table.add_column("Description", style="dim")

    for alias, model in MODELS.items():
        table.add_row(alias, model.name, model.provider, model.id, model.description)

    console.print()
    console.print(table)
    console.print()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="claudex",
        description="ClaudeX — CLI for GitHub Copilot Business models",
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=None,
        help="Model to use (e.g. opus, sonnet, gpt-4o, o4-mini)",
    )
    parser.add_argument(
        "-l",
        "--list-models",
        action="store_true",
        help="List available models and exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"claudex {__version__}",
    )
    parser.add_argument(
        "--logout",
        action="store_true",
        help="Clear cached GitHub token and exit",
    )

    args = parser.parse_args()

    if args.list_models:
        list_models()
        return

    if args.logout:
        clear_cached_token()
        console.print("  Cached token cleared.")
        return

    cli = ClaudeXCLI(model=args.model)
    try:
        cli.run()
    except KeyboardInterrupt:
        print("\n")


if __name__ == "__main__":
    main()
