# ClaudeX

A **Claude Code-like CLI** that supports **GitHub Copilot Business** and **OpenAI API** — access Claude Opus, Sonnet, GPT-5, Gemini, and more from your terminal.

Choose your backend: GitHub Copilot Business (no extra billing) or OpenAI API (direct access with your API key).

## Features

- **Multiple backends** — GitHub Copilot Business or OpenAI API
- **Interactive REPL** with streaming responses
- **16 models** — Claude Opus/Sonnet/Haiku, GPT-5/4o, Gemini 2.5 Pro, Codex
- **7 built-in tools** — bash, read/write/edit files, grep, directory listing, web fetch
- **@model prefix** — `@opus explain this` switches model for one message
- **Natural language model switching** — "verwende opus und ..." or "use sonnet and ..."
- **Markdown rendering** — toggle with `/markdown`
- **Multi-line input** — Alt+Enter for newlines
- **Token tracking** — TTFT, total time, token count per message
- **Thinking spinner** — animated indicator while waiting for response
- **Session history** — persistent across sessions
- **Plan Mode** — Backend-aware: Opus/Sonnet for Copilot, GPT-5/5-Mini for OpenAI, with approval gate

## Quick Start

### Prerequisites

- **Python 3.10+**
- **One of:**
  - **GitHub Copilot Business** subscription (Individual works too), OR
  - **OpenAI API key**
- **Git** (to clone)

### Install

**One-liner (empfohlen):**

```bash
git clone https://github.com/demirelh/claudex.git && cd claudex && ./install.sh
```

Das Skript:
1. Prüft Python 3.10+
2. Installiert via **pipx** (bevorzugt, isolierte Umgebung) oder `pip --user` (Fallback)
3. Macht `claudex` global in jedem Terminal verfügbar

**Oder manuell:**

```bash
# Option A: pipx (empfohlen — isoliert, global verfügbar)
pipx install git+https://github.com/demirelh/claudex.git

# Option B: pip --user (global ohne venv)
pip install --user git+https://github.com/demirelh/claudex.git

# Option C: Dev-Install (zum Mitentwickeln)
git clone https://github.com/demirelh/claudex.git
cd claudex
pip install -e .
```

> **Hinweis:** Bei `pip --user` muss `~/.local/bin` im PATH sein:
> ```bash
> echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
> ```

**Update:**

```bash
cd claudex && git pull && ./install.sh
# oder: pipx upgrade claudex
```

### Run

```bash
claudex
```

On first run, ClaudeX authenticates via **GitHub Device Flow**:

1. A URL and code are displayed
2. Open the URL in your browser
3. Enter the code and authorize
4. Token is cached in `~/.config/claudex/` — you won't need to do this again

```
╭──────────────────────────────────────────╮
│  ClaudeX  v0.1.0                         │
│  GitHub Copilot Business · Claude Sonnet 4│
│  cwd: /home/user/project                 │
╰──────────────────────────────────────────╯
  ✓ Authenticated — Claude Sonnet 4

project › hello!
  ⠋ Thinking (Claude Sonnet 4)...
  Hi! How can I help you today?
  TTFT 0.8s · 1.2s total · 42 tokens
```

### CLI Options

```bash
claudex                       # Default model (Claude Sonnet 4), auto-select backend
claudex --backend copilot     # Use GitHub Copilot Business backend
claudex --backend openai      # Use OpenAI API backend
claudex --model opus          # Start with Claude Opus 4.6
claudex -m gpt-5              # Start with GPT-5
claudex --list-models         # Show all available models
claudex --version             # Show version
```

### Backend Selection

ClaudeX supports two backends:

#### 1. GitHub Copilot Business (default)
- Uses your existing Copilot subscription
- No extra API keys needed
- Access to all models: Claude (Opus, Sonnet, Haiku), GPT (5, 4o, 4.1), Gemini
- Authentication via GitHub OAuth

```bash
claudex --backend copilot
```

#### 2. OpenAI API
- Requires `OPENAI_API_KEY` environment variable
- Direct OpenAI API access
- **Only supports OpenAI models** (gpt-4o, gpt-5, gpt-5-mini, etc.)
- Optional custom endpoint via `OPENAI_BASE_URL`

