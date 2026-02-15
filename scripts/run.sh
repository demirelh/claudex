#!/usr/bin/env bash
# =============================================================================
# ClaudeX — Pull & Restart
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== ClaudeX Pull & Restart ==="

# --- 1. Git Pull ---
echo "Pulling latest changes..."
git pull --ff-only

# --- 2. Restart Services ---
echo "Restarting services..."
docker compose down
docker compose up -d

# --- 3. Wait for Health ---
echo "Waiting for gateway..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:4000/health/liveliness >/dev/null 2>&1; then
        echo "Gateway healthy after $((i*3))s"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Gateway not healthy after 90s"
        docker compose logs litellm --tail=20
        exit 1
    fi
    sleep 3
done

echo ""
docker compose ps
echo ""
echo "=== ClaudeX running ==="
