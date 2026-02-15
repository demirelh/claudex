# Using ClaudeX with GitHub Copilot Business (No Anthropic API Key Needed)

This guide is for users who have **GitHub Copilot Business** subscription and want to use Claude models (Sonnet, Opus) **without** getting a separate Anthropic API key.

## 📋 Prerequisites

- ✅ GitHub Copilot Business subscription (or Enterprise/Pro+)
- ✅ VS Code with GitHub Copilot extension installed
- ✅ Docker + Docker Compose installed on your machine
- ✅ Claude CLI installed: `pip install claude-cli`

## 🎯 Two Approaches

You have two options to use Claude models with your GitHub Copilot subscription:

| Approach | Difficulty | ClaudeX Benefits | Best For |
|----------|------------|------------------|----------|
| **Option 1: Claude Code CLI** | Easy | ❌ No (bypasses gateway) | Individual developers who want simple setup |
| **Option 2: ClaudeX Proxy** | Moderate | ✅ Yes (PII masking, audit logs, budgets) | Teams needing centralized control |

---

## 🚀 Option 1: Claude Code CLI with GitHub Copilot (Simplest)

This is the **easiest** method but bypasses ClaudeX gateway features.

### Step 1: Install Claude Code CLI

```bash
npm install -g @anthropics/claude-code-cli
```

**Verify installation:**
```bash
claude-code --version
```

### Step 2: Authenticate with GitHub Copilot

```bash
claude-code auth github-copilot
```

This will:
1. Open your browser
2. Ask you to authorize with GitHub
3. Automatically configure Claude Code to use your Copilot subscription

### Step 3: Verify It Works

```bash
# Test with a simple prompt
claude-code "Write a hello world in Python"
```

### Step 4: Use It Like Regular Claude

```bash
# Interactive mode
claude-code

# Single prompt mode
claude-code "Explain async/await in JavaScript"

# With specific model
claude-code --model claude-opus-4.6 "Complex architecture question"
```

### Available Models via Claude Code CLI

- `claude-sonnet-4.5` (default) - Balanced speed/quality
- `claude-opus-4.6` - Best quality, complex reasoning
- `claude-haiku-4.5` - Fastest, cost-effective

### ✅ Pros
- ✅ No API key management
- ✅ Free with your Copilot subscription
- ✅ Automatic token refresh
- ✅ Simple setup (3 steps)

### ❌ Cons
- ❌ Bypasses ClaudeX gateway
- ❌ No PII masking
- ❌ No team budget controls
- ❌ No centralized audit logs
- ❌ No rate limiting

**Use this if:** You're an individual developer who wants the simplest setup and doesn't need enterprise features.

---

## 🏢 Option 2: ClaudeX Proxy with GitHub Copilot (Advanced)

This method routes requests through ClaudeX gateway, keeping all enterprise features (PII masking, budgets, audit logs).

### Step 1: Get Your GitHub Copilot Token

#### Method A: Via VS Code (Easiest)

1. **Open VS Code** with GitHub Copilot extension installed
2. **Open Command Palette:**
   - Mac: `Cmd + Shift + P`
   - Windows/Linux: `Ctrl + Shift + P`
