#!/usr/bin/env bash
# =============================================================================
# ClaudeX — Local Setup Script
# =============================================================================
# Usage: ./scripts/setup.sh
# Prerequisites: docker, docker compose
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== ClaudeX Local Setup ==="

# --- 1. Check prerequisites ---
for cmd in docker; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd is not installed."
        exit 1
    fi
done

if ! docker compose version &>/dev/null; then
    echo "ERROR: docker compose is not available."
    exit 1
fi

# --- 2. Create .env from template ---
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from template."
    echo ""
    echo "  >>> IMPORTANT: Edit .env and set your GITHUB_MODELS_PAT <<<"
    echo "  >>> Create a fine-grained PAT at: https://github.com/settings/tokens?type=beta"
    echo "  >>> Required scope: models:read (Account Permission)"
    echo ""
    read -rp "Press Enter after editing .env, or Ctrl+C to abort..."
else
    echo ".env already exists, skipping."
fi

# --- 3. Validate required env vars ---
source .env
if [[ "${GITHUB_MODELS_PAT:-}" == *"REPLACE_ME"* ]] || [[ -z "${GITHUB_MODELS_PAT:-}" ]]; then
    echo "ERROR: GITHUB_MODELS_PAT is not set in .env"
    exit 1
fi

# --- 4. Start services ---
echo ""
echo "Starting services..."
docker compose up -d

echo ""
echo "Waiting for gateway to become healthy..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:4000/health/liveliness >/dev/null 2>&1; then
        echo "Gateway is healthy!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Gateway did not become healthy within 60s."
        echo "Check logs with: docker compose logs litellm"
        exit 1
    fi
    sleep 2
done

# --- 5. Smoke test ---
echo ""
echo "Running smoke test..."
RESPONSE=$(curl -sf -X POST http://localhost:4000/v1/chat/completions \
    -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "Say exactly: gateway-ok"}],
        "max_tokens": 10
    }' 2>&1) || {
    echo "ERROR: Smoke test failed."
    echo "Response: $RESPONSE"
    echo "Check logs: docker compose logs litellm"
    exit 1
}

echo "Smoke test passed!"
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Gateway URL:  http://localhost:4000"
echo "Health check: curl http://localhost:4000/health"
echo ""
echo "To configure ClaudeX:"
echo "  export ANTHROPIC_BASE_URL=http://localhost:4000"
echo "  export ANTHROPIC_AUTH_TOKEN=${LITELLM_MASTER_KEY}"
echo "  claude"
echo ""
echo "To create team keys:"
echo "  ./scripts/create-team-keys.sh"
echo ""
echo "To run tests:"
echo "  make test"
