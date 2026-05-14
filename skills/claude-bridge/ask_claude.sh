#!/bin/bash
# Вызов Claude Code для получения ответа
# Использование: ask_claude.sh "вопрос"
# Ответ приходит на stdout

QUESTION="$1"
if [ -z "$QUESTION" ]; then
  echo '{"error":"no question provided"}'
  exit 1
fi

# Создаём временный MCP-конфиг, чтобы Claude подключил OpenClaw
MCP_CFG=$(mktemp)
cat > "$MCP_CFG" << 'MCPEOF'
{
  "mcpServers": {
    "openclaw-tank": {
      "command": "/home/shectory/skills/claude-bridge/openclaw-mcp-server.sh",
      "args": [],
      "env": {}
    }
  }
}
MCPEOF

# Запускаем Claude в headless режиме с вопросом
CLAUDE_RESPONSE=$(claude --print "$QUESTION" --mcp-config "$MCP_CFG" 2>/dev/null)
CLAUDE_EXIT=$?

rm -f "$MCP_CFG"

if [ $CLAUDE_EXIT -ne 0 ]; then
  echo "{\"error\":\"claude exit $CLAUDE_EXIT\",\"response\":\"\"}"
  exit $CLAUDE_EXIT
fi

echo "$CLAUDE_RESPONSE"
