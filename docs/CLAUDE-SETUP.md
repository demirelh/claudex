# Quick Start: Claude Models with ClaudeX

## 🎯 What Changed?

Claude Sonnet 4.5 and Opus 4.6 are now available in ClaudeX!

**Why weren't they available before?**
- ClaudeX was configured only for GitHub Models API (models.github.ai)
- GitHub Models API offers OpenAI, Meta, DeepSeek, etc. but **NOT** Claude
- The config had Claude models commented out with "not available"

**The fix:** Direct Anthropic API integration

## 🚀 Quick Setup (5 minutes)

### Step 1: Get an API Key

**Option A: Anthropic API Key (Recommended)**
1. Go to https://console.anthropic.com/settings/keys
2. Create new key
3. Copy the key (starts with `sk-ant-`)

**Option B: GitHub Copilot Business**
- If you have GitHub Copilot Business, see "Using GitHub Copilot" section below

### Step 2: Configure ClaudeX

```bash
# Copy example config
cp .env.example .env

# Edit .env and add your key:
# ANTHROPIC_API_KEY=sk-ant-your-key-here
nano .env  # or use your favorite editor
```

### Step 3: Start ClaudeX

```bash
make restart
```

### Step 4: Test It!

```bash
# Configure your shell
export ANTHROPIC_BASE_URL=http://localhost:4000
export ANTHROPIC_AUTH_TOKEN=<your-litellm-master-key>

# Use Claude!
claude
```

Or test with curl:
```bash
curl -X POST http://localhost:4000/v1/messages \
  -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-sonnet-4.5",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## 📦 Available Claude Models

| Model | Best For | Context | Cost (Input/Output) |
|-------|----------|---------|---------------------|
| **claude-sonnet-4.5** | Balanced speed/quality | 200K | $3/$15 per 1M tokens |
| **claude-opus-4.6** | Complex tasks, 1M context | 1M | $5/$25 per 1M tokens |
| **claude-haiku-4.5** | Fast, cost-effective | 200K | $0.25/$1.25 per 1M tokens |

Aliases: `claude-sonnet` → Sonnet 4.5, `claude-opus` → Opus 4.6

## 🏢 Using GitHub Copilot Business

### Option 1: Claude Code CLI (Simplest)

If you just want to use Claude and don't need ClaudeX features:

```bash
# Install
npm install -g @anthropics/claude-code-cli

# Authenticate with GitHub Copilot
claude-code auth github-copilot

# Use it!
claude-code
```

**Pros:** Free with your Copilot subscription, simple setup
**Cons:** Bypasses ClaudeX (no PII masking, no budget controls)

### Option 2: Proxy Through ClaudeX (Advanced)

Keep ClaudeX benefits (PII masking, audit logging, budget controls):

1. **Get GitHub Copilot token:**
   - Open VS Code with Copilot
   - Command Palette (Cmd/Ctrl+Shift+P)
   - Run: "GitHub Copilot: Show API Token"
   - Copy the token

2. **Configure ClaudeX:**
   ```bash
   # In .env:
   ANTHROPIC_API_KEY=<your-github-copilot-token>
   ```

3. **Restart and use:**
   ```bash
   make restart
   ```

⚠️ **Note:** Copilot tokens expire! For production, use Anthropic API key.

## 🔍 Troubleshooting

### "Invalid API Key"
- Check `.env` file exists and has `ANTHROPIC_API_KEY`
- Make sure key starts with `sk-ant-`
- Restart: `make restart`

### "Model not found: claude-sonnet"
- Configuration not loaded
- Run: `make restart`
- Check: `curl http://localhost:4000/health/readiness`

### "Authentication failed"
- You're using wrong token
- `ANTHROPIC_AUTH_TOKEN` should be your `LITELLM_MASTER_KEY` (from `.env`)
- NOT your Anthropic API key!

## 🎨 Example Use Cases

### Code Review
```bash
curl -X POST http://localhost:4000/v1/messages \
  -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-sonnet-4.5",
    "max_tokens": 2000,
    "messages": [{
      "role": "user",
      "content": "Review this code for security issues: [paste code]"
    }]
  }'
```

### Large Codebase Analysis (Opus 1M context)
```bash
curl -X POST http://localhost:4000/v1/messages \
  -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-opus-4.6",
    "max_tokens": 4000,
    "messages": [{
      "role": "user",
      "content": "Analyze this entire codebase: [paste massive file]"
    }]
  }'
```

### Fast Responses (Haiku)
```bash
curl -X POST http://localhost:4000/v1/messages \
  -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-haiku-4.5",
    "max_tokens": 500,
    "messages": [{
      "role": "user",
      "content": "Quick: best practice for error handling in Python?"
    }]
  }'
```

## 🎯 Why Use ClaudeX?

Even if you could use Claude directly, ClaudeX gives you:

### 1. PII Protection
Automatically masks:
- Credit card numbers
- Email addresses
- Phone numbers
- API keys & tokens
- GitHub PATs

### 2. Budget Control
```bash
# Create team key with $100/month limit
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "team_id": "team-backend",
    "max_budget": 100.0,
    "budget_duration": "30d",
    "models": ["claude-sonnet-4.5", "gpt-4.1-mini"]
  }'
```

### 3. Multi-Provider Access
One gateway for:
- ✅ Claude (Anthropic)
- ✅ GPT-4.1, O3, O4 (OpenAI via GitHub)
- ✅ Llama 4 (Meta via GitHub)
- ✅ DeepSeek R1
- ✅ Mistral, Codestral
- ✅ Grok 3

### 4. Audit Logging
Every request logged to PostgreSQL:
- Who used what model?
- How many tokens?
- How much cost?
- When?

## 📊 Cost Comparison

### Anthropic API Direct
| Model | Input | Output |
|-------|-------|--------|
| Sonnet 4.5 | $3/1M | $15/1M |
| Opus 4.6 | $5/1M | $25/1M |
| Haiku 4.5 | $0.25/1M | $1.25/1M |

### GitHub Copilot Business
- $19/user/month flat rate
- Includes Claude access
- May have usage limits

## 📚 More Resources

- Full docs: [README.md](../README.md)
- German docs: [GERMAN-README.md](./GERMAN-README.md)
- LiteLLM config: [config/litellm-config.yaml](../config/litellm-config.yaml)
- Anthropic docs: https://docs.anthropic.com

## 🆘 Need Help?

1. Check logs: `make logs-litellm`
2. Test health: `curl http://localhost:4000/health/liveliness`
3. Validate config: `make test-quick`
4. Open GitHub issue

---

**Summary:** Claude models are now available! Use Anthropic API key or GitHub Copilot Business. Configuration is in `.env` and models work just like the others through the ClaudeX gateway.
