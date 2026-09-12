#!/usr/bin/env bash
# bootstrap.sh — run the full /onboarding pipeline in the current project folder.
# Idempotent: safe to re-run.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$(pwd)"
FORCE="${ONBOARDING_FORCE:-0}"

# 0. Short-circuit: if already fresh, print one line and exit.
if [[ "$FORCE" != "1" ]]; then
  if fresh_out="$("$SKILL_DIR/bin/check_freshness.sh" 2>/dev/null)"; then
    echo "/onboarding: up-to-date ($fresh_out) — re-run with ONBOARDING_FORCE=1 to refresh anyway"
    exit 0
  fi
fi

echo "=== /onboarding @ $PROJECT_DIR ==="

# 1. Detect agent
eval "$("$SKILL_DIR/bin/detect_agent.sh")"
echo "agent=$agent_id node=$node"
if [[ "$agent_id" == "UNKNOWN" ]]; then
  echo "ERROR: cannot infer agent_id — fill .onboarding/AGENT.md manually or set 'agent_id:' header in AGENTS.md/CLAUDE.md" >&2
  exit 2
fi

# 1.5. Grep-guard: сканирует репо на прямое чтение файлов Ключника.
# Регрессия 2026-08-11 (fed-backup msg 24302): агент cat'ил .lineman-proxy.env
# и засветил 4 ключа. Политика: секреты ТОЛЬКО через Keymaster HTTP API.
# Trusted репо (Lineman, Keymaster сами) whitelisted внутри скрипта.
# Override: ONBOARDING_STRICT_SECRETS=0 — warning вместо hard-fail (для ситуаций
# когда легит-исключение и добавить в whitelist пока нельзя).
if ! "$SKILL_DIR/bin/check_secret_reads.sh" "$PROJECT_DIR"; then
  if [[ "${ONBOARDING_STRICT_SECRETS:-1}" = "1" ]]; then
    echo "ERROR: /onboarding aborted — прямое чтение секретных файлов не разрешено." >&2
    echo "Fix hits выше или override: ONBOARDING_STRICT_SECRETS=0 (только если legit — тогда сообщи Клоду для расширения whitelist)." >&2
    exit 3
  fi
  echo "WARN: secret-read pattern(s) detected but ONBOARDING_STRICT_SECRETS=0 — продолжаем (небезопасно)"
fi

# 2. Канон НЕ копируется в папку агента (изменено 2026-09-12).
# Копия на 40 KB устаревала молча и занимала контекст ради знаний, нужных пару раз за
# сессию. Канон спрашивается из индекса fedrag через Lineman. Нужна только его sha —
# по ней check_freshness.sh понимает, что канон на smain разошёлся с карточкой.
mkdir -p .onboarding
rm -f .onboarding/CANONICAL.md      # чистим наследие: два источника правды хуже одного

CANON_SHA="unknown"
if [[ -r /home/shectory/docs/FEDERATION_AGENT_ONBOARDING.md ]]; then
  CANON_SHA="$(sha256sum /home/shectory/docs/FEDERATION_AGENT_ONBOARDING.md | awk '{print $1}')"
else
  raw="$(curl -sS --max-time 5 http://10.66.0.1:9090/api/onboarding/canon.sha256 2>/dev/null | tr -d ' \n' || true)"
  [[ "$raw" =~ ^[0-9a-f]{64}$ ]] && CANON_SHA="$raw"
fi

# Проверка, что индекс отвечает. Недоступность не валит онбординг: карточка
# самодостаточна, а агент узнаёт из отчёта, что канон сверить не удалось.
FEDRAG_STATE="$(curl -sS --max-time 60 -X POST http://10.66.0.1:9090/api/fedrag/search \
    -H "X-Agent-Name: $agent_id" -H 'Content-Type: application/json' \
    -d '{"query":"контракт агента федерации"}' 2>/dev/null \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("source","no-answer"))' 2>/dev/null \
  || echo unreachable)"
echo "fedrag=$FEDRAG_STATE"
[[ "$FEDRAG_STATE" != "ragkit" && "$FEDRAG_STATE" != "cache" ]] && \
  echo "WARN: индекс канона недоступен ($FEDRAG_STATE) — карточка написана, канон не сверен"

