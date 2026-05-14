#!/usr/bin/env bash
# PostToolUse hook: логируем Bash вызовы Claude Code в Lineman /api/log
# Вызывается Claude Code после каждого использования Bash инструмента
# Stdin: JSON {tool_name, tool_input, tool_response}

set -euo pipefail

INPUT=$(cat)

TOOL=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null || echo "")

# Только Bash вызовы
[[ "$TOOL" != "Bash" ]] && exit 0

# Линеман должен быть запущен
curl -sf http://127.0.0.1:9090/health > /dev/null 2>&1 || exit 0

# Извлекаем данные и отправляем сигнал
python3 - <<PYEOF
import json, sys, time, urllib.request, urllib.error

try:
    data = json.loads('''$INPUT'''.replace("'", "\\'"))
except:
    sys.exit(0)

tool_input    = data.get("tool_input", {})
tool_response = data.get("tool_response", {})

cmd = tool_input.get("command", "")[:120] if isinstance(tool_input, dict) else ""
out = ""
if isinstance(tool_response, dict):
    out = str(tool_response.get("stdout") or tool_response.get("output") or "")[:60]

# Оцениваем размер вывода в токенах (~4 chars/token)
out_all = str(tool_response)
tokens_out = len(out_all) // 4

payload = json.dumps({
    "ts":         time.time(),
    "from_node":  "smain",
    "from_agent": "claude-code",
    "to_service": "bash",
    "type":       "tool_call",
    "tokens_out": tokens_out,
    "status":     "ok",
    "meta":       {"cmd": cmd},
}).encode()

try:
    req = urllib.request.Request(
        "http://127.0.0.1:9090/api/signal",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    urllib.request.urlopen(req, timeout=2)
except:
    pass
PYEOF

exit 0
