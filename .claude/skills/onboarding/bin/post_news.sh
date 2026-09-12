#!/usr/bin/env bash
# post_news.sh — register a news event in the federation onboarding log.
# Goes to Klod-Access inbox with topic=news so the daily refresh job folds it in.
#
# Usage: post_news.sh <agent_id> <node> <event> "<key=val; key=val; ...>"
#   <event>: onboarded | doc-added | purpose-changed | repo-moved | canon-gap | retired | other
set -euo pipefail

AGENT="${1:?usage: post_news.sh <agent_id> <node> <event> <details>}"
NODE="${2:?node required}"
EVENT="${3:?event required}"
DETAILS="${4:-}"

KLOD_INBOX="${KLOD_INBOX:-http://10.66.0.1:9090/api/agent/klod-access/message}"
TS="$(date '+%Y-%m-%d %H:%M:%S %z')"

# JSONL-ish single-line payload, but sent as plain text (Lineman accepts both).
msg="news event=$EVENT ts=\"$TS\" agent=$AGENT node=$NODE details=\"$DETAILS\""

http_code="$(curl -sS --max-time 6 -o /dev/null -w '%{http_code}' \
             -X POST "$KLOD_INBOX?from=$AGENT&node=$NODE&topic=news" \
             -H 'Content-Type: text/plain' --data "$msg" 2>/dev/null || echo 000)"

if [[ "$http_code" =~ ^2 ]]; then
  echo "news=registered http=$http_code event=$EVENT"
  exit 0
fi

# Fallback: append to local JSONL so the next refresh on smain can still pick it up
# (works when this skill runs on smain itself; on other nodes the next /onboarding
# attempt or a manual sync will deliver the news).
fallback="$HOME/.onboarding-news-outbox.jsonl"
printf '{"ts":"%s","agent":"%s","node":"%s","event":"%s","details":"%s","delivered":false}\n' \
       "$TS" "$AGENT" "$NODE" "$EVENT" "${DETAILS//\"/\\\"}" >>"$fallback"
echo "news=queued-locally http=$http_code path=$fallback"
exit 0
