#!/usr/bin/env bash
# Federation inbox poller — checks ~/workspaces/claude-inbox/ every 60s.
# For each new agent file: calls ask-claude.sh, delivers response via SSH or Telegram.
#
# Agent routing table: PATTERN -> SSH_TARGET:INBOX_PATH
# If SSH_TARGET is empty, response goes to Telegram only.

INBOX="${HOME}/workspaces/claude-inbox"
DONE_DIR="${INBOX}/.processed"
LINEMAN="http://127.0.0.1:9090"
CHAT_ID=36910539
LOG="${HOME}/logs/federation-poll.log"

mkdir -p "$DONE_DIR" "${HOME}/logs"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

tg_notify() {
    curl -s -X POST "${LINEMAN}/api/tg/send" \
        -H "Content-Type: application/json" \
        -d "{\"account\": \"default\", \"chat_id\": ${CHAT_ID}, \"text\": $(printf '%s' "$1" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}" \
        >> "$LOG" 2>&1
}

ssh_deliver() {
    local ssh_target="$1" inbox_path="$2" fname="$3" content="$4"
    ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$ssh_target" \
        "mkdir -p '$inbox_path' && cat > '$inbox_path/$fname'" <<< "$content" 2>> "$LOG"
}

# Routing: pattern -> "ssh_user@host|inbox_path|agent_label"
# ssh target empty = Telegram-only delivery
declare -A ROUTES
ROUTES["_GARDEN_"]="shevbo@10.66.0.4|/home/shevbo/wiki/inbox|claude-garden"
ROUTES["_CODEX_"]="||codex"   # Windows VM — SSH path TBD, Telegram only for now

