# AI Gateway

Enterprise AI Gateway that routes LLM requests through [GitHub Models API](https://docs.github.com/en/github-models), enabling centralized billing via GitHub Enterprise.

Built on [LiteLLM Proxy](https://github.com/BerriAI/litellm) with PII masking, rate limiting, team-based API keys, and full audit logging.

## Architecture

```mermaid
flowchart TB
    subgraph clients["Developer Workstation"]
        claude["Claude Code"]
        vscode["VS Code / Cursor"]
        sdk["OpenAI SDK / curl"]
    end

    subgraph gateway["Internal Network (Docker / K8s)"]
        direction TB
        subgraph litellm["LiteLLM Proxy :4000"]
            direction LR
            auth["Auth\n+ Virtual Keys\n+ Rate Limits"]
            format["Format Translation\nAnthropic ↔ OpenAI"]
            guardrails["Guardrails\n+ PII Masking"]
            cache["Response Cache"]
        end

        subgraph backing["Backing Services"]
            direction LR
            postgres[("PostgreSQL\nKeys, Budgets,\nAudit Logs")]
            redis[("Redis\nCache +\nRate Limits")]
        end

        subgraph presidio["Presidio PII Engine"]
            direction LR
            analyzer["Analyzer :3000\nDetect PII"]
            anonymizer["Anonymizer :3000\nMask PII"]
        end
    end

    subgraph github["GitHub Cloud"]
        models["GitHub Models API\nmodels.github.ai/inference"]
        billing["GitHub Enterprise\nBilling"]
    end

    subgraph mcp["Code Context (MCP)"]
        ghserver["GitHub MCP Server\n77 tools: repos, PRs,\nissues, search"]
    end

    claude -- "ANTHROPIC_BASE_URL\n/v1/messages" --> litellm
    vscode -- "/v1/chat/completions" --> litellm
    sdk -- "/v1/chat/completions" --> litellm

    auth --> guardrails
    guardrails --> format
    format --> cache

    litellm --> postgres
    litellm --> redis
    guardrails -.-> analyzer
    guardrails -.-> anonymizer

    cache -- "OpenAI format\nBearer PAT" --> models
    models --> billing

    claude -. "stdio" .-> ghserver
    ghserver -. "GitHub API" .-> github
```

### Request Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant L as LiteLLM Proxy
    participant P as Presidio
    participant G as GitHub Models API

    C->>L: POST /v1/messages (Anthropic format)
    activate L
    L->>L: Authenticate virtual key
    L->>L: Check budget + rate limits
    L->>P: Scan prompt for PII
    P-->>L: Masked prompt
    L->>L: Translate Anthropic → OpenAI format
    L->>G: POST /chat/completions (OpenAI format)
    G-->>L: OpenAI response
    L->>P: Scan response for PII
    P-->>L: Masked response
    L->>L: Translate OpenAI → Anthropic format
    L-->>C: Anthropic Messages response
    deactivate L
```

## Available Models

All models are billed through GitHub Enterprise. Current catalog (Feb 2026):

| Alias | Provider | GitHub Model ID |
|-------|----------|-----------------|
| `gpt-4.1` | OpenAI | `openai/gpt-4.1` |
| `gpt-4.1-mini` | OpenAI | `openai/gpt-4.1-mini` |
| `gpt-4.1-nano` | OpenAI | `openai/gpt-4.1-nano` |
| `gpt-4o` | OpenAI | `openai/gpt-4o` |
| `o3-mini` | OpenAI | `openai/o3-mini` |
| `o4-mini` | OpenAI | `openai/o4-mini` |
| `llama-4-scout` | Meta | `meta/llama-4-scout-17b-16e-instruct` |
| `llama-4-maverick` | Meta | `meta/llama-4-maverick-17b-128e-instruct-fp8` |
| `llama-3.3-70b` | Meta | `meta/llama-3.3-70b-instruct` |
| `deepseek-r1` | DeepSeek | `deepseek/deepseek-r1` |
| `mistral-medium` | Mistral | `mistral-ai/mistral-medium-2505` |
| `codestral` | Mistral | `mistral-ai/codestral-2501` |
| `grok-3` | xAI | `xai/grok-3` |
| `grok-3-mini` | xAI | `xai/grok-3-mini` |

> **Note:** Claude/Anthropic models are **not** available on GitHub Models as of 2026-02-15. The config contains a commented-out section to enable them when they appear.

## Quick Start

### Prerequisites

- Docker + Docker Compose
- GitHub PAT with `models:read` scope ([create one](https://github.com/settings/tokens?type=beta))

### 1. Setup

```bash
git clone https://github.com/demirelh/ai-gateway.git
cd ai-gateway
make setup
```

This will:
- Create `.env` from template (you fill in your GitHub PAT)
- Start all services (LiteLLM, PostgreSQL, Redis, Presidio)
- Run a smoke test

### 2. Verify

```bash
make status
# or
make test-quick
```

### 3. Use

```bash
# Set in your shell profile
export ANTHROPIC_BASE_URL=http://localhost:4000
export ANTHROPIC_AUTH_TOKEN=<your-litellm-master-key>

# Claude Code works through the gateway
claude

# Or use curl directly (OpenAI format)
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4.1-mini",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'

# Anthropic Messages format also works
curl -X POST http://localhost:4000/v1/messages \
  -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "gpt-4.1-mini",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Team Key Management

Create per-team API keys with budget limits and model restrictions:

```bash
# Auto-create keys for predefined teams
make keys

# Or manually
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "team-backend",
    "max_budget": 100.0,
    "budget_duration": "30d",
    "models": ["gpt-4.1", "gpt-4.1-mini", "deepseek-r1"]
  }'
```

Each team key enforces:
- **Budget cap** (monthly spend limit)
- **Model allowlist** (only specified models accessible)
- **Rate limits** (configurable per key)

## Project Structure

```
ai-gateway/
├── config/
│   ├── litellm-config.yaml      # Model routing, guardrails, cache config
│   └── managed-mcp.json         # Org-wide MCP policy template
├── docker-compose.yaml          # Local dev: LiteLLM + Postgres + Redis + Presidio
├── .env.example                 # Environment variable template
├── .mcp.json                    # GitHub MCP Server config for projects
├── Makefile                     # All common operations
├── scripts/
│   ├── setup.sh                 # First-time setup
│   ├── create-team-keys.sh      # Generate team API keys
│   └── test-gateway.sh          # Quick validation without pytest
├── tests/                       # pytest test suite
│   ├── test_health.py           # Health probes
│   ├── test_auth.py             # Auth + virtual keys
│   ├── test_anthropic_format.py # Anthropic Messages API translation
│   ├── test_openai_format.py    # OpenAI Chat Completions passthrough
│   ├── test_streaming.py        # SSE streaming (both formats)
│   ├── test_tool_use.py         # Function calling / tool use
│   ├── test_pii_redaction.py    # Presidio PII masking
│   └── test_rate_limiting.py    # Budget limits + model restrictions
├── k8s/
│   ├── base/                    # Kustomize base (namespace, deployments, network policies, HPA)
│   └── overlays/production/     # Production overlay (higher replicas, resources)
└── docs/
    └── PLAN.md                  # Full architecture plan & implementation brief
```

## Makefile Commands

```
make setup            # First-time setup (env, start, smoke test)
make up               # Start all services
make down             # Stop all services
make restart          # Restart all services
make status           # Show service status + health check
make logs             # Tail all service logs
make logs-litellm     # Tail LiteLLM logs only
make keys             # Create team virtual keys
make test             # Run full pytest suite
make test-quick       # Quick curl-based validation
make test-integration # Integration tests only
make test-guardrails  # PII/guardrail tests only
make k8s-deploy-base  # Deploy to Kubernetes (base)
make k8s-deploy-prod  # Deploy to Kubernetes (production)
make clean            # Remove containers + volumes
```

## Kubernetes Deployment

```bash
# Validate manifests
make k8s-dry-run

# Deploy base config (2 replicas)
make k8s-deploy-base

# Deploy production overlay (3+ replicas, higher resources)
make k8s-deploy-prod
```

The K8s setup includes:
- **Pod Security Standards**: `restricted` profile
- **NetworkPolicies**: egress only to `models.github.ai:443`
- **HPA**: auto-scale 2-8 (base) or 3-16 (prod) replicas on CPU/memory
- **PDB**: minimum 1 pod always available
- **Ingress**: internal-only with IP whitelist and SSE streaming support

## Security

- **PII Masking**: Presidio scans all prompts/responses for credit cards, emails, IBANs, phone numbers, SSNs, and GitHub PATs before they reach the LLM
- **Auth**: Every request requires a valid API key (master or virtual team key)
- **Budget Controls**: Per-team spending limits with configurable durations
- **Model Restrictions**: Team keys can be locked to specific models
- **Network Isolation**: K8s NetworkPolicies restrict egress to GitHub APIs only
- **No secrets in logs**: API keys are never logged; Presidio masks sensitive data in log output

See [docs/PLAN.md](docs/PLAN.md) for the full security checklist (OWASP, SSRF, prompt injection mitigations).

## Configuration

### Adding Models

Edit `config/litellm-config.yaml` and add a new entry. Model names come from `gh models list`:

```yaml
- model_name: "my-alias"          # Name your users will use
  litellm_params:
    model: "openai/<provider>/<model-id>"  # From GitHub Models catalog
    api_key: "os.environ/GITHUB_MODELS_PAT"
    api_base: "https://models.github.ai/inference"
```

Restart with `make restart` after config changes.

### Environment Variables

See [.env.example](.env.example) for all available variables. Required:

| Variable | Description |
|----------|-------------|
| `GITHUB_MODELS_PAT` | GitHub PAT with `models:read` scope |
| `LITELLM_MASTER_KEY` | Admin key for proxy management |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `DATABASE_URL` | Full PostgreSQL connection string |

## License

Internal use only.
