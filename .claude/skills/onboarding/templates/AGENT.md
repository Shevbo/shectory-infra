# Agent card — <agent_id>

agent_id: <agent_id>
node: <smain|sdev|hoster|pi|pi2|vibe>
repo_path: </abs/path/to/this/folder>
purpose: <одной строкой что делает агент>
last_onboarded_at: <YYYY-MM-DD HH:MM MSK>
canon_sha256: <sha256 первых 64 символов>
staleness_ttl_hours: 168   # после этого срока /onboarding снова предложит обновиться
modules: []                # JIT-модули онбординга по нужде: [tts], [live-audio], [portal-auth].
                           # /onboarding подтянет docs/onboarding-modules/<mod>.md только для
                           # перечисленных. Пусто = только ядро-контракт (канон §0).

## Entry points
- <бинарник/скрипт/endpoint> — <что делает>

# push_endpoint: http://<host>:<port>/klod/push
# Раскомментируй и подставь свой URL если агент держит HTTP-сервер и хочет получать ответы от Клода
# мгновенно (push) вместо опроса /outbox. Если ничего не указано — работает pull-режим (см. §3 канона).

## Docs owned by this agent
- <путь/к/доке.md> — <раздел>

## Dependencies on federation
- LLM: только через Klod-Access, свой ключ провайдера запрещён
- Secrets: только через Ключника, значение — approval-flow с подтверждением Бориса
- Telegram: через /api/tg/send
- Новый постоянный ресурс: уведомить fed-backup (`POST /api/agent/fed-backup/message`)

## Канон федерации: спрашивай, а не читай целиком

Копия канона в папке агента больше не хранится. Канон живёт в индексе на sdev
и спрашивается одной командой через Lineman:

```bash
curl -sS -m 60 -X POST http://10.66.0.1:9090/api/fedrag/search \
  -H 'X-Agent-Name: <agent_id>' -H 'Content-Type: application/json' \
  -d '{"query":"свой вопрос обычными словами"}' | jq -r .text
```

В индексе: канон онбординга, контракты всех агентов федерации, карта узлов, реестр
компонентов, журналы инцидентов, проектная память. Ответ приходит с путём файла и
номерами строк — первоисточник при необходимости читается точечно, а не целиком.

Если в ответе `"source": "fallback"` — индекс недоступен: действуй по этой карточке,
чего в ней нет — спрашивай Клода каналом ниже. Не выдумывай.

Лимит 20 запросов в минуту на агента: демон один на всю федерацию и обслуживает
запросы по очереди, зациклившийся агент иначе ослепил бы остальных.

## Канал общения с Клодом (канон §3, hard rules)

**Отправить** жалобу/вопрос/инфо:
```
POST http://10.66.0.1:9090/api/agent/klod-access/message?from=<agent_id>[&node=<node>]
Content-Type: text/plain   (или application/json {"message":"..."} или form-urlencoded)
Body: свободный текст
```

**Забрать ответы** (poll раз в 5 мин или sooner при активной беседе):
```
GET http://10.66.0.1:9090/api/agent/klod-access/outbox?to=<agent_id>&since=<my_cursor>
```
Курсор `<my_cursor>` = id последнего обработанного ответа, храни у себя. При first-run = 0.

**НЕ ЧИТАТЬ** `~/.federation-inbox/<agent_id>/inbox.jsonl` в надежде найти там ответ Клода — это catch-all inbox для сообщений от других агентов, ответы Клода **всегда** в outbox (регрессия 2026-08-11: klod-stl молча пропустил ответ потому что читал не тот файл).

**Health-check** твоего поллера:
```bash
curl -s "http://10.66.0.1:9090/api/agent/klod-access/outbox?to=<agent_id>&since=0" | jq '.messages | length'
```
≥1 = канал живой; 0 при известной активности = поллер сломан у тебя.

## News log (post_news.sh appends here)
