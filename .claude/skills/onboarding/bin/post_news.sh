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

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fallback="$HOME/.onboarding-news-outbox.jsonl"

# send_news <text>: 0 если Lineman принял (2xx), 1 иначе. Маршрут выбирает klod_http.sh:
# напрямую, а на узлах без WG — через ssh-jump на Pi.
send_news() {
  local status route
  status="$(printf '%s' "$1" | "$SELF_DIR/klod_http.sh" POST \
            "/api/agent/klod-access/message?from=$AGENT&node=$NODE&topic=news" - text/plain \
            2>&1 >/dev/null | tail -1)"
  route="${status##*route=}"
  status="${status#http=}"; status="${status%% *}"
  LAST_HTTP="$status"; LAST_ROUTE="$route"
  [[ "$status" =~ ^2 ]]
}

if send_news "$msg"; then
  echo "news=registered http=$LAST_HTTP route=$LAST_ROUTE event=$EVENT"
  # Досылаем то, что копилось, пока Lineman был недостижим. Нужен python3 для разбора
  # JSONL; без него очередь просто остаётся на следующий раз.
  if [[ -s "$fallback" ]] && command -v python3 >/dev/null 2>&1; then
    python3 - "$fallback" "$SELF_DIR/klod_http.sh" <<'PYQ'
import json, subprocess, sys
path, helper = sys.argv[1], sys.argv[2]
kept, sent = [], 0
for line in open(path, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    try:
        r = json.loads(line)
    except Exception:
        kept.append(line); continue
    if r.get("delivered"):
        continue
    text = 'news event=%s ts="%s" agent=%s node=%s details="%s" queued=true' % (
        r.get("event"), r.get("ts"), r.get("agent"), r.get("node"), r.get("details", ""))
    q = "/api/agent/klod-access/message?from=%s&node=%s&topic=news" % (r.get("agent"), r.get("node"))
    p = subprocess.run([helper, "POST", q, "-", "text/plain"], input=text.encode(),
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    last = (p.stderr.decode(errors="replace").strip().splitlines() or [""])[-1]
    if last.startswith("http=2"):
        sent += 1
    else:
        kept.append(line)
open(path, "w", encoding="utf-8").write("".join(k + "\n" for k in kept))
print("news-outbox=flushed sent=%d left=%d" % (sent, len(kept)))
PYQ
  fi
  exit 0
fi

# Ни один маршрут не принял: копим локально. Очередь досылается при следующем
# успешном вызове post_news.sh (см. блок выше).
printf '{"ts":"%s","agent":"%s","node":"%s","event":"%s","details":"%s","delivered":false}\n' \
       "$TS" "$AGENT" "$NODE" "$EVENT" "${DETAILS//\"/\\\"}" >>"$fallback"
echo "news=queued-locally http=$LAST_HTTP route=$LAST_ROUTE path=$fallback"
exit 0
