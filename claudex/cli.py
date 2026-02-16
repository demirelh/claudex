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
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style as PTStyle

from . import __version__
from .auth import ensure_auth, get_copilot_token, clear_cached_token, CopilotToken
from .client import stream_chat_with_tools, CopilotAPIError
from .config import Config, CONFIG_DIR
from .models import (
    MODELS,
    MODEL_ALIASES,
    DEFAULT_MODEL,
    resolve_model,
    get_model_id,
    get_canonical_key,
)
from .tools import TOOL_DEFINITIONS, execute_tool

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
  [command]/model[/command] <name>    Switch model (e.g. opus, sonnet, gpt-4o)
  [command]/models[/command]         List all available models
  [command]/system[/command] <msg>   Set system prompt for this session
  [command]/clear[/command]          Clear conversation history
  [command]/tools[/command]          Toggle tool use on/off
  [command]/compact[/command]        Toggle compact vs Markdown output
  [command]/config[/command]         Show current configuration
  [command]/save[/command]           Save current settings as defaults
  [command]/logout[/command]         Clear cached GitHub token
  [command]/help[/command]           Show this help
  [command]/quit[/command]           Exit  [dim](or Ctrl+D / Ctrl+C)[/dim]

[bold]Inline model switching:[/bold]
  [dim]@opus[/dim]   <msg>     Send this message using Claude Opus
  [dim]@sonnet[/dim] <msg>     Send using Sonnet (switches back after)
  [dim]@gpt-5[/dim]  <msg>     Send using GPT-5

[bold]Multi-line input:[/bold]
  Press [cyan]Shift+Enter[/cyan] or [cyan]Alt+Enter[/cyan] to add a new line.
  Press [cyan]Enter[/cyan] to send.

[bold]Tools (enabled by default):[/bold]
  • [dim]bash[/dim]             — Run shell commands
  • [dim]read_file[/dim]        — Read file contents
  • [dim]write_file[/dim]       — Create/overwrite files
  • [dim]edit_file[/dim]        — Search-and-replace edit
  • [dim]list_directory[/dim]    — List directory contents
  • [dim]grep_search[/dim]      — Search files with regex
  • [dim]web_fetch[/dim]        — Fetch URLs (HTTP/HTTPS)

[bold]Tips:[/bold]
  • The model can use tools automatically (files, shell, web)
  • Use /tools to disable tools for plain chat mode
  • Conversation history is kept for the session (/clear to reset)
  • Token usage is shown after each response
