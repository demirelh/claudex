# ClaudeX CLI — Implementation Plan

## Problem

The ClaudeX repo provides a LiteLLM gateway routing to **GitHub Models API** (`models.github.ai`),
but Claude/Anthropic models are **not available** on GitHub Models (as of Feb 2026).

However, the user has **GitHub Copilot Business**, which provides access to Claude Opus 4, Sonnet 4,
GPT-4o, and other models via the **Copilot API** (`api.githubcopilot.com`).

Currently there is **no CLI tool** in this repo — only gateway infrastructure.

## Goal

Build a standalone Python CLI (`claudex`) that:
1. Authenticates with GitHub via OAuth device flow (like the VS Code Copilot extension does)
2. Exchanges the GitHub token for a Copilot session token
3. Calls the Copilot Chat Completions API to access Claude models
4. Provides an interactive terminal REPL with streaming — like Claude Code (`claude` CLI)

## Architecture

```
User ──> claudex CLI ──> GitHub OAuth (device flow)
                   │
                   └──> Copilot API (api.githubcopilot.com/chat/completions)
                              │
                              └──> Claude Opus 4, Sonnet 4, GPT-4o, etc.
```

### Auth Flow
1. GitHub Device Flow with Copilot client ID → OAuth token
2. Exchange OAuth token → short-lived Copilot session token (via `/copilot_internal/v2/token`)
3. Use Copilot token for API calls (auto-refresh on expiry)

### Package Structure
```
claudex/
├── __init__.py          # Package version
├── __main__.py          # python -m claudex entry point
├── auth.py              # GitHub OAuth device flow + Copilot token exchange
├── client.py            # Copilot API client (streaming SSE)
├── models.py            # Available model definitions + aliases
├── config.py            # User configuration (~/.config/claudex/)
└── cli.py               # Interactive REPL with slash commands
```

## Features
- Interactive terminal REPL with prompt history
- Streaming responses (SSE)
- Model switching (`/model opus`, `/model sonnet`, `/model gpt-4o`)
- System prompt support (`/system <msg>`)
- Conversation management (`/clear`)
- Token caching (`~/.config/claudex/`)
- Auto token refresh (Copilot tokens expire ~30min)
- Multiple auth methods: GITHUB_TOKEN env, cached token, or interactive device flow

## Models (via Copilot Business)
| Alias       | Model ID                        | Provider   |
|-------------|--------------------------------|------------|
| `opus`      | `claude-opus-4-20250514`       | Anthropic  |
| `sonnet`    | `claude-sonnet-4-20250514`     | Anthropic  |
| `haiku`     | `claude-3.5-haiku-20241022`    | Anthropic  |
| `gpt-4o`    | `gpt-4o`                       | OpenAI     |
| `gpt-4.1`   | `gpt-4.1`                      | OpenAI     |
| `o3-mini`   | `o3-mini`                      | OpenAI     |
| `o4-mini`   | `o4-mini`                      | OpenAI     |

## Dependencies
- `httpx` — async HTTP client with SSE streaming
- `rich` — terminal UI, panels, tables
- `prompt-toolkit` — REPL with history / key bindings

## Usage
```bash
# Install
cd claudex && pip install -e .

# Run
claudex

# Or with a specific model
claudex --model opus

# Or set GITHUB_TOKEN to skip device flow
export GITHUB_TOKEN=ghp_xxx
claudex
```
