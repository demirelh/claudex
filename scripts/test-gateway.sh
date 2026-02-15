#!/usr/bin/env bash
# =============================================================================
# Quick Gateway Validation (runs without pytest)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

GW="${GATEWAY_URL:-http://localhost:4000}"
KEY="${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY must be set}"
PASS=0
FAIL=0

check() {
    local name="$1"
    local expected_code="$2"
    local actual_code="$3"
    if [ "$actual_code" -eq "$expected_code" ]; then
        echo "  PASS: $name (HTTP $actual_code)"
        ((PASS++))
    else
        echo "  FAIL: $name (expected $expected_code, got $actual_code)"
        ((FAIL++))
    fi
}

echo "=== Gateway Validation ==="
echo "URL: $GW"
echo ""

# Health
echo "[Health]"
CODE=$(curl -sf -o /dev/null -w '%{http_code}' "$GW/health/liveliness")
check "Liveliness" 200 "$CODE"

# Auth
echo "[Auth]"
CODE=$(curl -sf -o /dev/null -w '%{http_code}' -X POST "$GW/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{"model":"gpt-4.1-mini","messages":[{"role":"user","content":"hi"}]}')
check "No-auth rejected" 401 "$CODE"

# OpenAI format
echo "[OpenAI Format]"
CODE=$(curl -sf -o /dev/null -w '%{http_code}' -X POST "$GW/v1/chat/completions" \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"gpt-4.1-mini","messages":[{"role":"user","content":"Say: ok"}],"max_tokens":5}')
check "Chat completions" 200 "$CODE"

# Anthropic format
echo "[Anthropic Format]"
CODE=$(curl -sf -o /dev/null -w '%{http_code}' -X POST "$GW/v1/messages" \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -H "anthropic-version: 2023-06-01" \
    -d '{"model":"claude-haiku","max_tokens":10,"messages":[{"role":"user","content":"Say: ok"}]}')
check "Messages API" 200 "$CODE"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