"""

# Max tool call iterations per message to prevent infinite loops
MAX_TOOL_ITERATIONS = 25

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

    def __init__(self, model: Optional[str] = None, debug: bool = False):
        self.config = Config.load()
        self.messages: list[dict] = []
        self.current_model = model or self.config.default_model
        self.system_prompt = self.config.system_prompt
        self.github_token: Optional[str] = None
        self.copilot_token: Optional[CopilotToken] = None
        self.tools_enabled: bool = True
        self.markdown_mode: bool = True
        self.debug: bool = debug
        # Session stats
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.session_start: float = time.time()

    def _refresh_token_if_needed(self):
        """Refresh Copilot session token if expired."""
        if self.copilot_token and not self.copilot_token.is_expired:
            return
        assert self.github_token is not None
        self.copilot_token = get_copilot_token(self.github_token, debug=self.debug)

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

        elif command == "/tools":
            self.tools_enabled = not self.tools_enabled
            state = "[success]enabled[/success]" if self.tools_enabled else "[warning]disabled[/warning]"
            console.print(f"  Tools: {state}")

        elif command == "/compact":
            self.markdown_mode = not self.markdown_mode
            mode = "[success]Markdown[/success]" if self.markdown_mode else "[info]compact (plain)[/info]"
            console.print(f"  Output: {mode}")

        elif command == "/config":
            model = resolve_model(self.current_model)
            model_name = model.name if model else self.current_model
            console.print(f"  Model:       [model]{model_name}[/model]")
            console.print(f"  Temperature: {self.config.temperature}")
            console.print(f"  Max tokens:  {self.config.max_tokens}")
            tools_state = "[success]on[/success]" if self.tools_enabled else "[warning]off[/warning]"
            console.print(f"  Tools:       {tools_state}")
            md_state = "[success]Markdown[/success]" if self.markdown_mode else "[info]plain[/info]"
            console.print(f"  Output:      {md_state}")
            console.print(f"  Tokens:      {self.total_prompt_tokens:,} in / {self.total_completion_tokens:,} out")
            sp = self.system_prompt or "[dim](none)[/dim]"
            console.print(f"  System:      {sp[:80]}")
            console.print(f"  CWD:         [dim]{os.getcwd()}[/dim]")

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

    def _parse_model_prefix(self, user_input: str) -> tuple[Optional[str], str]:
        """Parse model override from input.

        Supports:
            '@opus plan this'                -> ('opus-4.6', 'plan this')
            'use opus and plan this'         -> ('opus-4.6', 'plan this')
            'verwende opus und plan this'    -> ('opus-4.6', 'plan this')
            'hello'                          -> (None, 'hello')
        """
        # --- 1. Explicit @model prefix ---
        match = re.match(r"^@(\S+)\s+(.+)$", user_input, re.DOTALL)
        if match:
            model_name = match.group(1)
            message = match.group(2)
            resolved = resolve_model(model_name)
            if resolved:
                return get_canonical_key(model_name), message

        # --- 2. Natural-language model switch ---
        # Patterns: "use <model> ...", "verwende <model> ...", "nutze <model> ...",
        #           "with <model> ...", "mit <model> ...", "nimm <model> ..."
        nl_match = re.match(
            r"^(?:use|verwende|nutze|nimm|mit|with|take)\s+(\S+)"
            r"(?:\s+(?:und|and|to|um|,)\s+|\s*,\s*)(.+)$",
            user_input,
            re.IGNORECASE | re.DOTALL,
        )
        if nl_match:
            model_name = nl_match.group(1)
            message = nl_match.group(2)
            resolved = resolve_model(model_name)
            if resolved:
                return get_canonical_key(model_name), message

        return None, user_input

    def _render_response(self, text: str):
        """Render response text — Markdown or plain."""
        if self.markdown_mode and text.strip():
            try:
                md = Markdown(text)
                console.print(md)
            except Exception:
                # Fallback to plain text
                print(text)
        else:
            print(text)

    async def _send_message(self, user_input: str):
        """Send a message and stream the response, handling tool calls."""
        # Parse @model prefix for one-off model switching
        override_model, actual_input = self._parse_model_prefix(user_input)
        use_model = override_model or self.current_model

        self.messages.append({"role": "user", "content": actual_input})

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

        model_id = get_model_id(use_model)
        model_obj = resolve_model(use_model)
        model_display = model_obj.name if model_obj else use_model
        tools = TOOL_DEFINITIONS if self.tools_enabled else None

        if override_model:
            console.print(f"  [dim]Using [model]{model_display}[/model] for this message[/dim]")

        # Track total tokens for this message exchange
        msg_prompt_tokens = 0
        msg_completion_tokens = 0
        msg_start = time.monotonic()

        # Tool call loop — the model may call tools multiple times
        for iteration in range(MAX_TOOL_ITERATIONS):

            # --- Show thinking spinner while waiting for first token ---
            spinner_text = Text.assemble(
                ("  ", ""),
                ("⠋ ", "cyan"),
                (f"Thinking ({model_display})...", "dim"),
            )
            chunks_collected: list[str] = []
            first_chunk_received = False
            live = Live(
                Spinner("dots", text=f"  [dim]Thinking ({model_display})...[/dim]"),
                console=console,
                refresh_per_second=12,
                transient=True,
            )
            live.start()

            def on_chunk(chunk: str):
                nonlocal first_chunk_received
                if not first_chunk_received:
                    first_chunk_received = True
                    live.stop()
                chunks_collected.append(chunk)
                if not self.markdown_mode:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()

            try:
                result = await stream_chat_with_tools(
                    token=self.copilot_token,
                    messages=self._build_messages(),
                    model=model_id,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    tools=tools,
                    on_content_chunk=on_chunk,
                )
            except KeyboardInterrupt:
                live.stop()
                console.print("\n  [warning]Response cancelled[/warning]")
                return
            except PermissionError as e:
                live.stop()
                console.print(f"\n  [error]{e}[/error]")
                self.copilot_token = None
                return
            except CopilotAPIError as e:
                live.stop()
                console.print(f"\n  [error]{e}[/error]")
                return
            except Exception as e:
                live.stop()
                console.print(f"\n  [error]Error: {e}[/error]")
                return
            finally:
                if live.is_started:
                    live.stop()

            # Track tokens
            msg_prompt_tokens += result.prompt_tokens
            msg_completion_tokens += result.completion_tokens

            # --- Text response (no tool calls) → done ---
            if not result.has_tool_calls:
                if result.content:
                    if self.markdown_mode:
                        console.print()
                        self._render_response(result.content)
                    else:
                        print()  # Newline after streamed text
                    self.messages.append(
                        {"role": "assistant", "content": result.content}
                    )

                # Show stats
                self.total_prompt_tokens += msg_prompt_tokens
                self.total_completion_tokens += msg_completion_tokens
                elapsed = time.monotonic() - msg_start
                stats_parts = []
                if result.time_to_first_token > 0:
                    stats_parts.append(f"TTFT {result.time_to_first_token:.1f}s")
                stats_parts.append(f"{elapsed:.1f}s total")
                if msg_prompt_tokens or msg_completion_tokens:
                    stats_parts.append(f"{msg_prompt_tokens + msg_completion_tokens:,} tokens")
                console.print(f"  [dim]{' · '.join(stats_parts)}[/dim]")
                console.print()
                return

            # --- Tool calls ---
            if result.content:
                if self.markdown_mode:
                    console.print()
                    self._render_response(result.content)
                else:
                    print()

            # Build assistant message with tool_calls
            assistant_msg: dict = {
                "role": "assistant",
                "content": result.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function_name,
                            "arguments": tc.arguments_json,
                        },
                    }
                    for tc in result.tool_calls
                ],
            }
            self.messages.append(assistant_msg)

            # Execute each tool call
            for tc in result.tool_calls:
                try:
                    args = json.loads(tc.arguments_json) if tc.arguments_json else {}
                except json.JSONDecodeError:
                    args = {}

                # Display tool invocation in a styled way
                args_preview = ", ".join(
                    f"{k}={repr(v)[:60]}" for k, v in args.items()
                )
                console.print()
                console.print(
                    f"  [info]⚡ {tc.function_name}[/info]"
                    f"  [dim]{args_preview}[/dim]"
                )

                tool_result = execute_tool(tc.function_name, args, console)

                # Show truncated result in panel
                preview_lines = tool_result.split("\n")
                if len(preview_lines) > 8:
                    preview = "\n".join(preview_lines[:8]) + f"\n... ({len(preview_lines) - 8} more lines)"
                else:
                    preview = tool_result
                if len(preview) > 500:
                    preview = preview[:500] + "..."
                console.print(Panel(
                    Text(preview, style="dim"),
                    border_style="dim",
                    padding=(0, 1),
                    expand=False,
                ))

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    }
                )

            # Loop: send tool results back to model

        console.print("  [warning]Max tool iterations reached[/warning]")

    def _build_prompt_fragments(self):
        """Build the prompt showing CWD and model."""
        cwd = os.path.basename(os.getcwd()) or "/"
        model_obj = resolve_model(self.current_model)
        model_short = model_obj.name if model_obj else self.current_model
        return [
            ("class:cwd", f"{cwd}"),
            ("class:prompt", " › "),
        ]

    def run(self):
        """Main sync REPL loop."""
        # --- Banner ---
        model = resolve_model(self.current_model)
        model_display = model.name if model else self.current_model

        console.print()
        console.print(
            Panel(
                f"[bold white]ClaudeX[/bold white]  [dim]v{__version__}[/dim]\n"
                f"[dim]GitHub Copilot Business[/dim] · [model]{model_display}[/model]\n"
                f"[dim]cwd: {os.getcwd()}[/dim]",
                border_style="bright_blue",
                padding=(0, 2),
            )
        )
        console.print(
            "  Type [command]/help[/command] for commands, "
            "[command]/quit[/command] to exit."
        )
        console.print(
            "  [dim]Multi-line: Shift+Enter or Alt+Enter. "
            "Prefix @model to override.[/dim]\n"
        )

        # --- Authenticate ---
        try:
            self.github_token, self.copilot_token = ensure_auth(console, debug=self.debug)
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

        # --- Multi-line key bindings ---
        kb = KeyBindings()

        @kb.add("escape", "enter")   # Alt+Enter
        def _(event):
            event.current_buffer.insert_text("\n")

        # --- REPL ---
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        pt_style = PTStyle.from_dict({
            "prompt": "#00cc99 bold",
            "cwd": "#888888",
        })

        session = PromptSession(
            history=FileHistory(str(CONFIG_DIR / "history")),
            key_bindings=kb,
            multiline=False,
        )

        while True:
            try:
                user_input = session.prompt(
                    self._build_prompt_fragments(),
                    style=pt_style,
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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show diagnostic info (account, token, API responses)",
    )

    args = parser.parse_args()

    if args.list_models:
        list_models()
        return

    if args.logout:
        clear_cached_token()
        console.print("  Cached token cleared.")
        return

    cli = ClaudeXCLI(model=args.model, debug=args.debug)
    try:
        cli.run()
    except KeyboardInterrupt:
        print("\n")


if __name__ == "__main__":
    main()
