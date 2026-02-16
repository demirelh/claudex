"""Tool definitions and execution for ClaudeX CLI.

Implements local tool execution that the LLM can invoke:
  - bash: Run shell commands
  - read_file: Read file contents
  - write_file: Write/create files
  - list_directory: List directory contents
  - web_fetch: Fetch URL content

Tools use the OpenAI function calling format.
"""

import json
import os
import subprocess
import traceback
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function calling format)
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Execute a shell command on the user's machine. "
                "Use this for running programs, installing packages, "
                "searching files, git operations, system tasks, etc. "
                "The command runs in the user's current working directory. "
                "Commands time out after 120 seconds."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file. Returns the full text content. "
                "Use this to examine source code, configs, logs, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file (absolute or relative to cwd)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write content to a file. Creates the file if it doesn't exist, "
                "overwrites if it does. Creates parent directories as needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file (absolute or relative to cwd)",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": (
                "List the contents of a directory. Returns file/folder names "
                "with type indicators (/ for directories). "
                "Useful to explore project structure."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory (default: current directory)",
                        "default": ".",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": (
                "Fetch the content of a URL. Returns the response text. "
                "Use this to check websites, download content, query APIs, etc. "
                "Supports HTTP/HTTPS. Timeout: 30 seconds."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, etc.)",
                        "default": "GET",
                        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"],
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers as key-value pairs",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional request body (for POST/PUT/PATCH)",
                    },
                },
                "required": ["url"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def execute_tool(name: str, arguments: dict[str, Any], console=None) -> str:
    """Execute a tool and return the result as a string.

    Args:
        name: Tool function name.
        arguments: Tool arguments dict.
        console: Optional Rich console for output.

    Returns:
        Result string to send back to the model.
    """
    try:
        if name == "bash":
            return _run_bash(arguments, console)
        elif name == "read_file":
            return _run_read_file(arguments, console)
        elif name == "write_file":
            return _run_write_file(arguments, console)
        elif name == "list_directory":
            return _run_list_directory(arguments, console)
        elif name == "web_fetch":
            return _run_web_fetch(arguments, console)
        else:
            return f"Error: Unknown tool '{name}'"
    except Exception as e:
        return f"Error executing {name}: {e}"


def _run_bash(args: dict, console=None) -> str:
    """Execute a shell command."""
    command = args.get("command", "")
    if not command:
        return "Error: No command provided"

    if console:
        console.print(f"  [dim]$ {command}[/dim]")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.getcwd(),
        )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n"
            output += result.stderr

        if result.returncode != 0:
            output += f"\n[Exit code: {result.returncode}]"

        # Truncate very long output
        if len(output) > 50000:
            output = output[:25000] + "\n\n... (truncated) ...\n\n" + output[-25000:]

        return output.strip() if output.strip() else "(no output)"

    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120 seconds"


def _run_read_file(args: dict, console=None) -> str:
    """Read a file's contents."""
    path = args.get("path", "")
    if not path:
        return "Error: No path provided"

    filepath = Path(path).expanduser()
    if not filepath.is_absolute():
        filepath = Path.cwd() / filepath

    if console:
        console.print(f"  [dim]📄 Reading {filepath}[/dim]")

    if not filepath.exists():
        return f"Error: File not found: {filepath}"
    if not filepath.is_file():
        return f"Error: Not a file: {filepath}"

    try:
        content = filepath.read_text(errors="replace")
        # Truncate very large files
        if len(content) > 100000:
            content = content[:50000] + "\n\n... (truncated, file is very large) ...\n\n" + content[-50000:]
        return content
    except Exception as e:
        return f"Error reading file: {e}"


def _run_write_file(args: dict, console=None) -> str:
    """Write content to a file."""
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return "Error: No path provided"

    filepath = Path(path).expanduser()
    if not filepath.is_absolute():
        filepath = Path.cwd() / filepath

    if console:
        action = "Overwriting" if filepath.exists() else "Creating"
        console.print(f"  [dim]📝 {action} {filepath}[/dim]")

    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        return f"Successfully wrote {len(content)} bytes to {filepath}"
    except Exception as e:
        return f"Error writing file: {e}"


def _run_list_directory(args: dict, console=None) -> str:
    """List directory contents."""
    path = args.get("path", ".")

    dirpath = Path(path).expanduser()
    if not dirpath.is_absolute():
        dirpath = Path.cwd() / dirpath

    if console:
        console.print(f"  [dim]📁 Listing {dirpath}[/dim]")

    if not dirpath.exists():
        return f"Error: Directory not found: {dirpath}"
    if not dirpath.is_dir():
        return f"Error: Not a directory: {dirpath}"

    try:
        entries = sorted(dirpath.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = []
        for entry in entries:
            if entry.name.startswith("."):
                continue  # Skip hidden files by default
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {e}"


def _run_web_fetch(args: dict, console=None) -> str:
    """Fetch URL content."""
    url = args.get("url", "")
    method = args.get("method", "GET").upper()
    headers = args.get("headers", {})
    body = args.get("body")

    if not url:
        return "Error: No URL provided"

    if console:
        console.print(f"  [dim]🌐 {method} {url}[/dim]")

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.request(
                method,
                url,
                headers=headers or {},
                content=body.encode() if body else None,
            )

            # Build result
            result = f"HTTP {response.status_code} {response.reason_phrase}\n"
            result += f"Content-Type: {response.headers.get('content-type', 'unknown')}\n\n"

            text = response.text
            # Truncate very large responses
            if len(text) > 50000:
                text = text[:25000] + "\n\n... (truncated) ...\n\n" + text[-25000:]
            result += text

            return result

    except httpx.TimeoutException:
        return f"Error: Request timed out after 30 seconds"
    except httpx.ConnectError as e:
        return f"Error: Could not connect to {url}: {e}"
    except Exception as e:
        return f"Error fetching URL: {e}"
