#!/usr/bin/env bash
# check_freshness.sh — fast check whether /onboarding in this folder is still fresh.
# Prints ONE line, machine-parseable:
#   status=fresh   age_hours=N ttl_hours=M canon_sha=...
#   status=stale   reason=age|sha|missing age_hours=N ttl_hours=M
#   status=absent  (no .onboarding/AGENT.md)
# Exit codes: 0 = fresh, 1 = stale, 2 = absent
set -euo pipefail

AGENT_FILE=".onboarding/AGENT.md"
# CANON_FILE удалён 2026-09-12: локальной копии канона больше нет, sha берётся удалённо
DEFAULT_TTL_HOURS=168   # 7 days

if [[ ! -r "$AGENT_FILE" ]]; then
  echo "status=absent"
  exit 2
fi

last="$(grep -m1 -E '^last_onboarded_at:' "$AGENT_FILE" | sed -E 's/^last_onboarded_at:[[:space:]]*//')"
ttl="$(grep -m1 -E '^staleness_ttl_hours:' "$AGENT_FILE" | awk '{print $2}')"
[[ -z "$ttl" ]] && ttl="$DEFAULT_TTL_HOURS"

# parse "YYYY-MM-DD HH:MM MSK" or similar; fall back to file mtime
last_epoch="$(date -d "${last/MSK/+0300}" +%s 2>/dev/null || stat -c %Y "$AGENT_FILE")"
now_epoch="$(date +%s)"
age_hours=$(( (now_epoch - last_epoch) / 3600 ))

stored_sha="$(grep -m1 -E '^canon_sha256:' "$AGENT_FILE" | awk '{print $2}')"
remote_sha=""

# remote sha — try local file (smain), then Lineman http. Accept ONLY a clean 64-hex string;
# otherwise treat as "unknown" and fall back to age-only check (avoids false-positive stale
# when the http endpoint returns an HTML 404 page).
if [[ -r /home/shectory/docs/FEDERATION_AGENT_ONBOARDING.md ]]; then
  remote_sha="$(sha256sum /home/shectory/docs/FEDERATION_AGENT_ONBOARDING.md | awk '{print $1}')"
else
  raw="$(curl -sS --max-time 3 http://10.66.0.1:9090/api/onboarding/canon.sha256 2>/dev/null | tr -d ' \n' || true)"
  if [[ "$raw" =~ ^[0-9a-f]{64}$ ]]; then
    remote_sha="$raw"
  fi
fi

if (( age_hours >= ttl )); then
  echo "status=stale reason=age age_hours=$age_hours ttl_hours=$ttl"
  exit 1
fi
if [[ -n "$remote_sha" && -n "$stored_sha" && "$remote_sha" != "$stored_sha" ]]; then
  echo "status=stale reason=sha age_hours=$age_hours ttl_hours=$ttl"
  exit 1
fi
echo "status=fresh age_hours=$age_hours ttl_hours=$ttl canon_sha=${stored_sha:0:12}"
exit 0
