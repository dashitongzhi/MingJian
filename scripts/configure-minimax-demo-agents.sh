#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${PLANAGENT_API_BASE_URL:-http://localhost:8000}"
MINIMAX_API_KEY="${PLANAGENT_DEMO_MINIMAX_API_KEY:-${MINIMAX_API_KEY:-${ANTHROPIC_API_KEY:-}}}"
MINIMAX_BASE_URL="${PLANAGENT_DEMO_MINIMAX_BASE_URL:-https://api.minimaxi.com/anthropic}"
MINIMAX_MODEL="${PLANAGENT_DEMO_MINIMAX_MODEL:-MiniMax-M2.7}"

if [[ -z "$MINIMAX_API_KEY" ]]; then
  printf 'missing MiniMax API key; set PLANAGENT_DEMO_MINIMAX_API_KEY or MINIMAX_API_KEY\n' >&2
  exit 1
fi

api_key_json="$(printf '%s' "$MINIMAX_API_KEY" | jq -Rs .)"
base_url_json="$(printf '%s' "$MINIMAX_BASE_URL" | jq -Rs .)"
model_json="$(printf '%s' "$MINIMAX_MODEL" | jq -Rs .)"
payload="{\"keys\":[{\"provider_type\":\"anthropic\",\"api_key\":$api_key_json,\"base_url\":$base_url_json,\"model\":$model_json}]}"

printf '%s' "$payload" | curl -fsS \
  -H 'Content-Type: application/json' \
  --data-binary @- \
  "$API_BASE_URL/agents/configure" \
  | jq '{total, ready, agents: [.agents[] | {role, name, has_key, effective_model}]}'
