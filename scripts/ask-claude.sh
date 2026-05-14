#!/bin/bash
# ask-claude.sh — Быстрый запрос к Executive Advisor (Клод)
# Использование: ~/scripts/ask-claude.sh "Твой вопрос"
# Или с файлом контекста: ~/scripts/ask-claude.sh "Вопрос" /path/to/context.md

QUESTION="$1"
CONTEXT_FILE="$2"

if [ -z "$QUESTION" ]; then
    echo "Использование: ask-claude.sh \"вопрос\" [файл_контекста]"
    exit 1
fi

if [ -n "$CONTEXT_FILE" ] && [ -f "$CONTEXT_FILE" ]; then
    PROMPT="Вопрос от агента системы Бориса:

$QUESTION

Контекст из файла $CONTEXT_FILE:
$(cat "$CONTEXT_FILE")
"
else
    PROMPT="Вопрос от агента системы Бориса: $QUESTION"
fi

exec claude --print -p "$PROMPT"
