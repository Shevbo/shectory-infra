#!/usr/bin/env bash
# summarise-chat.sh — извлечь диалог из JSONL и сделать handoff через openclaw
# Usage: summarise-chat.sh [session_jsonl_path]
#   Без аргументов — берёт последний изменённый JSONL в проекте

set -euo pipefail

# ── 1. Найти файл сессии ─────────────────────────────────────────────────────
CWD_KEY=$(pwd | sed 's|/|-|g' | sed 's|^-||')
CLAUDE_DIR="$HOME/.claude/projects/$CWD_KEY"

if [[ "${1:-}" != "" ]]; then
  JSONL="$1"
elif [[ -d "$CLAUDE_DIR" ]]; then
  JSONL=$(find "$CLAUDE_DIR" -name "*.jsonl" -newer "$CLAUDE_DIR" -o -name "*.jsonl" \
          2>/dev/null | xargs ls -t 2>/dev/null | head -1)
  [[ -z "$JSONL" ]] && JSONL=$(ls -t "$CLAUDE_DIR"/*.jsonl 2>/dev/null | head -1)
else
  # fallback: ищем в любом проекте
  JSONL=$(find "$HOME/.claude/projects" -name "*.jsonl" 2>/dev/null | xargs ls -t 2>/dev/null | head -1)
fi

if [[ -z "$JSONL" || ! -f "$JSONL" ]]; then
  echo "❌ JSONL-файл сессии не найден" >&2
  exit 1
fi

# ── 2. Извлечь реплики ───────────────────────────────────────────────────────
EXTRACT=$(python3 - "$JSONL" <<'PYEOF'
import json, sys, re

JSONL = sys.argv[1]
turns = []
MAX_CHARS = 400

with open(JSONL, encoding='utf-8', errors='replace') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue

        t = msg.get('type')
        if t not in ('user', 'assistant'):
            continue

        content = msg.get('message', {}).get('content', '')
        if isinstance(content, list):
            text = ' '.join(
                p.get('text', '') for p in content
                if isinstance(p, dict) and p.get('type') == 'text'
            )
        else:
            text = str(content) if content else ''

        # Убрать system-reminder и xml-теги
        text = re.sub(r'<system-reminder>.*?</system-reminder>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]{1,80}>', '', text)
        text = text.strip()

        if not text or len(text) < 5:
            continue

        role = 'USER' if t == 'user' else 'AI'
        turns.append(f"{role}: {text[:MAX_CHARS]}{'…' if len(text) > MAX_CHARS else ''}")

# Последние 60 реплик
for turn in turns[-60:]:
    print(turn)
    print()
PYEOF
)

if [[ -z "$EXTRACT" ]]; then
  echo "❌ Не удалось извлечь реплики из $JSONL" >&2
  exit 1
fi

TOTAL=$(echo "$EXTRACT" | wc -l)
echo "📄 Файл сессии: $JSONL" >&2
echo "📝 Извлечено строк: $TOTAL" >&2
echo "" >&2

# ── 3. Системный промпт для суммаризации ────────────────────────────────────
SYSPROMPT='Ты — ассистент по подготовке handoff-выжимки диалога.
Твоя задача: создать ОДИН markdown-блок, который пользователь скопирует и вставит первым сообщением в новый чат.

ПРАВИЛА:
- Начни с одной строки-инструкции: "Скопируй блок ниже и вставь первым сообщением в новый чат."
- Потом — fenced markdown-блок (```markdown ... ```)
- Внутри блока: заголовок "# Контекст из прошлого чата", цитата с инструкцией агенту, затем секции
- TL;DR: одна строка — главный результат
- О чём был чат: 1-3 предложения
- Главное, что выяснили / сделали: буллеты
- Ключевые решения и почему: буллеты с "потому что"
- Артефакты (файлы и пути): только если есть реальные пути/файлы из диалога
- Открытые вопросы / куда двигаться дальше: буллеты

ЖЁСТКИЕ ЗАПРЕТЫ:
- Не выдумывай факты которых нет в диалоге
- Не включай пустые секции
- Не пиши хронологию "сначала-потом"
- Не добавляй новый запрос внутрь handoff-блока
- После блока — ничего не пиши
- Язык: тот которым общался пользователь'

# ── 4. Запустить openclaw ────────────────────────────────────────────────────
TMPFILE=$(mktemp /tmp/summarise-prompt.XXXXXX)
trap 'rm -f "$TMPFILE"' EXIT

cat > "$TMPFILE" <<PROMPT
Прочитай диалог ниже и создай handoff-выжимку.

ДИАЛОГ:
${EXTRACT}

---
Ответ СТРОГО в следующем формате (и только он, ничего больше):

Скопируй блок ниже и вставь первым сообщением в новый чат.

\`\`\`markdown
# Контекст из прошлого чата

> Это передача контекста из предыдущей сессии. Прочитай, подтверди коротким «принял», и жди следующего сообщения.

**TL;DR:** [одна строка — главный результат чата]

## О чём был чат
[1-3 предложения о теме и цели]

## Главное, что выяснили / сделали
- [пункт]
- [пункт]

## Ключевые решения и почему
- **[решение]** — потому что [причина из диалога]

## Артефакты (файлы и пути)
- [только реальные файловые пути из диалога]

## Открытые вопросы / куда двигаться дальше
- [пункт]
\`\`\`

Правила: только факты из диалога, без выдумки, пустые секции не включать.
PROMPT

openclaw capability model run \
  --model "deepseek/deepseek-v4-flash" \
  --prompt "$(cat "$TMPFILE")" \
  2>/dev/null