while true; do
    for f in "${INBOX}"/*.md "${INBOX}"/*.txt; do
        [[ -f "$f" ]] || continue
        fname="$(basename "$f")"
        [[ -f "${DONE_DIR}/${fname}" ]] && continue
        # Обрабатываем ТОЛЬКО входящие тикеты от агентов.
        # Без этого ANS_/REPLY_/MSG_/GREETING/TEST* файлы (наши же ответы и шум)
        # рекурсивно попадают в обработку и плодят бесконечную петлю ANS_*ANS_*.
        case "$fname" in
            ANS_*|REPLY_*|MSG_*|GREETING*|TEST_*|github_*) continue ;;
        esac

        # Match route
        matched_pattern=""
        matched_route=""
        for pattern in "${!ROUTES[@]}"; do
            if [[ "$fname" == *"${pattern}"* ]]; then
                matched_pattern="$pattern"
                matched_route="${ROUTES[$pattern]}"
                break
            fi
        done

        # Catch-all: process any unmatched agent file via Telegram only.
        # Извлекаем чистый agent_id из паттерна TASK_<ts>_<agent>.md (что и шлёт escalate.sh).
        # Иначе agent_label = весь fname → Lineman push 404 + ANS-имя громоздкое.
        if [[ -z "$matched_pattern" ]]; then
            matched_pattern="(catch-all)"
            stem="${fname%.*}"
            if [[ "$stem" =~ ^TASK_[0-9]+_(.+)$ ]]; then
                agent_from_name="${BASH_REMATCH[1]}"
            else
                agent_from_name="$stem"
            fi
            matched_route="||${agent_from_name}"
        fi

        log "New file: $fname (pattern: $matched_pattern)"

        ssh_target="$(echo "$matched_route" | cut -d'|' -f1)"
        inbox_path="$(echo "$matched_route" | cut -d'|' -f2)"
        agent_label="$(echo "$matched_route" | cut -d'|' -f3)"

        TIMESTAMP=$(date +%s)
        REPLY_FILE="REPLY_${TIMESTAMP}_FROM_EA.md"
        ANS_FILE="ANS_${TIMESTAMP}_${agent_label}.md"

        RESPONSE="$(~/scripts/ask-claude.sh \
            "Входящий запрос от агента ${agent_label}. Ответь по существу. Файл: ${fname}" \
            "$f" 2>&1)"
        ASK_RC=$?

        # Transient failure: ask-claude печатает sentinel и rc=2. Не помечаем
        # TASK как processed, не пишем ANS — следующий тик попробует снова.
        # Иначе агент получит "API Error: 407" в качестве «ответа EA» и решит,
        # что Клод сказал НЕТ.
        if [[ "$RESPONSE" == *"__EA_TRANSIENT_FAILURE__"* ]] || [[ "$ASK_RC" -ne 0 ]]; then
            attempts_file="${DONE_DIR}/${fname}.attempts"
            attempts=$(cat "$attempts_file" 2>/dev/null || echo 0)
            attempts=$((attempts + 1))
            echo "$attempts" > "$attempts_file"
            log "ask-claude transient failure (attempt ${attempts}/6) for ${fname} — deferring"
            if [[ "$attempts" -lt 6 ]]; then
                # TG только на первую неудачу: 5 одинаковых алертов подряд = спам
                [[ "$attempts" -eq 1 ]] && tg_notify "[federation-poll] ${agent_label}: EA недоступен (попытка 1/6). Файл ${fname} в очереди, ретраи молча."
                continue
            fi
            # >=6 неудач подряд → не зацикливаемся: помечаем + предупреждаем агента
            log "ask-claude permanent failure for ${fname} after ${attempts} attempts"
            touch "${DONE_DIR}/${fname}"
            {
                printf '# Reply from EA to %s — %s\n\n' "${agent_label}" "$(date '+%Y-%m-%dT%H:%M:%S%:z')"
                printf 'Re: %s\n\n---\n\n' "${fname}"
                printf 'EA временно недоступен (LLM-канал упал на %s попытках). Это не отказ по существу — повтори запрос позже.\n' "$attempts"
            } > "${INBOX}/${ANS_FILE}"
            tg_notify "[federation-poll] КРИТ: ${agent_label} не получил ответ EA за ${attempts} попыток. Файл: ${fname}. Проверь iProyal/claude CLI."
            continue
        fi

        # Успех — помечаем processed
        touch "${DONE_DIR}/${fname}"
        rm -f "${DONE_DIR}/${fname}.attempts"
        log "Response ready (${#RESPONSE} chars) for ${agent_label}"

        delivered=false
        if [[ -n "$ssh_target" && -n "$inbox_path" ]]; then
            if ssh_deliver "$ssh_target" "$inbox_path" "$REPLY_FILE" "$RESPONSE"; then
                log "SSH delivered to ${ssh_target}:${inbox_path}/${REPLY_FILE}"
                delivered=true
            else
                log "SSH delivery failed for ${agent_label}"
            fi
        fi

        # Local writeback в inbox: гарантированный ответ для агентов без SSH-route
        # (career-bot и др. поллят свой inbox по ANS_*<agent>*.md)
        {
            printf '# Reply from EA to %s — %s\n\n' "${agent_label}" "$(date '+%Y-%m-%dT%H:%M:%S%:z')"
            printf 'Re: %s\n\n---\n\n' "${fname}"
            printf '%s\n' "${RESPONSE}"
        } > "${INBOX}/${ANS_FILE}"
        log "Local writeback: ${INBOX}/${ANS_FILE}"

        # Доставка через Lineman /api/agent — если агент в node_map, придёт push'ом
        push_status="$(curl -sS -m 5 -G "${LINEMAN}/api/agent/${agent_label}/message" \
            --data-urlencode "from=ea" \
            --data-urlencode "message=EA reply ready: ${ANS_FILE}" \
            -w '%{http_code}' -o /dev/null 2>>"$LOG" || echo "000")"
        log "Lineman push to ${agent_label}: HTTP ${push_status}"

        tg_notify "[federation-poll → ${agent_label}] Обработан: ${fname}
Ответ: ${ANS_FILE} (HTTP push ${push_status})
$(if [[ "$delivered" == "true" ]]; then echo "SSH доставлен"; else echo "SSH не настроен — ANS_ файл в inbox + push"; fi)
---
$(echo "$RESPONSE" | head -5)"
    done
    sleep 60
done
