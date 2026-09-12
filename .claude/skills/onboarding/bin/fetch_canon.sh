#!/usr/bin/env bash
# fetch_canon.sh — pull the federation onboarding canon to ./.onboarding/CANONICAL.md
# Fallback chain: local file (smain) → Lineman HTTP (WG nodes) → ssh-jump via Pi (Windows/IoT)
set -euo pipefail

DEST="${1:-./.onboarding/CANONICAL.md}"
mkdir -p "$(dirname "$DEST")"

# (a) smain — direct
if [[ -r /home/shectory/docs/FEDERATION_AGENT_ONBOARDING.md ]]; then
  cp /home/shectory/docs/FEDERATION_AGENT_ONBOARDING.md "$DEST"
  echo "fetched-from=local-file bytes=$(wc -c <"$DEST")"
  exit 0
fi

# (b) Lineman HTTP via WG
if curl -sS --max-time 5 -o "$DEST.tmp" -w "%{http_code}" \
      http://10.66.0.1:9090/api/onboarding/canon 2>/dev/null | grep -q '^200$'; then
  mv "$DEST.tmp" "$DEST"
  echo "fetched-from=lineman-http bytes=$(wc -c <"$DEST")"
  exit 0
fi
rm -f "$DEST.tmp"

# (c) ssh-jump through Pi
if command -v ssh >/dev/null 2>&1; then
  if ssh -o ConnectTimeout=5 -o BatchMode=yes -J shevbo-pi shectory@smain \
         'cat /home/shectory/docs/FEDERATION_AGENT_ONBOARDING.md' >"$DEST" 2>/dev/null && \
         [[ -s "$DEST" ]]; then
    echo "fetched-from=ssh-jump bytes=$(wc -c <"$DEST")"
    exit 0
  fi
fi

echo "fetched-from=NONE error=all-routes-failed" >&2
exit 1
