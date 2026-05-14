#!/usr/bin/env bash
# go2lineman.sh — переключить OpenClaw агентов И Claude Code: через Lineman proxy или напрямую
# Usage: go2lineman.sh on|off|status

set -euo pipefail

MODE="${1:-status}"
OC_JSON="$HOME/.openclaw/openclaw.json"
BASHRC="$HOME/.bashrc"
MARKER="# go2lineman: ANTHROPIC_BASE_URL"

LINEMAN_GOOGLE="http://127.0.0.1:9090/proxy/google"
LINEMAN_DEEPSEEK="http://127.0.0.1:9090/proxy/deepseek"
DIRECT_GOOGLE="https://gemini-proxy-worker.bshevelev75.workers.dev"
DIRECT_DEEPSEEK="https://api.deepseek.com"

# ── Читаем текущее состояние ─────────────────────────────────────────────────
current_google=$(python3 -c "
import json
try:
    d = json.load(open('$OC_JSON'))
    print(d.get('models',{}).get('providers',{}).get('google',{}).get('baseUrl','?'))
except: print('?')
" 2>/dev/null || echo "?")

case "$MODE" in
  status)
    if [[ "$current_google" == *"127.0.0.1"* ]]; then
      echo "✅ LINEMAN ON  — OpenClaw: Google+DeepSeek → 127.0.0.1:9090"
    else
      echo "🔴 LINEMAN OFF — OpenClaw: Google→CF Worker, DeepSeek→api.deepseek.com"
    fi
    echo "   Claude Code: всегда напрямую → api.anthropic.com (не зависит от Lineman)"
    ;;

  on)
    python3 - "$OC_JSON" "$LINEMAN_GOOGLE" "$LINEMAN_DEEPSEEK" <<'PYEOF'
import json, sys
path, gurl, durl = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f: d = json.load(f)
d['models']['providers']['google']['baseUrl'] = gurl
d['models']['providers']['deepseek']['baseUrl'] = durl
with open(path, 'w') as f: json.dump(d, f, indent=2, ensure_ascii=False)
PYEOF
    echo "✅ Lineman ON — OpenClaw: Google+DeepSeek → 127.0.0.1:9090"
    sleep 2
    tail -3 /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log 2>/dev/null \
      | grep -q "config change" && echo "🔄 OpenClaw перезагрузил конфиг" \
      || echo "⏳ OpenClaw перечитает конфиг автоматически"
    ;;

  off)
    python3 - "$OC_JSON" "$DIRECT_GOOGLE" "$DIRECT_DEEPSEEK" <<'PYEOF'
import json, sys
path, gurl, durl = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f: d = json.load(f)
d['models']['providers']['google']['baseUrl'] = gurl
d['models']['providers']['deepseek']['baseUrl'] = durl
with open(path, 'w') as f: json.dump(d, f, indent=2, ensure_ascii=False)
PYEOF
    echo "🔴 Lineman OFF — OpenClaw напрямую:"
    echo "   Google → $DIRECT_GOOGLE"
    echo "   DeepSeek → $DIRECT_DEEPSEEK"
    sleep 2
    tail -3 /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log 2>/dev/null \
      | grep -q "config change" && echo "🔄 OpenClaw перезагрузил конфиг" \
      || echo "⏳ OpenClaw перечитает конфиг автоматически"
    ;;

  *)
    echo "Usage: go2lineman.sh on|off|status" >&2
    exit 1
    ;;
esac
