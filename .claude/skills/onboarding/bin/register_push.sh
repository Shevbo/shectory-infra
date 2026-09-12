#!/usr/bin/env bash
# register_push.sh — register (or clear) an agent's push endpoint with Klod-Access.
# Reads .onboarding/AGENT.md for field `push_endpoint:` (one absolute http(s) URL).
# Idempotent. Prints one line.
#   push_url=registered <url>
#   push_url=cleared
#   push_url=skipped (no field in AGENT.md)
#   push_url=unreachable (klod API failed)
set -euo pipefail

AGENT="${1:?usage: register_push.sh <agent_id> [<url>]}"
URL="${2:-}"

if [[ -z "$URL" && -r .onboarding/AGENT.md ]]; then
  URL="$(grep -m1 -E '^push_endpoint:' .onboarding/AGENT.md | sed -E 's/^push_endpoint:[[:space:]]*//' | tr -d ' "'\''')"
fi

if [[ -z "$URL" ]]; then
  echo "push_url=skipped (no push_endpoint in .onboarding/AGENT.md)"
  exit 0
fi

API="${KLOD_PUSH_URL_API:-http://10.66.0.1:9090/api/agent/klod-access/push_url}"
clear_flag="${ONBOARDING_CLEAR_PUSH:-0}"
if [[ "$clear_flag" == "1" ]]; then
  URL=""
fi

resp="$(curl -sS --max-time 5 -X POST "$API?agent=$AGENT&url=$URL" 2>/dev/null || true)"
if [[ -z "$resp" ]]; then
  echo "push_url=unreachable api=$API"
  exit 0
fi
if echo "$resp" | grep -q '"status": "ok"'; then
  if [[ -z "$URL" ]]; then
    echo "push_url=cleared"
  else
    echo "push_url=registered $URL"
  fi
else
  echo "push_url=error resp=$resp"
fi