# 3. Write/update local AGENT.md (preserve any TODO markers the user filled)
TS_MSK="$(TZ=Europe/Moscow date '+%Y-%m-%d %H:%M MSK')"
REPO_PATH="$PROJECT_DIR"
PURPOSE_LINE=""
TTL_LINE="staleness_ttl_hours: 168"
if [[ -r .onboarding/AGENT.md ]]; then
  PURPOSE_LINE="$(grep -m1 -E '^purpose:' .onboarding/AGENT.md || true)"
  prev_ttl="$(grep -m1 -E '^staleness_ttl_hours:' .onboarding/AGENT.md || true)"
  [[ -n "$prev_ttl" ]] && TTL_LINE="$prev_ttl"
fi
[[ -z "$PURPOSE_LINE" ]] && PURPOSE_LINE='purpose: TODO — одной строкой что делает агент'
# CANON_SHA уже получен в шаге 2 удалённо — локальной копии канона больше нет.

# Preserve push_endpoint from previous AGENT.md if user already set it
PUSH_LINE=""
if [[ -r .onboarding/AGENT.md ]]; then
  PUSH_LINE="$(grep -m1 -E '^push_endpoint:' .onboarding/AGENT.md || true)"
fi
[[ -z "$PUSH_LINE" ]] && PUSH_LINE='# push_endpoint: http://<host>:<port>/klod/push   # раскомментируй если у агента есть HTTP-сервер для приёма push'

cat > .onboarding/AGENT.md <<EOF
# Agent card — $agent_id

agent_id: $agent_id
node: $node
repo_path: $REPO_PATH
$PURPOSE_LINE
last_onboarded_at: $TS_MSK
canon_sha256: $CANON_SHA
$TTL_LINE
$PUSH_LINE

## Entry points
TODO: какие бинарники / скрипты / эндпоинты этот агент держит (заполни вручную)

## Docs owned by this agent
TODO: пути к README/SPEC/ARCHITECTURE внутри репо (одной строкой каждый)

## Dependencies on federation
- LLM: только через Klod-Access, свой ключ провайдера запрещён
- Secrets: только через Ключника, значение — approval-flow с подтверждением Бориса
- Telegram: через /api/tg/send
- Новый постоянный ресурс: уведомить fed-backup (\`POST /api/agent/fed-backup/message\`)

## Канон федерации: спрашивай, а не читай целиком

Копия канона в папке не хранится. Канон живёт в индексе на sdev и спрашивается
одной командой через Lineman:

\`\`\`bash
curl -sS -m 60 -X POST http://10.66.0.1:9090/api/fedrag/search \\
  -H 'X-Agent-Name: $agent_id' -H 'Content-Type: application/json' \\
  -d '{"query":"свой вопрос обычными словами"}' | jq -r .text
\`\`\`

В индексе: канон онбординга, контракты всех агентов, карта узлов, реестр компонентов,
журналы инцидентов, проектная память. Ответ приходит с путём файла и номерами строк —
первоисточник читается точечно, а не целиком.

\`"source": "fallback"\` в ответе = индекс недоступен: действуй по этой карточке, чего
в ней нет — спрашивай Клода каналом ниже. Не выдумывай.

Лимит 20 запросов в минуту на агента: демон один на федерацию и отвечает по очереди.

## Аварийный минимум — работает, когда индекс недоступен

Всё ниже действует без всякой сети, кроме WireGuard. Раньше рядом лежала копия канона
на 40 KB; её больше нет, поэтому этот раздел и есть твой пол под ногами.

### Куда стучаться

| Узел | Адрес |
|---|---|
| smain (Lineman, Ключник, Клод) | \`10.66.0.1:9090\`, локально \`127.0.0.1:9090\` |
| Ключник | \`10.66.0.1:9093\` |
| sdev | \`10.66.0.4\` |
| hoster | \`10.66.0.7\` |
| vibe (Windows) | \`127.0.0.1:19090\`, обратный SSH-туннель |

### Пять правил, которые не отменяет никакая авария

1. **LLM только через Lineman.** Свой ключ провайдера запрещён всегда.
2. **Секреты только через Ключника.** Значение — по approval-flow, подтверждает Борис.
   Никогда не читай файлы вроде \`.lineman-proxy.env\` напрямую и не печатай значения.
3. **Не спавнить автономные \`claude -p\`**, responder-daemon и автопилоты.
4. **Новый постоянный ресурс** — письмо \`fed-backup\`, иначе он не попадёт в бэкап.
5. **Кишки федерации** (config.json, manifest, node_map, роутинг, upstream) меняются
   только через Клода. Сам не правь, пришли спеку.

### Порядок эскалации

1. Проблема в своей зоне — чини сам, потом сообщи Клоду что сделал.
2. Не своя зона или нужен доступ — письмо Клоду:
   \`POST http://10.66.0.1:9090/api/agent/klod-access/message?from=$agent_id\`
3. Клод молчит больше часа и дело срочное — Борису в Telegram \`@bshevelev75\`.
4. **Ничего не выдумывай.** Не знаешь и спросить не у кого — так и скажи, а не угадывай.
   Неверный ответ дороже отсутствия ответа.

### Если индекс вернул \`"source": "stale"\`

Ответ взят из кэша, его возраст в поле \`age_s\`. Для чтения этого достаточно.
Для необратимого действия (удаление, переключение, выдача доступа) сверься
с первоисточником или спроси Клода.

## News log (заполняется автоматически post_news.sh)
EOF

echo "agent-card=written path=.onboarding/AGENT.md"

# 4. Cross-link from AGENTS.md / CLAUDE.md
MARKER=$(cat <<'EOF'

<!-- onboarding-marker BEGIN — do not edit; rewritten by /onboarding -->
> **Federation onboarding** — карточка агента: [.onboarding/AGENT.md](.onboarding/AGENT.md). Канон федерации локально не хранится: спрашивай индекс через `POST http://10.66.0.1:9090/api/fedrag/search`.
> При старте сессии Claude обязан запустить `bash ~/.claude/skills/onboarding/bin/check_freshness.sh`. Если `status=stale` или `status=absent` — предложить пользователю `/onboarding` (без долгих объяснений, одна строка).
<!-- onboarding-marker END -->
EOF
)
for doc in AGENTS.md CLAUDE.md; do
  [[ -f "$doc" ]] || continue
  # Strip previous marker block if any, then append fresh one
  python3 - "$doc" <<'PY'
