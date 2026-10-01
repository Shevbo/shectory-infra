#!/usr/bin/env bash
# check_portal_card.sh — завести карточку агента, если её ещё нет.
#
# Карточка отвечает на вопрос «кто это, на каком узле и зачем» — её видят и Клод,
# и другие агенты. Проверяется при каждом онбординге, поэтому обязана быть
# идемпотентной: повтор ничего не ломает и ничего не дублирует.
#
# Почему через klod_http.sh, а не прямым curl на dashboard.shectory.ru.
# Раньше скрипт ходил на https://dashboard.shectory.ru/api/portal/agents. После
# закрытия админ-API ролью (аудит 2026-09-16) этот путь требует cookie портала,
# которой у агента нет: приходил 302 на страницу входа, скрипт считал карточку
# недоступной и слал Клоду письмо «portal-card-missing». Клод заводил задачу,
# никто её не брал, следующий онбординг повторял всё заново — так за двое суток
# набежали карточки bf-serdcesevas и garden-living-cost.
#
# klod_http.sh ходит на Lineman внутренним маршрутом (WG, а с узлов без него —
# ssh-jump через Pi). Ручку наружу открывать не нужно: это служебный вызов.
set -euo pipefail

AGENT="${1:?usage: check_portal_card.sh <agent_id> <node> [<purpose>]}"
NODE="${2:?node required}"
PURPOSE="${3:-}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTTP="$SELF_DIR/klod_http.sh"

http_code() {   # последняя строка stderr вида "http=200 route=direct"
    sed -n 's/.*http=\([0-9]\{3\}\).*/\1/p' <<<"$1" | tail -1
}

# --- есть ли карточка
err="$(KLOD_AGENT="$AGENT" KLOD_HTTP_TIMEOUT=10 \
       "$HTTP" GET "/api/portal/agents/$AGENT" 2>&1 >/dev/null || true)"
code="$(http_code "$err")"

if [[ "$code" == "200" ]]; then
    echo "portal-card=ok agent=$AGENT"
    exit 0
fi

# --- нет (404) либо маршрут не отработал — пробуем завести
payload="$(AGENT="$AGENT" NODE="$NODE" PURPOSE="$PURPOSE" python3 -c '
import json, os
print(json.dumps({"agent_id": os.environ["AGENT"],
                  "node": os.environ["NODE"],
                  "purpose": os.environ.get("PURPOSE", ""),
                  "source": "onboarding-skill"}, ensure_ascii=False))')"

tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
printf '%s' "$payload" > "$tmp"

err="$(KLOD_AGENT="$AGENT" KLOD_HTTP_TIMEOUT=15 \
       "$HTTP" POST "/api/portal/agents" "$tmp" application/json 2>&1 >/dev/null || true)"
create_code="$(http_code "$err")"

# 201 — завели, 200 — карточка уже была и обновилась. Оба исхода нормальные.
if [[ "$create_code" == "201" || "$create_code" == "200" ]]; then
    echo "portal-card=created agent=$AGENT http=$create_code"
    exit 0
fi

# --- не вышло: сообщаем Клоду, но с диагностикой, а не одним «нет карточки».
# Без кодов обоих запросов прошлые письма не позволяли понять, сломана ручка,
# маршрут или сам агент.
msg="portal-card-missing: agent=$AGENT node=$NODE purpose=${PURPOSE:-unknown} probe_http=${code:-none} create_http=${create_code:-none}"
printf '%s' "$msg" | "$HTTP" POST \
    "/api/agent/klod-access/message?from=$AGENT&node=$NODE&topic=portal-card" - text/plain \
    >/dev/null 2>&1 || true
echo "portal-card=reported-missing agent=$AGENT probe=${code:-none} create=${create_code:-none}"