```bash
export OPENAI_API_KEY='sk-...'
claudex --backend openai
```

**Auto-selection:** If you don't specify `--backend`:
- If both backends are available (GitHub token + OPENAI_API_KEY), you'll be prompted to choose
- If only one is available, it's selected automatically
- If neither is available, GitHub auth flow starts

**Environment variables:**
- `OPENAI_API_KEY` — Your OpenAI API key
- `OPENAI_BASE_URL` — Custom OpenAI-compatible endpoint (optional, defaults to `https://api.openai.com/v1`)

**Model compatibility:**
- Copilot backend: All models (Claude, GPT, Gemini)
- OpenAI backend: Only OpenAI models (gpt-4o, gpt-5, etc.)

When using `--backend openai`, ClaudeX automatically switches to `gpt-4o` if the default or specified model is incompatible. Attempting to manually switch to an incompatible model (e.g., `/model opus`) will show an error message.

## Usage

### Slash Commands

| Command | Description |
|---------|-------------|
| `/model <name>` | Switch model permanently (e.g. `/model opus`) |
| `/models` | List all available models |
| `/system <msg>` | Set system prompt |
| `/clear` | Clear conversation history |
| `/compact` | Compress history (keep last 4 messages) |
| `/config` | Show current config + token stats |
| `/tools` | List available tools |
| `/tools on\|off` | Enable/disable tool use |
| `/markdown` | Toggle Markdown rendering |
| `/save` | Save current config to disk |
| `/logout` | Clear cached GitHub token |
| `/plan [task]` | Enter plan mode (Opus inspects + writes plan) |
| `/plan show` | Display current plan |
| `/plan stop` | Exit plan/exec mode → normal |
| `/approve` | Approve plan → start execution (Sonnet) |
| `/deny [feedback]` | Deny plan, request revision |
| `/help` | Show all commands |
| `/quit` | Exit |

### Model Switching

**Permanent switch** — all following messages use this model:
```
project › /model opus
  ✓ Switched to Claude Opus 4.6
```

**One-off with @prefix** — only this message uses the model:
```
project › @opus explain quantum computing
  [Using Claude Opus 4.6 for this message]
  ...
project › next message    ← back to default model
```

**Natural language** — ClaudeX detects model names in phrases like:
```
project › verwende opus und überprüfe die Datei
project › use gpt-5 and write a test
project › nutze gemini und erkläre mir das
project › mit haiku, schreib einen Einzeiler
```

### Built-in Tools

ClaudeX can execute actions on your machine via function calling:

| Tool | Description |
|------|-------------|
| `bash` | Run shell commands |
| `read_file` | Read file contents |
| `write_file` | Create/overwrite files |
| `edit_file` | Search & replace in files |
| `list_directory` | List directory contents |
| `grep_search` | Regex search across files |
| `web_fetch` | Fetch URLs |

Tools are **enabled by default**. Toggle with `/tools on` or `/tools off`.

### Plan Mode

Plan Mode splits complex tasks into a planning phase and an execution phase, with a mandatory approval gate in between.

**Default models (Copilot backend)**:
- Planning: Claude Opus 4.6
- Execution: Claude Sonnet 4

**OpenAI backend**:
- Planning: GPT-5
- Execution: GPT-5 Mini

**Workflow**: `NORMAL → /plan → PLAN → /approve → EXEC → done → NORMAL`

You can also trigger plan mode via **natural language** — no `/plan` command needed:
```
project › in plan mode, refactor the auth module
  ⏸ plan mode on (Claude Opus 4.6)

project › first plan then implement the changes
  ⏸ plan mode on (Claude Opus 4.6)

project › erst planen dann implementieren
  ⏸ plan mode on (Claude Opus 4.6)
```

Or use the explicit command:

```
project › /plan refactor the auth module
  ⏸ plan mode on (Claude Opus 4.6)
  Plan file: ~/.config/claudex/plans/20250101-120000-plan.md
  Read-only tools only. Write the plan, then /approve or /deny.

  [Opus inspects codebase with read-only tools, writes plan...]

project ⏸plan › /plan show
  # Refactoring Plan
  1. Extract token refresh into separate class...

project ⏸plan › /approve
  ⏵ executing approved plan (Claude Sonnet 4)
  [Sonnet implements each step with full tool access...]
  ✓ Execution complete → normal mode
```