import re, sys, pathlib
p = pathlib.Path(sys.argv[1])
src = p.read_text(encoding='utf-8')
new = re.sub(r'\n*<!-- onboarding-marker BEGIN.*?onboarding-marker END -->\n?', '', src, flags=re.DOTALL)
p.write_text(new, encoding='utf-8')
PY
  printf '%s\n' "$MARKER" >>"$doc"
  echo "cross-link=updated doc=$doc"
done

# 5. Ensure portal card
PURPOSE_VAL="$(printf '%s' "$PURPOSE_LINE" | sed -E 's/^purpose:[[:space:]]*//')"
"$SKILL_DIR/bin/check_portal_card.sh" "$agent_id" "$node" "$PURPOSE_VAL" || true

# 6. Register the onboarded event
shopt -s nullglob
docs_arr=( README.md ARCHITECTURE.md SPEC.md WIKI.md docs/*.md )
shopt -u nullglob
DOCS_LIST="$(printf '%s,' "${docs_arr[@]:0:5}" | sed 's/,$//')"
"$SKILL_DIR/bin/post_news.sh" "$agent_id" "$node" onboarded \
  "purpose=$PURPOSE_VAL; repo=$REPO_PATH; docs=${DOCS_LIST:-none}" || true

# 6.1 Pull pending messages from Klod-Access outbox addressed to this agent.
# Печатает inbox=empty / inbox=new count=N с краткими сообщениями. Cursor — в .onboarding/outbox_cursor.
"$SKILL_DIR/bin/pull_inbox.sh" "$agent_id" || true

# 6.2 Register the agent's push endpoint (if push_endpoint: declared in AGENT.md).
# Klod will POST replies directly to this URL instead of waiting for the agent to pull.
"$SKILL_DIR/bin/register_push.sh" "$agent_id" || true

# 7. Check spec-pilot availability (go-harness is a separate skill — Claude invokes it next)
if [[ -r "$HOME/.claude/skills/spec-pilot/SKILL.md" ]]; then
  echo "spec-pilot=installed"
else
  echo "spec-pilot=MISSING hint='rsync -az smain:.claude/skills/spec-pilot/ ~/.claude/skills/spec-pilot/'"
fi
if [[ -r "$HOME/.claude/skills/go-harness/SKILL.md" ]]; then
  echo "go-harness=installed (now invoke it via Skill tool to harness this folder)"
else
  echo "go-harness=MISSING hint='rsync -az smain:.claude/skills/go-harness/ ~/.claude/skills/go-harness/'"
fi

# Pin a hint inside AGENT.md so the next session knows what to do on a new task
if ! grep -q '^next_action_on_new_task:' .onboarding/AGENT.md 2>/dev/null; then
  printf '\nnext_action_on_new_task: при следующей нетривиальной задаче — активировать /spec-pilot (соберёт спеку и согласует перед кодом)\n' \
    >>.onboarding/AGENT.md
fi

echo "=== /onboarding done — next: invoke /go-harness in the same folder ==="
