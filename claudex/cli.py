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
from .backends import Backend, BackendType, CopilotBackend, OpenAIBackend
from .backends.copilot import CopilotAPIError
from .backends.openai import OpenAIAPIError
from .config import Config, CONFIG_DIR
from .models import (
    MODELS,
    MODEL_ALIASES,
    DEFAULT_MODEL,
    resolve_model,
    get_model_id,
    get_canonical_key,
    is_model_compatible,
    get_models_by_provider,
    get_default_model_for_provider,
)
from .plan_mode import PlanState, PermissionMode
from .tools import TOOL_DEFINITIONS, execute_tool, get_tools_for_mode

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

[bold]Plan Mode:[/bold]
  [command]/plan[/command]           Enter plan mode (Opus, read-only tools)
  [command]/plan show[/command]      Show current plan content
  [command]/plan path[/command]      Show plan file path
  [command]/plan stop[/command]      Exit plan/exec mode → normal
  [command]/approve[/command]        Approve plan → execute with Sonnet
  [command]/deny[/command] [msg]     Deny plan with feedback → revise

[bold]Tips:[/bold]
  • The model can use tools automatically (files, shell, web)
  • Use /tools to disable tools for plain chat mode
  • Conversation history is kept for the session (/clear to reset)
  • Token usage is shown after each response
  • In plan mode, model is locked to Opus; only read-only tools allowed
  • After /approve, execution uses Sonnet with all tools
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

    def __init__(
        self,
        model: Optional[str] = None,
        debug: bool = False,
        backend_type: Optional[BackendType] = None,
    ):
        self.config = Config.load()
        self.messages: list[dict] = []
        self.current_model = model or self.config.default_model
        self.system_prompt = self.config.system_prompt
        self.debug: bool = debug
        self.backend_type: Optional[BackendType] = backend_type
        self.backend: Optional[Backend] = None
        # Legacy copilot fields (kept for compatibility)
        self.github_token: Optional[str] = None
        self.copilot_token: Optional[CopilotToken] = None
        self.tools_enabled: bool = True
        self.markdown_mode: bool = True
        # Plan mode
        self.plan_state = PlanState(
            plan_dir=Path(self.config.plan_dir).expanduser()
        )
        # Session stats
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.session_start: float = time.time()

    def _refresh_token_if_needed(self):
        """Refresh backend token if expired (Copilot only)."""
        if isinstance(self.backend, CopilotBackend):
            self.backend.refresh_token_if_needed()
            self.copilot_token = self.backend.copilot_token

    def _build_messages(self) -> list[dict]:
        """Build the full message list including system prompt."""
        msgs = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        msgs.extend(self.messages)
        return msgs

    def _select_backend(self) -> BackendType:
        """Select backend based on availability and user input.

        Priority:
        1. If only one backend is available, use it automatically
        2. If both are available, ask user interactively
        3. Default to Copilot if neither is available (will fail later with clear error)
        """
        import os
        from .auth import get_github_token

        has_copilot = get_github_token() is not None
        has_openai = bool(os.environ.get("OPENAI_API_KEY"))

        if has_copilot and has_openai:
            # Both available — ask user
            console.print()
            console.print("  [bold]Multiple backends available:[/bold]")
            console.print("    1. [cyan]copilot[/cyan] — GitHub Copilot Business (Claude, GPT, Gemini)")
            console.print("    2. [cyan]openai[/cyan]  — OpenAI API (GPT models only)")
            console.print()

            while True:
                try:
                    choice = input("  Select backend (copilot/openai) [copilot]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    console.print()
                    sys.exit(0)

                if not choice or choice == "copilot" or choice == "1":
                    return BackendType.COPILOT
                elif choice == "openai" or choice == "2":
                    return BackendType.OPENAI
                else:
                    console.print("  [warning]Invalid choice. Please enter 'copilot' or 'openai'.[/warning]")

        elif has_openai:
            console.print("  [dim]Using OpenAI backend (OPENAI_API_KEY found)[/dim]")
            return BackendType.OPENAI
        else:
            # Default to Copilot (will authenticate or fail with clear error)
            return BackendType.COPILOT

    def _handle_command(self, cmd: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        parts = cmd.strip().split(None, 1)
        command = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if command in ("/quit", "/exit", "/q"):
            raise EOFError()

        elif command == "/help":
            console.print(HELP_TEXT)

        elif command == "/plan":
            return self._handle_plan_command(arg)

        elif command == "/approve":
            return self._handle_approve_command()

        elif command == "/deny":
            return self._handle_deny_command(arg)

        elif command == "/model":
            # Block model switching in plan/exec modes
            if self.plan_state.mode != PermissionMode.NORMAL:
                mode_name = self.plan_state.mode.value
                locked = self.config.get_plan_model(self.backend.backend_type if self.backend else None) if self.plan_state.mode == PermissionMode.PLAN else self.config.get_exec_model(self.backend.backend_type if self.backend else None)
                locked_obj = resolve_model(locked)
                locked_name = locked_obj.name if locked_obj else locked
                console.print(
                    f"  [warning]Model locked to {locked_name} in {mode_name} mode.[/warning]"
                )
                console.print("  [dim]Use /plan stop to return to normal mode.[/dim]")
                return True

            if not arg:
                model = resolve_model(self.current_model)
                name = model.name if model else self.current_model
                model_id = model.id if model else self.current_model
                console.print(f"  Current: [model]{name}[/model] ({model_id})")
                return True

            resolved = resolve_model(arg)
            if resolved:
                # Check backend compatibility
                if self.backend and self.backend.backend_type == BackendType.OPENAI:
                    if not is_model_compatible(arg, "OpenAI"):
                        console.print(
                            f"  [error]Model '{resolved.name}' is not available with OpenAI backend.[/error]\n"
                            "  OpenAI backend only supports OpenAI models (gpt-4o, gpt-5, etc.).\n"
                            "  Restart with --backend copilot for Claude/Gemini models."
                        )
                        return True

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
            # Filter models by backend if using OpenAI
            if self.backend and self.backend.backend_type == BackendType.OPENAI:
                models_to_show = get_models_by_provider("OpenAI")
                title = "Available Models (OpenAI Backend)"
            else:
                models_to_show = MODELS
                title = "Available Models"

            table = Table(
                title=title,
                show_lines=False,
                padding=(0, 2),
                title_style="bold",
            )
            table.add_column("Alias", style="cyan bold")
            table.add_column("Model", style="white")
            table.add_column("Provider", style="dim")
            table.add_column("Description", style="dim")

            for alias, model in models_to_show.items():
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

            # Filter aliases that point to shown models
            shown_keys = set(models_to_show.keys())
            relevant_aliases = {
                k: v for k, v in MODEL_ALIASES.items()
                if v in shown_keys
            }
            if relevant_aliases:
                aliases_str = ", ".join(
                    f"[dim]{k}[/dim]→[cyan]{v}[/cyan]" for k, v in relevant_aliases.items()
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
            removed, remaining = clear_cached_token()
            if removed:
                console.print("  [success]✓[/success] Cached token cleared.")
            else:
                console.print("  [dim]No cached token found.[/dim]")
            if remaining:
                console.print()
                console.print("  [warning]⚠ Still logged in via:[/warning]")
                for src in remaining:
                    console.print(f"    • {src}")
                console.print()
                console.print("  [dim]ClaudeX will use these on next start.[/dim]")
                console.print("  [dim]To fully log out, remove those too.[/dim]")
            else:
                console.print("  Next run will start device flow login.")

        else:
            console.print(
                f"  [warning]Unknown command: {command}[/warning]  "
                f"Type [command]/help[/command] for available commands."
            )

        return True

    # ------------------------------------------------------------------
    # Plan mode commands
    # ------------------------------------------------------------------

    def _handle_plan_command(self, arg: str) -> bool:
        """Handle /plan and its subcommands."""
        sub = arg.lower().strip()

        if sub == "show":
            content = self.plan_state.get_plan_content()
            if content:
                console.print()
                self._render_response(content)
                console.print()
            else:
                console.print("  [dim]No plan file yet.[/dim]")

        elif sub == "path":
            if self.plan_state.plan_path:
                console.print(f"  [dim]{self.plan_state.plan_path}[/dim]")
            else:
                console.print("  [dim]No active plan.[/dim]")

        elif sub == "stop":
            if self.plan_state.mode == PermissionMode.NORMAL:
                console.print("  [dim]Already in normal mode.[/dim]")
            else:
                prev = self.plan_state.mode.value
                self.plan_state.stop()
                console.print(
                    f"  [success]✓[/success] Exited {prev} mode → normal"
                )

        else:
            # Enter plan mode
            if self.plan_state.mode == PermissionMode.PLAN:
                console.print("  [warning]Already in plan mode.[/warning]")
                if self.plan_state.plan_path:
                    console.print(
                        f"  [dim]Plan file: {self.plan_state.plan_path}[/dim]"
                    )
                return True

            plan_path = self.plan_state.enter_plan()
            plan_model = self.config.get_plan_model(self.backend.backend_type if self.backend else None)
            plan_model_obj = resolve_model(plan_model)
            plan_model_name = (
                plan_model_obj.name if plan_model_obj else plan_model
            )
            console.print(
                f"  ⏸ [warning]plan mode on[/warning] "
                f"([model]{plan_model_name}[/model])"
            )
            console.print(f"  [dim]Plan file: {plan_path}[/dim]")
            console.print(
                "  [dim]Read-only tools only. Write the plan, "
                "then /approve or /deny.[/dim]"
            )

            # Inject a system-level instruction so the model knows it's planning
            plan_instruction = (
                f"You are now in PLAN MODE. Your task is to inspect the codebase "
                f"using read-only tools (read_file, list_directory, grep_search, "
                f"web_fetch) and produce a detailed implementation plan. "
                f"Write the plan to: {plan_path}\n"
                f"Do NOT implement anything — only plan. "
                f"When the plan is complete, tell the user to type /approve or /deny."
            )
            self.messages.append(
                {"role": "system", "content": plan_instruction}
            )

            # If user provided a task after /plan, send it
            if arg and sub not in ("show", "path", "stop"):
                asyncio.run(self._send_message(arg))

        return True

    def _handle_approve_command(self) -> bool:
        """Handle /approve — approve plan and start execution."""
        if self.plan_state.mode != PermissionMode.PLAN:
            console.print("  [warning]Not in plan mode. Use /plan first.[/warning]")
            return True

        try:
            plan_content = self.plan_state.approve()
        except ValueError as e:
            console.print(f"  [error]{e}[/error]")
            return True

        exec_model = self.config.get_exec_model(self.backend.backend_type if self.backend else None)
        exec_model_obj = resolve_model(exec_model)
        exec_model_name = (
            exec_model_obj.name if exec_model_obj else exec_model
        )
        console.print(
            f"  ⏵ [success]executing approved plan[/success] "
            f"([model]{exec_model_name}[/model])"
        )

        # Inject approved plan as context + execution instruction
        exec_instruction = (
            f"The user has APPROVED the following plan. You are now in "
            f"EXECUTION MODE. Implement the plan step by step using all "
            f"available tools (bash, read_file, write_file, edit_file, etc.).\n\n"
            f"--- APPROVED PLAN ---\n{plan_content}\n--- END PLAN ---\n\n"
            f"Execute now. Be thorough and complete each step."
        )
        self.messages.append({"role": "user", "content": exec_instruction})

        # Auto-trigger execution
        asyncio.run(self._send_message_exec())

        return True

    def _handle_deny_command(self, feedback: str) -> bool:
        """Handle /deny — deny plan and request revision."""
        if self.plan_state.mode != PermissionMode.PLAN:
            console.print("  [warning]Not in plan mode. Use /plan first.[/warning]")
            return True

        self.plan_state.deny()
        feedback = feedback or "Please revise the plan."

        console.print("  ⏸ [warning]plan denied — revising[/warning]")
        console.print(f"  [dim]Feedback: {feedback}[/dim]")

        deny_msg = (
            f"The plan was DENIED by the user. Feedback: {feedback}\n"
            f"Please revise the plan at {self.plan_state.plan_path} "
            f"and address the feedback. Stay in plan mode."
        )
        self.messages.append({"role": "user", "content": deny_msg})
        asyncio.run(self._send_message(deny_msg))

        return True

    async def _send_message_exec(self):
        """Send the execution trigger message (internal, for /approve)."""
        # This reuses _send_message logic but skips the user input append
        # since we already appended the exec instruction
        try:
            self._refresh_token_if_needed()
        except (SystemExit, Exception) as e:
            console.print(f"\n  [error]{e}[/error]")
            return

        use_model = self.config.get_exec_model(self.backend.backend_type if self.backend else None)
        model_id = get_model_id(use_model)
        model_obj = resolve_model(use_model)
        model_display = model_obj.name if model_obj else use_model
        tools = get_tools_for_mode(self.plan_state.mode.value) if self.tools_enabled else None

        msg_prompt_tokens = 0
        msg_completion_tokens = 0
        msg_start = time.monotonic()

        for iteration in range(MAX_TOOL_ITERATIONS):
            chunks_collected: list[str] = []
            first_chunk_received = False
            live = Live(
                Spinner("dots", text=f"  [dim]Executing ({model_display})...[/dim]"),
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
                result = await self.backend.stream_chat_with_tools(
                    messages=self._build_messages(),
                    model=model_id,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    tools=tools,
                    on_content_chunk=on_chunk,
                )
            except Exception as e:
                live.stop()
                console.print(f"\n  [error]Error: {e}[/error]")
                return
            finally:
                if live.is_started:
                    live.stop()

            msg_prompt_tokens += result.prompt_tokens
            msg_completion_tokens += result.completion_tokens

            # Handle partial (interrupted) result
            if result.partial:
                if result.content:
                    if self.markdown_mode:
                        console.print()
                        self._render_response(result.content)
                    else:
                        print()
                    self.messages.append({"role": "assistant", "content": result.content})
                console.print(
                    "  [warning]⚠ Response interrupted (connection lost). "
                    "Partial content preserved. Send a follow-up to continue.[/warning]"
                )
                console.print()
                return

            if not result.has_tool_calls:
                if result.content:
                    if self.markdown_mode:
                        console.print()
                        self._render_response(result.content)
                    else:
                        print()
                    self.messages.append({"role": "assistant", "content": result.content})

                self.total_prompt_tokens += msg_prompt_tokens
                self.total_completion_tokens += msg_completion_tokens
                elapsed = time.monotonic() - msg_start
                stats = f"{elapsed:.1f}s total"
                if msg_prompt_tokens or msg_completion_tokens:
                    stats += f" · {msg_prompt_tokens + msg_completion_tokens:,} tokens"
                console.print(f"  [dim]{stats}[/dim]")
                console.print()

                # Execution done → back to normal
                self.plan_state.finish_exec()
                console.print("  [success]✓[/success] Execution complete → normal mode")
                console.print()
                return

            # Tool calls — same logic as _send_message
            if result.content:
                if self.markdown_mode:
                    console.print()
                    self._render_response(result.content)
                else:
                    print()

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

            for tc in result.tool_calls:
                try:
                    args = json.loads(tc.arguments_json) if tc.arguments_json else {}
                except json.JSONDecodeError:
                    args = {}

                args_preview = ", ".join(f"{k}={repr(v)[:60]}" for k, v in args.items())
                console.print()
                console.print(f"  [info]⚡ {tc.function_name}[/info]  [dim]{args_preview}[/dim]")

                tool_result = execute_tool(tc.function_name, args, console)

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

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

        console.print("  [warning]Max tool iterations reached[/warning]")
        self.plan_state.finish_exec()
        console.print("  [success]✓[/success] Execution complete → normal mode")

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

    def _detect_plan_intent(self, user_input: str) -> tuple[bool, str]:
        """Detect plan mode intent in natural language input.

        Matches patterns like:
            'in plan mode ...'           -> (True, '...')
            'first plan then implement'  -> (True, 'first plan then implement ...')
            'erst planen dann ...'       -> (True, '...')
            'plan with opus ...'         -> (True, '...')
            'plan mode: ...'             -> (True, '...')
            'im plan modus ...'          -> (True, '...')

        Returns:
            (is_plan, task_text) — task_text is the full input if plan is detected.
        """
        if self.plan_state.mode != PermissionMode.NORMAL:
            return False, user_input

        lower = user_input.lower()

        # Direct patterns: starts with plan-related phrases
        plan_patterns = [
            # English
            r"(?:^|\. )(?:first |start )?(?:in )?plan ?mode",
            r"(?:^|\. )plan (?:with|using|in) (?:opus|claude)",
            r"(?:^|\. )first plan[, ] ?then (?:implement|execute|do|build|code)",
            r"(?:^|\. )(?:use |start )plan mode",
            # German
            r"(?:^|\. )(?:erst(?:mal)? )?(?:im )?plan ?modus",
            r"(?:^|\. )erst(?:mal)? planen[, ] ?dann",
            r"(?:^|\. )(?:zuerst |erst(?:mal)? )?plan(?:en|ung)? (?:mit|in|und dann)",
        ]

        for pattern in plan_patterns:
            if re.search(pattern, lower):
                return True, user_input

        # Check for "plan mode" or "plan modus" anywhere in the text
        if re.search(r"\bplan[- ]?mod(?:e|us)\b", lower):
            return True, user_input

        return False, user_input

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

        # Mode-based model override (enforced, takes priority)
        if self.plan_state.mode == PermissionMode.PLAN:
            use_model = self.config.get_plan_model(self.backend.backend_type if self.backend else None)
            if override_model:
                plan_obj = resolve_model(use_model)
                console.print(f"  [dim]Model locked to {plan_obj.name if plan_obj else use_model} in plan mode[/dim]")
        elif self.plan_state.mode == PermissionMode.EXEC:
            use_model = self.config.get_exec_model(self.backend.backend_type if self.backend else None)
            if override_model:
                exec_obj = resolve_model(use_model)
                console.print(f"  [dim]Model locked to {exec_obj.name if exec_obj else use_model} in exec mode[/dim]")

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

        # Mode-aware tool selection
        if not self.tools_enabled:
            tools = None
        else:
            tools = get_tools_for_mode(self.plan_state.mode.value)

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
                result = await self.backend.stream_chat_with_tools(
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
                if isinstance(self.backend, CopilotBackend):
                    self.copilot_token = None
                return
            except (CopilotAPIError, OpenAIAPIError) as e:
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

            # Handle partial (interrupted) result
            if result.partial:
                if result.content:
                    if self.markdown_mode:
                        console.print()
                        self._render_response(result.content)
                    else:
                        print()
                    self.messages.append(
                        {"role": "assistant", "content": result.content}
                    )
                console.print(
                    "  [warning]⚠ Response interrupted (connection lost). "
                    "Partial content preserved. Send a follow-up to continue.[/warning]"
                )
                console.print()
                return

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

                # Plan mode: enforce tool permissions
                allowed, reason = self.plan_state.is_tool_allowed(
                    tc.function_name, args
                )
                if not allowed:
                    console.print(f"  [error]{reason}[/error]")
                    tool_result = f"BLOCKED: {reason}"
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_result,
                        }
                    )
                    continue

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
        """Build the prompt showing CWD, mode indicator, and model."""
        cwd = os.path.basename(os.getcwd()) or "/"
        if self.plan_state.mode == PermissionMode.PLAN:
            return [
                ("class:cwd", f"{cwd}"),
                ("class:plan", " ⏸plan"),
                ("class:prompt", " › "),
            ]
        elif self.plan_state.mode == PermissionMode.EXEC:
            return [
                ("class:cwd", f"{cwd}"),
                ("class:exec", " ⏵exec"),
                ("class:prompt", " › "),
            ]
        return [
            ("class:cwd", f"{cwd}"),
            ("class:prompt", " › "),
        ]

    def run(self):
        """Main sync REPL loop."""
        # --- Determine and initialize backend ---
        if not self.backend_type:
            # Auto-select backend based on availability
            self.backend_type = self._select_backend()

        # Initialize backend based on type
        if self.backend_type == BackendType.COPILOT:
            try:
                self.github_token, self.copilot_token = ensure_auth(console, debug=self.debug)
                self.backend = CopilotBackend(
                    self.github_token, self.copilot_token, debug=self.debug
                )
            except SystemExit as e:
                console.print(f"  [error]{e}[/error]")
                return
            except Exception as e:
                console.print(f"  [error]Authentication failed: {e}[/error]")
                return
        elif self.backend_type == BackendType.OPENAI:
            self.backend = OpenAIBackend()
            if not self.backend.is_available():
                console.print()
                console.print(
                    "  [error]OpenAI API key not found.[/error]\n"
                    "  Set the OPENAI_API_KEY environment variable:\n"
                    "    export OPENAI_API_KEY='your-api-key'\n"
                )
                return

        # Validate model compatibility with backend
        if self.backend.backend_type == BackendType.OPENAI:
            if not is_model_compatible(self.current_model, "OpenAI"):
                resolved = resolve_model(self.current_model)
                model_name = resolved.name if resolved else self.current_model
                # Auto-switch to a compatible OpenAI model
                default_openai_model = get_default_model_for_provider("OpenAI")
                self.current_model = default_openai_model
                default_model_obj = resolve_model(default_openai_model)
                console.print()
                console.print(
                    f"  [warning]Model '{model_name}' is not available with OpenAI backend.[/warning]\n"
                    f"  [info]Automatically switched to {default_model_obj.name}.[/info]\n"
                    "  [dim]Use --backend copilot for Claude/Gemini models.[/dim]\n"
                )

        # --- Banner ---
        model = resolve_model(self.current_model)
        model_display = model.name if model else self.current_model

        console.print()
        console.print(
            Panel(
                f"[bold white]ClaudeX[/bold white]  [dim]v{__version__}[/dim]\n"
                f"[dim]{self.backend.name}[/dim] · [model]{model_display}[/model]\n"
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

        # Show authentication status
        resolved = resolve_model(self.current_model)
        if resolved:
            console.print(
                f"  [success]✓[/success] Ready — [model]{resolved.name}[/model]\n"
            )
        else:
            console.print(
                f"  [success]✓[/success] Ready — [model]{self.current_model}[/model]\n"
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
            "plan": "#ff8800 bold",
            "exec": "#00ccff bold",
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

            # Detect plan mode intent in natural language
            is_plan, task_text = self._detect_plan_intent(user_input)
            if is_plan:
                self._handle_plan_command(task_text)
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
        description="ClaudeX — CLI for GitHub Copilot Business and OpenAI models",
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=None,
        help="Model to use (e.g. opus, sonnet, gpt-4o, gpt-5)",
    )
    parser.add_argument(
        "--backend",
        "--provider",
        dest="backend",
        type=str,
        choices=["copilot", "openai"],
        default=None,
        help="Backend to use: copilot (GitHub Copilot Business) or openai (OpenAI API)",
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
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Start in plan mode (Opus for planning, Sonnet for execution)",
    )

    args = parser.parse_args()

    if args.list_models:
        list_models()
        return

    if args.logout:
        removed, remaining = clear_cached_token()
        if removed:
            console.print("  [success]✓[/success] Cached token cleared.")
        else:
            console.print("  [dim]No cached token found.[/dim]")
        if remaining:
            console.print()
            console.print("  [warning]⚠ Still logged in via:[/warning]")
            for src in remaining:
                console.print(f"    • {src}")
            console.print()
            console.print("  [dim]ClaudeX will use these on next start.[/dim]")
        return

    # Parse backend type
    backend_type = None
    if args.backend:
        if args.backend == "copilot":
            backend_type = BackendType.COPILOT
        elif args.backend == "openai":
            backend_type = BackendType.OPENAI

    cli = ClaudeXCLI(model=args.model, debug=args.debug, backend_type=backend_type)
    if args.plan:
        plan_path = cli.plan_state.enter_plan()
        console.print(f"  ⏸ [warning]plan mode on[/warning] ([model]Opus[/model])")
        console.print(f"  [dim]Plan file: {plan_path}[/dim]")
    try:
        cli.run()
    except KeyboardInterrupt:
        print("\n")


if __name__ == "__main__":
    main()
