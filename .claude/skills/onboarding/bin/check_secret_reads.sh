#!/usr/bin/env bash
# Grep-guard: сканирует code репо-агента на прямое чтение файлов Ключника.
# Инцидент 2026-08-11 (fed-backup msg 24302): агент `cat ~/keymaster/.lineman-proxy.env`
# и засветил 4 ключа. Политика: секреты ТОЛЬКО через Keymaster HTTP API
# (POST /keymaster/request-value). Прямое чтение файлов — блокирующий findng.
#
# Usage: check_secret_reads.sh [PATH]  (default: cwd)
# Exit 0 если чисто, 1 если найдены запрещённые паттерны.

set -uo pipefail
ROOT="${1:-$(pwd)}"

# Паттерны прямого чтения (регексы для grep -E). Ловим:
#   cat ~/keymaster/*, cat ~/.keymaster/*, read ~/.claude/.credentials.json,
#   open(...).read(), pathlib.Path().read_text() c этими путями.
FORBIDDEN=(
  '~/keymaster/\.'
  '~/keymaster/[a-z]'
  '~/\.keymaster/credentials/'
  '~/\.keymaster/manifest\.json'
  '~/\.claude/\.credentials\.json'
  '~/\.openclaw/openclaw\.json'
  '~/\.openclaw/agents/[a-z].*/auth-profiles\.json'
  '/home/shectory/keymaster/\.'
  '/home/shectory/\.keymaster/credentials/'
  '/home/shectory/\.claude/\.credentials\.json'
)

# Исключения: сами keymaster-компоненты + этот скрипт + инстр.доки.
EXCLUDE_DIRS=(
  '.git' 'node_modules' '.venv' 'venv' '__pycache__' '.next' 'dist' 'build'
  '.claude/skills/onboarding' '.claude/memory' 'docs/superpowers' 'docs/DAILY'
  'graphify-out' '.harness' '.playwright-mcp'
)
EXCLUDE_ARGS=()
for d in "${EXCLUDE_DIRS[@]}"; do EXCLUDE_ARGS+=(--exclude-dir="$d"); done
# Плюс filename-паттерны: .bak/.old/CLAUDE.md/AGENTS.md — доки/backup'ы, не активный код.
EXCLUDE_ARGS+=(--exclude='*.bak' --exclude='*.bak-*' --exclude='*.old' --exclude='*.orig'
               --exclude='CLAUDE.md' --exclude='AGENTS.md' --exclude='README*.md'
               --exclude='*.md' --exclude='DAILY_*' --exclude='TASK_*' --exclude='ANS_*'
               --exclude='TZ_*.md' --exclude='WIKI.md')

# Whitelist пути: доверенные компоненты, которым читать секреты можно
# (они САМИ = gate-keeper'ы или их legit клиенты). Всё остальное — findng.
#   - keymaster/*                  — сам Ключник (сервер + tg-бот + sync + rotation)
#   - workspaces/infra/lineman/*   — Lineman целиком (LLM-шлюз, использует
#                                    OAuth/proxy-creds напрямую по контракту)
#   - workspaces/keymaster/*       — dev-копии, если есть
WHITELIST_REGEX='(/keymaster/|/workspaces/infra/lineman/|/workspaces/keymaster/|\.claude/skills/onboarding/)'

echo "[grep-guard] scanning $ROOT for direct-secret-read patterns..."
hits_total=0
for pat in "${FORBIDDEN[@]}"; do
  # grep рекурсивно, показывает file:line:match
  raw=$(grep -rEnH "${EXCLUDE_ARGS[@]}" "$pat" "$ROOT" 2>/dev/null || true)
  [ -z "$raw" ] && continue
  # Фильтруем whitelisted пути
  filtered=$(echo "$raw" | grep -vE "$WHITELIST_REGEX" || true)
  [ -z "$filtered" ] && continue
  hits=$(echo "$filtered" | wc -l)
  hits_total=$((hits_total + hits))
  echo
  echo "❌ pattern: $pat ($hits hit(s))"
  echo "$filtered" | head -20
done

if [ "$hits_total" -eq 0 ]; then
  echo "[grep-guard] ok: repo не содержит прямого чтения секретных файлов."
  exit 0
fi

cat <<EOF

════════════════════════════════════════════════════════════════════
❌ ONBOARDING BLOCKED: $hits_total direct-secret-read pattern(s) found.

Твой агент читает файлы Ключника напрямую. Это запрещено с 2026-08-11
(инцидент утечки fed-backup — 4 ключа open text в чат):

  Политика (канон §3): секреты ТОЛЬКО через Keymaster HTTP API.
  POST http://10.66.0.1:9090/keymaster/request-value
       ?name=<NAME>&requester=<your_agent_id>&purpose=<why>
  Ответ содержит delivery-путь; читай оттуда (TTL 300s).

Исправь все hit'ы выше, затем повтори /onboarding.
════════════════════════════════════════════════════════════════════
EOF
exit 1
