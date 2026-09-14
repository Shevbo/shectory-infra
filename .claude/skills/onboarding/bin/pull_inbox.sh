#!/usr/bin/env bash
# pull_inbox.sh — pull unread messages from Klod-Access outbox addressed to this agent.
# Reads cursor from .onboarding/outbox_cursor, writes new max id back. Prints up to 10 messages.
set -euo pipefail

AGENT="${1:?usage: pull_inbox.sh <agent_id>}"
CURSOR_FILE=".onboarding/outbox_cursor"
SINCE="0"
[[ -r "$CURSOR_FILE" ]] && SINCE="$(cat "$CURSOR_FILE" | tr -dc '0-9')"
[[ -z "$SINCE" ]] && SINCE="0"

# Через klod_http.sh: напрямую, а на узлах без WG — ssh-jump на Pi.
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
resp="$("$SELF_DIR/klod_http.sh" GET "/api/agent/klod-access/outbox?to=$AGENT&since=$SINCE&limit=10" 2>/dev/null || true)"
[[ -z "$resp" ]] && { echo "inbox=unreachable"; exit 0; }

python3 - "$resp" "$CURSOR_FILE" "$AGENT" <<'PY'
import json, sys, pathlib
raw, cursor_path, agent = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    data = json.loads(raw)
except Exception:
    print(f"inbox=bad-response bytes={len(raw)}")
    sys.exit(0)
msgs = data.get("messages") or []
if not msgs:
    print(f"inbox=empty agent={agent}")
    sys.exit(0)
print(f"inbox=new count={len(msgs)} agent={agent}")
for m in msgs:
    mid = m.get("id"); ts = m.get("ts","?")
    irt = m.get("in_reply_to")
    txt = (m.get("message") or "").strip().replace("\n", " ")
    if len(txt) > 200: txt = txt[:200] + "..."
    print(f"  #{mid} ts={ts} in_reply_to={irt} | {txt}")
max_id = max((m.get("id") or 0) for m in msgs)
pathlib.Path(cursor_path).write_text(str(max_id))
PY
