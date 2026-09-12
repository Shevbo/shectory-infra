#!/usr/bin/env bash
# detect_agent.sh — derive agent_id and node for the current project folder
# Outputs two lines: "agent_id=<id>" and "node=<host>".
# If agent_id cannot be inferred, exits with code 2 and prints "agent_id=UNKNOWN".
set -euo pipefail

NODE="$(hostname -s 2>/dev/null || hostname || echo unknown)"

agent_id=""

# 1. Existing AGENT.md snapshot
if [[ -r .onboarding/AGENT.md ]]; then
  agent_id="$(grep -m1 -E '^agent_id:' .onboarding/AGENT.md | awk -F: '{print $2}' | tr -d ' "' || true)"
fi

# 2. AGENTS.md / CLAUDE.md hint
if [[ -z "$agent_id" ]]; then
  for f in AGENTS.md CLAUDE.md; do
    [[ -r "$f" ]] || continue
    agent_id="$(grep -m1 -iE '^(agent_id|agent)[[:space:]]*[:=][[:space:]]*' "$f" \
                | sed -E 's/.*[:=][[:space:]]*//; s/[[:space:]"`'\'']+//g' || true)"
    [[ -n "$agent_id" ]] && break
  done
fi

# 3. Fall back to folder name (sanitized)
if [[ -z "$agent_id" ]]; then
  agent_id="$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed -E 's/^-+|-+$//g; s/-+/-/g')"
fi

if [[ -z "$agent_id" || "$agent_id" == "-" ]]; then
  echo "agent_id=UNKNOWN"
  echo "node=$NODE"
  exit 2
fi

echo "agent_id=$agent_id"
echo "node=$NODE"