**Rules**:
- **Plan phase**: Model locked to Opus. Only read-only tools (`read_file`, `list_directory`, `grep_search`, `web_fetch`) + writing to the plan file.
- **Exec phase**: Model locked to Sonnet. All tools available.
- **`/deny [feedback]`**: Rejects the plan and sends feedback to Opus for revision.
- **`/plan stop`**: Force-exit any mode back to normal.
- **`@model` and `/model` are locked** during plan/exec modes.

Start with `--plan` flag to enter plan mode immediately:
```bash
claudex --plan
```

## Available Models

All models accessed via your GitHub Copilot Business subscription — no extra API keys:

| Alias | Model | Provider |
|-------|-------|----------|
| `opus` | Claude Opus 4.6 | Anthropic |
| `opus-4.5` | Claude Opus 4.5 | Anthropic |
| `sonnet` | Claude Sonnet 4 | Anthropic |
| `sonnet-4.5` | Claude Sonnet 4.5 | Anthropic |
| `haiku` | Claude Haiku 4.5 | Anthropic |
| `gemini` | Gemini 2.5 Pro | Google |
| `gpt-5` | GPT-5 | OpenAI |
| `gpt-5-mini` | GPT-5 Mini | OpenAI |
| `gpt-4o` | GPT-4o | OpenAI |
| `gpt-4o-mini` | GPT-4o Mini | OpenAI |
| `gpt-4.1` | GPT-4.1 | OpenAI |
| `codex` | GPT-5.3 Codex | OpenAI |

Run `claudex --list-models` for the full list with descriptions.

## Configuration

Settings are stored in `~/.config/claudex/config.json`:

```json
{
  "default_model": "sonnet",
  "temperature": 0.0,
  "max_tokens": 16384,
  "system_prompt": null,
  "plan_model": "opus",
  "exec_model": "sonnet",
  "plan_model_openai": "gpt-5",
  "exec_model_openai": "gpt-5-mini",
  "plan_dir": "~/.config/claudex/plans"
}
```

**Backend-specific plan/exec models**:
- `plan_model` / `exec_model`: Used with Copilot backend (default: opus/sonnet)
- `plan_model_openai` / `exec_model_openai`: Used with OpenAI backend (default: gpt-5/gpt-5-mini)

Edit via slash commands (`/model`, `/system`) and persist with `/save`.

## Project Structure

```
claudex/
├── claudex/                   # Python CLI package
│   ├── __init__.py            # Package version
│   ├── __main__.py            # python -m claudex
│   ├── auth.py                # GitHub OAuth device flow + Copilot token
│   ├── client.py              # Copilot API streaming client
│   ├── cli.py                 # Interactive REPL
│   ├── config.py              # User config persistence
│   ├── models.py              # Model definitions + aliases
│   ├── plan_mode.py           # Plan Mode state machine
│   └── tools.py               # Tool definitions + execution
├── pyproject.toml             # Package config (pip install -e .)
├── config/                    # Gateway config (optional)
├── docker-compose.yaml        # Gateway services (optional)
├── k8s/                       # Kubernetes deployment (optional)
├── scripts/                   # Helper scripts
└── tests/                     # Test suite
```

## How It Works

1. **Auth**: OAuth Device Flow → GitHub token cached locally → exchanged for Copilot session token (auto-refreshes every ~30 min)
2. **API**: Sends OpenAI-compatible chat completions to `api.githubcopilot.com` with headers mimicking VS Code Copilot Chat
3. **Streaming**: SSE streaming with tool call delta parsing
4. **Tools**: Function calling in OpenAI format — model requests tool calls, ClaudeX executes locally, results sent back

## Gateway (Optional, for Teams)

The repo also includes an optional **LiteLLM gateway** for team use with centralized billing, PII masking, rate limiting, and audit logging. See [docker-compose.yaml](docker-compose.yaml) and [docs/PLAN.md](docs/PLAN.md) for details.

```bash
make setup   # Set up gateway
make up      # Start services
make keys    # Create team API keys
```

## License

MIT
