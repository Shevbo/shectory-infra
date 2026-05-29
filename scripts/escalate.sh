#!/bin/bash
# escalate.sh — Multi-channel escalation for agents.
#
# Usage: escalate.sh <agent_id> "<question>" [context_file]
#
# Channels (try in order):
#   1. ask-claude.sh (PATH or ~/scripts/) — synchronous, 30s timeout
#   2. ~/workspaces/claude-inbox/TASK_<ts>_<AGENT>.md — async
#   3. Lineman /api/tg/send — alert Boris (one-time)
#
# Dedup: same sha256(agent_id|question) within 60 minutes → skip with exit 0.

set -u
AGENT_ID="${1:-}"
QUESTION="${2:-}"
CONTEXT_FILE="${3:-}"

if [[ -z "$AGENT_ID" || -z "$QUESTION" ]]; then
    echo "usage: escalate.sh <agent_id> \"<question>\" [context_file]" >&2
    exit 2
fi

DEDUP_FILE="${HOME}/.cache/escalate-recent.json"
mkdir -p "${HOME}/.cache"
[[ -f "$DEDUP_FILE" ]] || echo '{}' > "$DEDUP_FILE"

QHASH=$(printf '%s|%s' "$AGENT_ID" "$QUESTION" | sha256sum | cut -c1-16)
NOW=$(date +%s)

# Check dedup
LAST=$(DEDUP_FILE="$DEDUP_FILE" QHASH="$QHASH" python3 -c "
import json, os
try:
    d = json.load(open(os.environ['DEDUP_FILE']))
    print(d.get(os.environ['QHASH'], 0))
except Exception:
    print(0)
")
if [[ "$LAST" -gt 0 ]] && [[ $((NOW - LAST)) -lt 3600 ]]; then
    echo "[escalate] deduped: same question hashed=$QHASH escalated $((NOW - LAST))s ago, skipping"
    exit 0
fi

# Record this attempt
DEDUP_FILE="$DEDUP_FILE" QHASH="$QHASH" NOW="$NOW" python3 -c "
import json, os
path = os.environ['DEDUP_FILE']
qhash = os.environ['QHASH']
now = int(os.environ['NOW'])
try:
    d = json.load(open(path))
except Exception:
    d = {}
d[qhash] = now
# Trim old entries (>1d)
d = {k: v for k, v in d.items() if now - v < 86400}
json.dump(d, open(path, 'w'))
"

# Channel 1: ask-claude.sh with 30s timeout (prefer PATH, fall back to ~/scripts)
ASK_CLAUDE=$(command -v ask-claude.sh || true)
[[ -z "$ASK_CLAUDE" ]] && ASK_CLAUDE="${HOME}/scripts/ask-claude.sh"
if [[ -x "$ASK_CLAUDE" ]]; then
    if [[ -n "$CONTEXT_FILE" && -f "$CONTEXT_FILE" ]]; then
        OUTPUT=$(timeout 30 "$ASK_CLAUDE" "[$AGENT_ID] $QUESTION" "$CONTEXT_FILE" 2>&1)
    else
        OUTPUT=$(timeout 30 "$ASK_CLAUDE" "[$AGENT_ID] $QUESTION" 2>&1)
    fi
    RC=$?
    if [[ $RC -eq 0 ]] && [[ -n "$OUTPUT" ]]; then
        echo "$OUTPUT"
        exit 0
    fi
fi

# Channel 2: claude-inbox file drop
INBOX_DIR="${HOME}/workspaces/claude-inbox"
if mkdir -p "$INBOX_DIR" 2>/dev/null; then
    INBOX_FILE="$INBOX_DIR/TASK_${NOW}_${AGENT_ID}.md"
    {
        echo "# Escalation from $AGENT_ID — $(date -Iseconds)"
        echo ""
        echo "## Question"
        echo "$QUESTION"
        if [[ -n "$CONTEXT_FILE" && -f "$CONTEXT_FILE" ]]; then
            echo ""
            echo "## Context (from $CONTEXT_FILE)"
            cat "$CONTEXT_FILE"
        fi
    } > "$INBOX_FILE"
    if [[ -f "$INBOX_FILE" ]]; then
        echo "[escalate] queued to inbox: $INBOX_FILE"
        exit 0
    fi
fi

# Channel 3: TG alert to Boris (best effort)
BORIS_CHAT_ID="${BORIS_CHAT_ID:-36910539}"
AGENT_ID="$AGENT_ID" QUESTION="$QUESTION" BORIS_CHAT_ID="$BORIS_CHAT_ID" \
    curl -s --noproxy "*" --max-time 10 -X POST "http://127.0.0.1:9090/api/tg/send" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "
import json, os
print(json.dumps({
  'account': 'default',
  'chat_id': int(os.environ['BORIS_CHAT_ID']),
  'text': '⚠️ Escalation from ' + os.environ['AGENT_ID'] + ' failed all channels: ' + os.environ['QUESTION'][:500],
}))
")" > /dev/null
echo "[escalate] all channels failed; tg alert sent (best-effort)" >&2
exit 1
