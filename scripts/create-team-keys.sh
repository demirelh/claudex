#!/usr/bin/env bash
# =============================================================================
# Create Virtual Keys for Teams
# =============================================================================
# Usage: ./scripts/create-team-keys.sh
# Requires: LITELLM_MASTER_KEY env var or .env file
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env if it exists
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

GATEWAY_URL="${GATEWAY_URL:-http://localhost:4000}"
MASTER_KEY="${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY must be set}"

# --- Team definitions ---
# Adjust these to match your organization's teams
TEAMS=(
    "frontend:50.0:claude-sonnet,claude-haiku,gpt-4.1-mini"
    "backend:100.0:claude-sonnet,claude-haiku,gpt-4.1,gpt-4.1-mini"
    "data:75.0:claude-sonnet,gpt-4.1,deepseek-r1"
    "devops:30.0:claude-haiku,gpt-4.1-mini"
)

echo "=== Creating Team Virtual Keys ==="
echo "Gateway: $GATEWAY_URL"
echo ""

for team_entry in "${TEAMS[@]}"; do
    IFS=':' read -r team_name budget models <<< "$team_entry"

    # Convert comma-separated models to JSON array
    models_json=$(echo "$models" | tr ',' '\n' | sed 's/.*/"&"/' | tr '\n' ',' | sed 's/,$//')

    echo "--- Team: $team_name (Budget: \$$budget/30d, Models: $models) ---"

    RESPONSE=$(curl -sf -X POST "$GATEWAY_URL/key/generate" \
        -H "Authorization: Bearer $MASTER_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"team_id\": \"team-$team_name\",
            \"max_budget\": $budget,
            \"budget_duration\": \"30d\",
            \"models\": [$models_json],
            \"metadata\": {\"team\": \"$team_name\", \"created_by\": \"setup-script\"}
        }" 2>&1) || {
        echo "  ERROR: Failed to create key for $team_name"
        echo "  Response: $RESPONSE"
        continue
    }

    KEY=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])" 2>/dev/null || echo "PARSE_ERROR")

    echo "  Key: $KEY"
    echo ""
done

echo "=== Done ==="
echo ""
echo "Developers should set in their shell profile:"
echo "  export ANTHROPIC_BASE_URL=$GATEWAY_URL"
echo "  export ANTHROPIC_AUTH_TOKEN=<team-key-from-above>"
