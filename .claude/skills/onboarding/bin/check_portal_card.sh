#!/usr/bin/env bash
# check_portal_card.sh — ensure a portal card exists for <agent_id>@<node>.
# Behaviour:
#   - GET https://dashboard.shectory.ru/api/portal/agents/<id> (via local DNS if reachable)
#   - 200 → echo "portal-card=ok"
#   - 404 → POST to create with minimal body
#   - any failure → fall back to posting a klod-news event "portal-card-missing"
set -euo pipefail

AGENT="${1:?usage: check_portal_card.sh <agent_id> <node> [<purpose>]}"
NODE="${2:?node required}"
PURPOSE="${3:-}"

API_BASE="${PORTAL_API_BASE:-https://dashboard.shectory.ru/api}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# GET probe
code="$(curl -sS -o /tmp/portal_card_$$.json -w '%{http_code}' --max-time 6 \
        "$API_BASE/portal/agents/$AGENT" 2>/dev/null || echo 000)"

case "$code" in
  200)
    echo "portal-card=ok agent=$AGENT"
    rm -f "/tmp/portal_card_$$.json"; exit 0
    ;;
  404)
    rm -f "/tmp/portal_card_$$.json"
    body="$(printf '{"agent_id":"%s","node":"%s","purpose":"%s","source":"onboarding-skill"}' \
            "$AGENT" "$NODE" "${PURPOSE//\"/\\\"}")"
    create_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 6 \
                   -X POST -H 'Content-Type: application/json' \
                   --data "$body" "$API_BASE/portal/agents" 2>/dev/null || echo 000)"
    if [[ "$create_code" =~ ^2 ]]; then
      echo "portal-card=created agent=$AGENT http=$create_code"; exit 0
    fi
    # fallthrough to fallback
    ;;
  000|5*)
    rm -f "/tmp/portal_card_$$.json"
    ;;
  *)
    rm -f "/tmp/portal_card_$$.json"
    ;;
esac

# Fallback: tell Klod the card is missing — он создаст руками или поднимет ручку
msg="portal-card-missing: agent=$AGENT node=$NODE purpose=${PURPOSE:-unknown} probe_http=$code"
# Через klod_http.sh: иначе с узла без WG сообщение о пропавшей карточке тоже терялось.
printf '%s' "$msg" | "$SELF_DIR/klod_http.sh" POST \
     "/api/agent/klod-access/message?from=$AGENT&node=$NODE&topic=portal-card" - text/plain \
     >/dev/null 2>&1 || true
echo "portal-card=reported-missing agent=$AGENT probe_http=$code"
