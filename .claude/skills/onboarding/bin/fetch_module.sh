#!/usr/bin/env bash
# fetch_module.sh <module> [dest] — pull one JIT onboarding module.
# Модули перечислены в поле `modules:` карточки .onboarding/AGENT.md (канон §0).
# Fallback: local file (smain) → Lineman HTTP (WG) → ssh-jump via Pi (Windows/IoT).
# portal-auth живёт в lineman/docs, остальные — в docs/onboarding-modules/.
set -euo pipefail

MOD="${1:?usage: fetch_module.sh <module> [dest]}"
DEST="${2:-./.onboarding/modules/${MOD}.md}"
mkdir -p "$(dirname "$DEST")"

case "$MOD" in
  portal-auth) REL="workspaces/infra/lineman/docs/PORTAL_AUTH_STANDARD.md" ;;
  *)           REL="docs/onboarding-modules/${MOD}.md" ;;
esac

# (a) smain — direct
if [[ -r "/home/shectory/${REL}" ]]; then
  cp "/home/shectory/${REL}" "$DEST"
  echo "module=${MOD} from=local-file bytes=$(wc -c <"$DEST")"; exit 0
fi

# (b) Lineman HTTP via WG
if curl -sS --max-time 5 -o "$DEST.tmp" -w "%{http_code}" \
      "http://10.66.0.1:9090/api/onboarding/module?name=${MOD}" 2>/dev/null | grep -q '^200$'; then
  mv "$DEST.tmp" "$DEST"
  echo "module=${MOD} from=lineman-http bytes=$(wc -c <"$DEST")"; exit 0
fi
rm -f "$DEST.tmp"

# (c) ssh-jump through Pi
if command -v ssh >/dev/null 2>&1; then
  if ssh -o ConnectTimeout=5 -o BatchMode=yes -J shevbo-pi shectory@smain \
         "cat /home/shectory/${REL}" >"$DEST" 2>/dev/null && [[ -s "$DEST" ]]; then
    echo "module=${MOD} from=ssh-jump bytes=$(wc -c <"$DEST")"; exit 0
  fi
fi

echo "module=${MOD} from=NONE error=all-routes-failed" >&2
exit 1