3. **Type and select:** `GitHub Copilot: Show API Token`
4. **Copy the token** that appears (it's a long string)

**⚠️ Important:** This token expires after a few hours/days and needs to be refreshed periodically.

#### Method B: Via Browser DevTools (Alternative)

1. Open https://github.com/copilot
2. Open browser DevTools (F12)
3. Go to Network tab
4. Make a Copilot request in VS Code
5. Look for requests to `api.githubcopilot.com`
6. Find the `Authorization` header value

### Step 2: Setup ClaudeX

```bash
# Clone repo (if not done)
git clone https://github.com/demirelh/claudex.git
cd claudex

# Copy environment template
cp .env.example .env
```

### Step 3: Configure Environment Variables

Edit `.env` file:

```bash
# Required: Your GitHub Copilot token (from Step 1)
ANTHROPIC_API_KEY=<paste-your-github-copilot-token-here>

# Required: Master key for ClaudeX admin
# Generate with: openssl rand -hex 32
LITELLM_MASTER_KEY=sk-litellm-your-secure-key-here

# Required: Database password
POSTGRES_PASSWORD=secure-database-password

# Required: Full database URL (update password to match above)
DATABASE_URL=postgresql://litellm:secure-database-password@postgres:5432/litellm

# Optional: GitHub Models PAT (for other models like GPT-4, Llama)
GITHUB_MODELS_PAT=github_pat_your-pat-if-needed
```

**Example `.env` file:**
```bash
ANTHROPIC_API_KEY=ghu_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0
LITELLM_MASTER_KEY=sk-litellm-7a3f9d2e1b8c4d6a9f2e7b1c3d8a5f4e
POSTGRES_PASSWORD=MySecure123Password
DATABASE_URL=postgresql://litellm:MySecure123Password@postgres:5432/litellm
REDIS_HOST=redis
REDIS_PORT=6379
PRESIDIO_ANALYZER_URL=http://presidio-analyzer:5001
PRESIDIO_ANONYMIZER_URL=http://presidio-anonymizer:5002
```

### Step 4: Start ClaudeX Services

```bash
# First time setup
make setup

# This will:
# - Validate your .env file
# - Pull Docker images
# - Start LiteLLM, PostgreSQL, Redis, Presidio
# - Run health checks
```

**Wait for all services to be healthy (30-60 seconds).**

### Step 5: Verify ClaudeX is Running

```bash
# Check service status
make status

# Test health endpoint
curl http://localhost:4000/health/liveliness

# Should return: {"status": "healthy"}
```

### Step 6: Configure Claude CLI to Use ClaudeX

Add to your shell profile (`~/.bashrc`, `~/.zshrc`, or `~/.bash_profile`):

```bash
# Point Claude CLI to ClaudeX gateway
export ANTHROPIC_BASE_URL=http://localhost:4000

# Use your LiteLLM master key for authentication
export ANTHROPIC_AUTH_TOKEN=sk-litellm-your-secure-key-here
```

**Apply changes:**
```bash
source ~/.bashrc  # or ~/.zshrc
```

### Step 7: Test with Claude CLI

```bash
# Interactive mode
claude

# Should connect through ClaudeX gateway
# Try a test prompt:
# > "Hello! Tell me a joke about Docker containers."
```

### Step 8: Test with curl (Alternative)

```bash
curl -X POST http://localhost:4000/v1/messages \
  -H "Authorization: Bearer sk-litellm-your-secure-key-here" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-sonnet-4.5",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "Hello from ClaudeX!"}
    ]
  }'
```

**Expected response:**
```json
{
  "id": "msg_...",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Hello! I'm Claude, running through your ClaudeX gateway..."
    }
  ],
  "model": "claude-sonnet-4.5",
  ...
}
```

### Step 9: Create Team API Keys (Optional)

For teams, create restricted API keys with budgets:

```bash
# Create a team key with $50/month budget
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "team-backend",
    "max_budget": 50.0,
    "budget_duration": "30d",
    "models": ["claude-sonnet-4.5", "claude-haiku-4.5"]
  }'
```

**Response includes:**
```json
{
  "key": "sk-proj-abc123...",
  "team_id": "team-backend",
  "max_budget": 50.0,
  ...
}
```

Give this `sk-proj-abc123...` key to team members instead of the master key.

### ✅ Pros
- ✅ All ClaudeX features (PII masking, audit logs, budgets)
- ✅ Centralized control for teams
- ✅ Uses your Copilot subscription (no extra Anthropic costs)
- ✅ Multi-model access (Claude + GPT + Llama + more)

### ❌ Cons
- ❌ More complex setup
- ❌ GitHub Copilot tokens expire (need periodic refresh)
- ❌ Requires Docker and managing services
- ❌ Additional infrastructure overhead

**Use this if:** You're a team that needs enterprise features like PII protection, budget controls, and audit logging.

---

## 🔄 Token Refresh (Option 2 Users)

GitHub Copilot tokens expire after hours/days. When you see authentication errors:

### Symptoms of Expired Token
```
Error: Authentication failed
Error: Invalid API key
Error: 401 Unauthorized
```

### How to Refresh

1. **Get new token from VS Code:**
   - Open Command Palette (`Cmd/Ctrl + Shift + P`)
   - Run: `GitHub Copilot: Show API Token`
   - Copy the new token

2. **Update `.env` file:**
   ```bash
   # Replace old token with new one
   ANTHROPIC_API_KEY=<new-token-from-vscode>
   ```

3. **Restart ClaudeX:**
   ```bash
   make restart
   ```

4. **Verify:**
   ```bash
   curl http://localhost:4000/health/liveliness
   ```

### Automation (Advanced)

For production, consider:
- Using a direct Anthropic API key instead (no expiration)
- Or automating token refresh with a script that fetches from GitHub API
- Or using GitHub Apps with longer-lived tokens

---

## 📊 Comparison: Anthropic API Key vs GitHub Copilot

| Feature | Anthropic API Key | GitHub Copilot Token |
|---------|-------------------|----------------------|
| **Cost** | Pay per token ($3-25/1M) | Included in Copilot ($19/user/mo) |
| **Token Expiration** | Never expires | Expires after hours/days |
| **Setup Complexity** | Simple (one key) | Moderate (token refresh needed) |
| **Production Ready** | ✅ Yes | ⚠️ Needs refresh automation |
| **Best For** | Production systems | Development/testing |

---

## 🔍 Troubleshooting

### Error: "Invalid API Key"

**Cause:** GitHub Copilot token expired or invalid

**Solution:**
1. Get fresh token from VS Code
2. Update `.env` file
3. Run `make restart`

### Error: "Model not found: claude-sonnet-4.5"

**Cause:** LiteLLM config not loaded properly

**Solution:**
```bash
# Restart services
make restart

# Check config is valid
python3 -c "import yaml; yaml.safe_load(open('config/litellm-config.yaml'))"

# Check health
curl http://localhost:4000/health/readiness
```

### Error: "Cannot connect to Docker daemon"

**Cause:** Docker not running

**Solution:**
```bash
# Mac: Start Docker Desktop app
# Linux: sudo systemctl start docker
# Windows: Start Docker Desktop
```

### Services won't start

**Cause:** Port conflicts or missing dependencies

**Solution:**
```bash
# Check if ports are in use
lsof -i :4000  # LiteLLM
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis

# Kill conflicting processes or change ports in docker-compose.yaml
make down
make up
```

### Claude CLI not connecting to gateway

**Cause:** Environment variables not set

**Solution:**
```bash
# Check if variables are set
echo $ANTHROPIC_BASE_URL
echo $ANTHROPIC_AUTH_TOKEN

# If empty, add to shell profile and reload
source ~/.bashrc  # or ~/.zshrc
```

---

## 📈 Monitoring Usage

### View Logs
```bash
# All services
make logs

# LiteLLM only
make logs-litellm

# Follow logs in real-time
make logs-litellm | grep -i claude
```

### Check Spending
```bash
# Get all spending logs
curl http://localhost:4000/spend/logs \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"

# Check specific team's spending
curl http://localhost:4000/spend/logs?team_id=team-backend \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

### View Active Keys
```bash
# List all API keys
curl http://localhost:4000/key/info \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

---

## 🎯 Use Cases

### Individual Developer
- **Use:** Option 1 (Claude Code CLI)
- **Why:** Simple, no infrastructure needed
- **Setup time:** 5 minutes

### Small Team (2-10 developers)
- **Use:** Option 2 (ClaudeX Proxy)
- **Why:** Budget controls, shared monitoring
- **Setup time:** 20 minutes

### Enterprise (10+ developers)
- **Use:** Option 2 (ClaudeX Proxy) + Team Keys
- **Why:** PII masking, audit logs, compliance
- **Setup time:** 1 hour (initial), then 5 min per team

---

## 🆘 Need More Help?

- **Full ClaudeX docs:** [README.md](../README.md)
- **Quick setup guide:** [CLAUDE-SETUP.md](./CLAUDE-SETUP.md)
- **German guide:** [GERMAN-README.md](./GERMAN-README.md)
- **GitHub Issues:** https://github.com/demirelh/claudex/issues

---

## ✅ Summary

### Option 1: Claude Code CLI (Simple)
```bash
npm install -g @anthropics/claude-code-cli
claude-code auth github-copilot
claude-code "Your prompt here"
```
✅ Best for: Individual developers, quick setup

### Option 2: ClaudeX Proxy (Advanced)
```bash
# Get GitHub Copilot token from VS Code
# Configure .env with token
make setup
export ANTHROPIC_BASE_URL=http://localhost:4000
export ANTHROPIC_AUTH_TOKEN=<litellm-master-key>
claude
```
✅ Best for: Teams, enterprise features, centralized control

**Both options use your GitHub Copilot Business subscription - no separate Anthropic API key needed!**
