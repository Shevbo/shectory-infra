# Federation Agent — Onboarding Contract

**Read this before doing anything else.** Этот документ — единственный
источник истины о том, как агенту федерации правильно жить. Если что-то не
покрыто здесь — пиши Клоду (см. ниже), не импровизируй.

Владелец: Klod-Access (klod-builder@smain). Последнее обновление: 2026-08-11.

> **AUTO**: динамические секции (§13 «Реестр агентов», §14 «События за сутки»)
> пересобираются ежедневно скриптом `scripts/onboarding_refresh.py` на smain.
> Статика — § 1..§12 — правится только Клодом руками.

---

## Кто ты в федерации

Ты — независимый агент, работающий на узле (`smain`, `hoster`, `sdev`, `pi`,
`pi2`, `vibe`). У тебя свой `agent_id` (например `smarthome`, `eshkola`,
`career-bot`, `klod-stl`) и `node` (где ты физически живёшь).

Ты НЕ держишь:
- сырые LLM-API-ключи (Anthropic/Google/DeepSeek/OpenAI/OpenRouter);
- пароли почтовых ящиков, БД, GitHub;
- общие auth-секреты федерации.

Всё, что нужно, ты получаешь по запросу через **Klod-Access** (это Я).

---

## 0. Ядро-контракт vs JIT-модули

Этот документ — **ядро-контракт**: кто ты (выше), адрес Lineman (§1), LLM-доступ
`/api/klod/ask` (§2), канал «жалоба → Клод» (§3), запреты (§7). Это носят в
контексте **все** агенты — коротко, без лишнего.

**Тематические модули** (голос/TTS, live audio, portal-auth+nginx) вынесены в
`docs/onboarding-modules/` и подтягиваются **JIT — только теми, кому нужны**, по полю
`modules:` в `.onboarding/AGENT.md`. Агент-парсер не должен носить в контексте
nginx-конфиги и голосовые API. `/onboarding` отдаёт ядро всем, модули — по списку
`modules:` карточки. Текущие модули:

| модуль | файл | кому |
|---|---|---|
| `tts` | `docs/onboarding-modules/tts.md` | агенты, которым нужен синтез речи |
| `live-audio` | `docs/onboarding-modules/live-audio.md` | двусторонний голос (Titan/Nurse) |
| `portal-auth` | `docs/PORTAL_AUTH_STANDARD.md` | агенты с логином пользователей в дашборд/портал |

---

## 1. Сетевой адрес Klod-Access

Все мои сервисы живут на `smain`, доступны через WireGuard:

```
Lineman API:    http://10.66.0.1:9090
Keymaster API:  http://127.0.0.1:9093     (только loopback на smain)
```

### 1.1 Если у тебя нет WireGuard напрямую

**Это нормально**. Большинство устройств не в WG. Маршрут зависит от класса:

**Linux / unix агенты на узлах в WG** (smain, hoster, sdev):
- WG поднят на самом узле → `curl http://10.66.0.1:9090/api/klod/ask`. Готово.

**Windows-агенты (vibe и подобное)**:
- WG на Windows исторически нестабилен (`vibe-access-via-pi` в памяти Бори).
- Канал: **через `shevbo-pi` как ssh-jump**. Pi сам в WG и видит `10.66.0.1`.
- Два паттерна:
  - **Удалённый curl**:
    ```powershell
    ssh -J shevbo-pi boris@<vibe-ip> "curl -sS -X POST http://10.66.0.1:9090/api/klod/ask -H 'Content-Type: application/json' -d '{...}'"
    ```
  - **Локальный port-forward** (если делаешь много вызовов):
    ```powershell
    ssh -N -L 9090:10.66.0.1:9090 shevbo-pi   # держать сессию открытой
    # дальше из Windows кода:
    curl http://127.0.0.1:9090/api/klod/ask -d '{...}'
    ```
- Pi → smain работает чисто, не нужно ничего ставить на Windows кроме
  OpenSSH-клиента.

> **Риск: `shevbo-pi` — единая точка отказа и латерального движения.** Весь
> Windows/IoT-трафик в федерацию идёт через один ssh-jump. Если Pi упал —
> эти агенты слепнут; если Pi скомпрометирован — злоумышленник видит весь их
> трафик к Lineman и может ходить в WG от их имени. Поэтому:
> - **Hardening Pi обязателен**: ssh только по ключам (`PasswordAuthentication no`),
>   отдельный непривилегированный пользователь для jump, `AllowTcpForwarding` только
>   на `10.66.0.1:9090`/`:9093`, автообновления безопасности, fail2ban.
> - **Мониторинг**: недоступность Pi = деградация канала. Проверяй `ssh shevbo-pi true`
>   перед серией вызовов; при таймауте не молоти в цикл.
> - **Что делать агенту при падении jump**: НЕ поднимать свой прямой публичный путь
>   и НЕ кешировать ключи «пока Pi лежит». Перейди в offline-очередь (копи задачи
>   локально) и сообщи Боре по любому доступному каналу, что Pi недоступен. Клод и
>   Дозор увидят пропажу heartbeat, но твой явный сигнал ускорит починку.

**Raspberry Pi / IoT устройства без WG** (pi2, smarthome и подобное):
- Если устройство в локальной сети дома и достаёт `shevbo-pi` — повторяй
  Windows-паттерн через ssh-jump.
- Если устройство только в внешнем интернете без VPN — **не открывай
  публичный путь сам**, напиши Боре через ssh smain что нужен WG/Tailscale
  клиент. Публичный IP smain для агентов закрыт IP-allowlist'ом (сам адрес —
  в Keymaster `SMAIN_PUBLIC_IP`, но он тебе не нужен: ходи через WG/Pi).

**Никогда не**:
- открывать публичный интернет к Lineman/Keymaster
- держать сырой LLM-ключ на узле «потому что временно нет канала»
- импровизировать ssh-цепочки `ssh smain 'cat openclaw.json' | …` — это
  обход политики, не норма

---

## 2. LLM-доступ (политика 2026-06-18 — НИКАКИХ исключений)

**Ни один агент не держит LLM-ключ.** Все LLM-вызовы — через единую ручку:

```
POST  http://10.66.0.1:9090/api/klod/ask
Headers:  Content-Type: application/json
Body:     {
  "agent":      "<твой agent_id>",          // required
  "prompt":     "<текст>",                  // required
  "model_hint": "<see table below>",        // optional, default normal
  "max_tokens": 1000                        // optional, default 1000, cap 4000
}
Response: { "text": "...", "model_used": "...", "provider": "...",
            "agent": "...", "elapsed_ms": N }
```

### Доступные `model_hint`

> **Иллюстративная таблица — истина в `GET /api/klod/models`** (§2.0). Ниже 6
> основных хинтов; полный список хинтов и реальные имена моделей всегда актуальны
> только в каталоге. Не хардкодь эти имена — спрашивай каталог.

| hint          | provider  | когда брать                                   |
|---------------|-----------|-----------------------------------------------|
| `fast`        | anthropic | короткий ответ, низкая цена                   |
| `normal`      | anthropic | рабочая лошадка (default)                      |
| `deep`        | anthropic | аналитика, длинный контекст                    |
| `gemini-pro`  | google    | reasoning через Gemini                         |
| `gemini-flash-lite` | google | parsing/extract intent, дёшево              |
| `local-fast`  | lm-studio | локально, без квот / сети (batch/parsing/test) |

Полный набор (все Gemini 3.x, DeepSeek v4, TTS/vision/image, local-*) — в `/api/klod/models`.
Нужна модель, которой нет в хинтах — шли `provider`+`model` явно (см. §2.0).
LM Studio (локальный, без квот) — через SSH-туннель на smain; для frontier-reasoning cloud.

**Контекстное окно для LM Studio:** передавай поле `context_size` в body `/api/klod/ask`:

```json
{ "agent":"...", "prompt":"...", "model_hint":"local-fast", "context_size": 16384 }
```

LM Studio (v0.3+) учитывает это поле при JIT-load модели. Если модель уже загружена
с другим n_ctx — текущий контекст сохраняется (LM Studio не перегружает на ходу).
Для cloud-провайдеров параметр игнорится. Реальная переразкгрузка LM Studio с новым
n_ctx — отдельная задача через admin-API LM Studio (пока не реализовано в Lineman).

### 2.0 Полный каталог LLM (динамический)

```
GET  http://10.66.0.1:9090/api/klod/models
Response: {
  "providers": {
    "anthropic":  [список всех claude-* которые отдаёт API],
    "google":     [все gemini-*/gemma-*/lyria-*/deep-research-* и т.д.],
    "deepseek":   [deepseek-v4-flash, deepseek-v4-pro],
    "lm-studio":  [google/gemma-4-12b, deepseek-r1-distill-qwen-14b, ...]
  },
  "errors": {},
  "klod_hints": {...},   // наш реестр /api/klod/ask
  "tts_hints":  {...},   // наш реестр /api/klod/tts
  "totals":     {anthropic: 9, google: 50, deepseek: 2, lm-studio: 6},
  "ttl_s": 3600
}
```

Кэш Lineman = 1 час. Источник — прямые запросы к каждому провайдеру (Anthropic /v1/models
через OAuth, Google /v1beta/models, DeepSeek /v1/models, LM Studio /v1/models). Имена
**без искажений** — ровно то что отдаёт каждый upstream. Хочешь модель которой нет в
`klod_hints` — шли через `provider`+`model` (см. §2):

```json
{ "agent":"...", "prompt":"...", "provider":"google", "model":"gemini-2.5-computer-use-preview-10-2025" }
```

### 2.1 TTS и Live audio — JIT-модули (не в ядре)

Голосовые возможности вынесены в отдельные модули — их подтягивают только
голосовые агенты, чтобы агент-парсер не носил это в контексте (см. §0):

- **TTS** (`/api/klod/tts`, base64-аудио): модуль `docs/onboarding-modules/tts.md`,
  поле `modules: [tts]` в `.onboarding/AGENT.md`.
- **Live audio** (двусторонний WebSocket-голос): модуль
  `docs/onboarding-modules/live-audio.md`, поле `modules: [live-audio]`.

### Возможные ошибки

- `400` — нет `prompt` / битый JSON
- `403` — `agent` не в реестре федерации (§13). Allowlist **закрыт** с 2026-07-04:
  источник — реестр §13 (node_map + federation_registry + `klod_ask.extra_agents`).
  Неизвестное имя не проходит. Пройди онбординг (§5) или попроси Клода добавить тебя.
- `429` — превышен бюджет (per-hour или per-day для твоего `agent`)
- `502` — upstream LLM-провайдер упал; ретрай с другим `model_hint`
- `503` — Klod OAuth недоступен (только для `fast|normal|deep`)

### Что НЕ делать

- ❌ Не ходить в `/proxy/anthropic`, `/proxy/google`, `/proxy/deepseek`
  напрямую. Эти пути зарезервированы за Lineman+Klod и legacy voice apps.
- ❌ Не запрашивать `GEMINI_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` /
  `CLAUDE_API_KEY` / `OPENROUTER_API_KEY` через Keymaster `request-value`.
  Pre_approved = `[lineman@smain]` only (политика 2026-06-23). Любой агент
  получит pending → Боря откажет → направит сюда.
- ❌ Не туннелировать ssh-цепочки `ssh smain 'cat openclaw.json' | …`.

---

## 3. Канал «жалоба → Клод» (единственный правильный)

**⚠️ КАНОНИЧЕСКИЙ КОНТРАКТ. Отклонения = молчаливая потеря сообщения.**

Существует **ровно один** путь общения с Клод-Доступом. Никаких «альтернативных»
inbox'ов или catch-all файлов не использовать — они существуют для legacy,
но НЕ для двусторонней переписки с Клодом.

| Направление | Что делать | Endpoint | Куда легло |
|---|---|---|---|
| Ты → Клод | Отправить жалобу/вопрос | `POST /api/agent/klod-access/message?from=<self>` | `~/klod-access/inbox.jsonl` |
| Клод → Ты | Забрать ответы (pull) | `GET /api/agent/klod-access/outbox?to=<self>&since=<cursor>` | `~/klod-access/outbox.jsonl` |
| Клод → Ты (push, опционально) | Зарегистрировать URL, Клод POST'нёт | `POST /api/agent/klod-access/push_url` — см. §3.1 | твой HTTP-сервер |

**Как это работает на стороне Клода (защита от промаха, 2026-08-11):**
- Когда Клод (или любой скрипт) шлёт `POST /api/agent/<X>/message?from=klod-access`, сервер **автоматически** пишет в `~/klod-access/outbox.jsonl`, а НЕ в `~/.federation-inbox/<X>/inbox.jsonl`. Ответ содержит `via: "klod-access-outbox"` — маркер что маршрутизация правильная. Раньше сообщения уходили в federation-inbox catch-all, откуда их никто из pull-подписчиков не видел. Инвариант закреплён в `tests/test_klod_access_routing.py`.
- Тело можно слать как `application/json`, `text/plain`, ИЛИ `application/x-www-form-urlencoded` (например `curl --data-urlencode "message@file"`) — сервер декодирует все три формы. URL-encoding больше не портит контент.

**Диагностика (если Клод «молчит»):**
| Симптом | Первая проверка |
|---|---|
| Ты POST'нул, Клод не отвечает часами | `curl /api/agent/klod-access/outbox?to=<self>&since=<твой_last_cursor>` — если есть новые, поллер сломан на твоей стороне |
| Твой `since=` не двигается | Клод действительно не ответил; повтори с `[QUESTION]` префиксом, укажи urgency |
| GET возвращает пусто, но ты видишь ответ в TG/через Борю | Кто-то шлёт в неправильный канал. Пришли Борису id ответа + путь откуда взял |
| POST возвращает `via: "lineman-file-catchall"` при `from=klod-access` | Регрессия — Борю пинговать немедленно, инвариант нарушен |

Когда у тебя возникла проблема, баг, неуверенность по контракту — напиши мне.

```
POST  http://10.66.0.1:9090/api/agent/klod-access/message
       ?from=<твой agent_id>&node=<smain|hoster|pi2|...>
Headers: Content-Type: text/plain   (или application/json с {"message":"..."} )
Body:    свободный текст жалобы/вопроса
Response: { "status": "ok", "id": N }
```

Lineman автоматически дополнит **триаж**: если в тексте есть слова-маркеры
(401/403/429/5xx/timeout/упал/ошибка/blocked) — подгрузит твои последние 5
ошибочных запросов из `request_log` и приложит как контекст. Не нужно
дублировать.

### Получение моих ответов (pull-режим)

Я отвечаю в outbox. Ты периодически опрашиваешь:

```
GET  http://10.66.0.1:9090/api/agent/klod-access/outbox?to=<твой agent_id>&since=<cursor>
Response: { "messages": [ { "id": N, "ts": "...", "to": "...",
                            "in_reply_to": M, "message": "..." }, ... ] }
```

Cursor `since` храни локально (последний обработанный `id`). Опрашивать раз в
~5 мин.

### 3.1 Push-режим (опционально, для агентов с HTTP-сервером)

Если у тебя есть HTTP-сервер и не хочется опрашивать `/outbox` каждые 5 мин —
зарегистрируй свой push-эндпоинт. Клод будет POST'ить туда reply мгновенно,
сразу после `write_outbox`.

Регистрация (один раз; /onboarding делает это автоматически если в
`.onboarding/AGENT.md` есть поле `push_endpoint:`):

```
POST  http://10.66.0.1:9090/api/agent/klod-access/push_url
       ?agent=<твой agent_id>&url=<http(s)://host:port/path>
Response: { "status": "ok", "agent": "...", "registered": true, "url": "..." }
```

Снять регистрацию: тот же POST с пустым `url`. Посмотреть кто что зарегистрировал:
`GET /api/agent/klod-access/push_urls`.

**Проверка владения (с 2026-07-04).** Регистрация push_url защищена от угона чужого
outbox двумя барьерами:
1. `agent` обязан быть в реестре §13 — нельзя зарегистрировать endpoint за произвольное имя.
2. `url` обязан указывать **внутрь федерации** (WG `10.66.0.0/24`, loopback или короткое
   WG-имя узла типа `smain`/`hoster`). Внешний адрес → `403` — outbox нельзя увести наружу.

Весь `/api/*` вдобавок закрыт IP-allowlist'ом (loopback/WG/Tailscale), снаружи push_url
недостижим. Криптографической per-agent идентичности пока нет: агент в WG теоретически
может зарегистрировать endpoint за другого известного агента. Полноценная attribution
(per-agent токен) — в бэклоге; до неё доверенная граница = членство в WG.

Формат push-payload, который Клод POST'нёт на твой URL (Content-Type: application/json):

```json
{
  "from": "klod-access",
  "to":   "<твой agent_id>",
  "id":   123,
  "in_reply_to": 100,
  "ts": "ISO-8601",
  "message": "..."
}
```

Заголовок `X-Klod-Channel: push` помогает отличить push от обычного POST. Ответь
2xx — это считается доставленным. На не-2xx или таймаут (>5с) push помечается
неудачным, **сообщение остаётся в outbox** — забери его pull'ом по §3.

Pull-режим продолжает работать как fallback. Push — это ускорение, не замена.

---

## 4. Если нужен секрет (НЕ LLM-ключ)

GitHub-токены, ssh-keys, application-passwords, etc. — через Keymaster.

**Только с loopback на smain или через свой узел в WG**:

```
POST  http://127.0.0.1:9093/keymaster/request-value
       ?name=<SECRET_NAME>&requester=<твой agent_id>&purpose=<что+делаешь>
Response (если в pre_approved):  { "status": "approved", "delivery": "~/.keymaster/delivery/<req_id>", "ttl_seconds": 300 }
Response (если нет):              { "request_id": "...", "status": "pending" }
```

Боря увидит запрос в `@ShectoryKeyMasterBot` с кнопками ✅/❌. Тебе никаких
кодов вводить не нужно — он жмёт кнопку, дальше delivery.

Метаданные секрета (что за секрет, кто использует, где живёт значение) —
открыты, не требуют одобрения:

```
GET   http://127.0.0.1:9093/keymaster/query?name=<NAME>&requester=<твой agent_id>
GET   http://127.0.0.1:9093/keymaster/list?requester=<твой agent_id>
GET   http://127.0.0.1:9093/keymaster/manifest                  → весь манифест (без значений)
```

---

## 5. Регистрация нового агента в федерации

Если тебя только что подняли:

1. Получить от Бори `agent_id` и узел (`node`).
2. Определить класс узла и канал до `10.66.0.1` (см. §1.1):
   - Linux в WG → прямой curl
   - Windows → ssh-jump через `shevbo-pi`
   - IoT/Pi в LAN без WG → ssh-jump через `shevbo-pi` если достаёт его,
     иначе писать Боре про WG-клиент
3. Сделать тестовый POST в `/api/agent/klod-access/message` со словами
   «онбординг: я <agent_id> на <node>, рад работать». Я увижу, отвечу в
   outbox, добавлю в реестр §13.
4. LLM-вызовы `/api/klod/ask` откроются ТОЛЬКО после добавления в реестр
   (allowlist закрыт, §2). До этого — 403; после онбординга — работает.
5. Если нужен секрет — `request-value` (см. §4). Боря одобрит явно если ОК.

---

## 6. Telegram-каналы (если нужно слать Боре)

**НИКОГДА не открывай свой бот** — всё через `Lineman /api/tg/send`:

```
POST  http://10.66.0.1:9090/api/tg/send
Body: { "account": "default",          // @ShectoryKlodBot — общий канал
        "chat_id": "<BORIS_CHAT_ID>",  // ID Бори — не хардкодь; Lineman подставит
        "text":    "..." }
```

`chat_id` можно **опустить** — Lineman по умолчанию шлёт Боре (дефолт настроен на
сервере). Если нужен явный ID — возьми `BORIS_CHAT_ID` из Keymaster, не вписывай
число в код/доки (оно уже утекало в git-историю).

Rate-limit 15 сек на account. Дедуп 60 сек одинаковых сообщений (борьба с
циклами).

Опциональный `account: "keymaster"` — @ShectoryKeyMasterBot, исключительно
для Ключника. Не использовать для общих алертов.

---

## 7. Что строго запрещено

- Кешировать LLM-ключи в env/файлах своего узла
- Открывать публичный интернет к Lineman/Keymaster без аппрува
- Логировать значения секретов (только sha256-отпечатки)
- Дёргать `/proxy/anthropic|google|deepseek` напрямую (это Lineman-internal)
- Импровизировать обходы при сломанном маршруте — писать жалобу в inbox

---

## 8. Кто тебя слышит

- **Я (Klod-Access)** — читаю inbox, отвечаю в outbox, решаю архитектуру.
- **Медик** на `hoster` — пытается авто-чинить R0-R1, R2+ эскалирует Боре.
- **Билдер** на `smain` — делает code-changes по тикетам (через Klod-backlog).

Если ты молчишь — никто не приходит. Жалуйся первым, не сиди в петле.

---

## 9. Где задавать вопросы по этому документу

Пиши в `klod-access` inbox с темой «онбординг-вопрос: …». Я обновлю
документ или добавлю исключение к политике (после согласования с Борей).

---

## 10. Стандарты, которые ты обязан соблюдать

| Стандарт | Где живёт | Что значит для тебя |
|---|---|---|
| Auth | `/home/shectory/workspaces/infra/lineman/docs/PORTAL_AUTH_STANDARD.md` | Вход в дашборд по email, не `boris`. SSO-канон для всех порталов федерации. |
| Time | UTC+3 (MSK) | Все даты в логах/коммитах/AGENT.md — MSK с явным `MSK` суффиксом. |
| Commit | conventional commits, **русский** | `fix(<agent>): ...`, `feat(<agent>): ...`. |
| Harness | `AGENTS.md` + `.harness/baseline.md` в корне каждого репо | См. skill `/go-harness`. Любая папка, в которую может прийти автономный агент — обязана быть L4-ready. |
| Безопасность | См. §7 + ниже | `/api/*` Lineman закрыт IP-allowlist'ом, secrets — только через Keymaster, логи без значений. |
| Общение | см. §10.1 ниже | Короткие фразы, русский, без воды, без эмодзи, без многостраничных отчётов. |

### 10.1 Краткое общение (mandatory)

Применяется ко **всему**: ответам пользователю, TG-сообщениям, коммитам, README, отчётам skill'ов.

- Без воды, без вступлений «Понял! Сейчас сделаю...», без закрывающего «Готово!». Сразу результат.
- Без эмодзи (включая ✅/❌/🚀 и т.п.).
- Без em-dash (`—` пиши только если это часть русской грамматики, не заменитель скобок).
- Без многостраничных отчётов. Если есть таблица — таблица; если список — список; **до 8 строк по умолчанию**, расширяешь только если пользователь явно попросил подробности.
- Без повтора того, что пользователь уже знает (свой план, перечисление того что я сделаю, и т.п.).
- Код пиши нормально (это не текст), но без необъяснительных комментариев.

Это **жёсткий contract**, не предпочтение. Длинные простыни в TG и в чате — повод для замечания агенту.

---

## 11. **Правило новостей (mandatory)**

Любое **существенное** изменение на стороне твоего агента — обязано
немедленно попасть в этот канон. Это единственный способ для других агентов
узнать «что у тебя теперь есть, где это лежит, и за что ты отвечаешь».

Триггеры (без исключений):

- Появился новый док (`README.md` / `SPEC.md` / `ARCHITECTURE.md`) у тебя в репо
- Изменилась цель / scope агента (`purpose`)
- Переехал репо (`repo_path`)
- Изменился публичный endpoint, который ты держишь
- Появилась/исчезла зависимость от другого агента федерации
- Ты обнаружил пробел в этом каноне (тогда event=`canon-gap`)
- Тебя списали / на паузе (event=`retired`)

Как сообщить:

```bash
~/.claude/skills/onboarding/bin/post_news.sh <agent_id> <node> <event> "<key=val; key=val>"
# или напрямую (если skill ещё не установлен):
curl -sS -X POST "http://10.66.0.1:9090/api/agent/klod-access/message?from=<agent_id>&node=<node>&topic=news" \
     -H 'Content-Type: text/plain' \
     --data "news event=<event> ts=\"$(TZ=Europe/Moscow date '+%Y-%m-%d %H:%M MSK')\" agent=<id> node=<node> details=\"...\""
```

Ежедневный refresh-скрипт собирает все события за сутки и подшивает их в
§14. Что не отправлено в news — для других агентов **не существует**.

---

## 12. Skill `/onboarding`

Для агента, которым управляет Claude Code (включая sub-агентов и dev-папки),
есть skill `/onboarding` (на `smain` и `sdev` в `~/.claude/skills/onboarding/`;
Windows — Боря копирует руками).

Что делает при `/onboarding` в проектной папке:

1. Определяет `agent_id` и `node` (по AGENT.md → AGENTS.md/CLAUDE.md → имени папки).
2. Тянет **ядро-контракт** (этот канон) в `.onboarding/CANONICAL.md` (3-уровневый
   fallback: local file → Lineman HTTP → ssh-jump через Pi).
2a. Тянет **JIT-модули** из `docs/onboarding-modules/`, перечисленные в поле
   `modules:` карточки `.onboarding/AGENT.md`, в `.onboarding/modules/<mod>.md`.
   Пусто → только ядро (§0). Агент-парсер не носит голос/nginx в контексте.
3. Пишет/обновляет project-local `.onboarding/AGENT.md` (карточка агента).
4. Добавляет однострочный маркер в `AGENTS.md`/`CLAUDE.md` (если их нет — пропускает).
5. Проверяет наличие карточки на портале; нет — создаёт, либо алертит Клоду.
6. Шлёт `news event=onboarded` (см. §11).

**Идемпотентен и токено-эффективен**: при повторном запуске skill сначала зовёт
`check_freshness.sh`. Если карточка не просрочена (TTL по умолчанию 168 ч) и
SHA канона не изменился — печатает ОДНУ строку `up-to-date` и выходит, не
читая канон и не вызывая под-skill'ы.

**Проактивная проверка устаревания**: маркер в `AGENTS.md`/`CLAUDE.md`
инструктирует любого Claude при старте сессии прогнать `check_freshness.sh`.
При `status=stale`/`absent` — предлагает пользователю `/onboarding` одной
строкой, без долгих объяснений.

**НЕ редактирует** этот канон сам — только Клод руками и `onboarding_refresh.py`.

---

## 13. Реестр агентов (AUTO)

<!-- AUTO:agents BEGIN -->
| node | agent_id | name | repo |
|---|---|---|---|
| hoster | `main` | Hoster | — |
| hoster | `shopin` | Shopin | `~/workspaces/shopin` |
| hoster | `inbox` | Inbox | `/home/shectory/workspaces/inbox` |
| sdev | `main` | TankDev | — |
| sdev | `selfcoder` | Selfcoder | `/home/shectory/workspaces/selfcoder` |
| sdev | `qaper` | QAper | `/home/shectory/workspaces/qaper` |
| smain | `selfcoder` | selfcoder | `/home/shectory/workspaces/selfcoder` |
| smain | `qaper` | qaper | `/home/shectory/workspaces/qaper` |
| smain | `virtual-boris` | virtual-boris | `/home/shectory/workspaces/virtual-boris` |
| smain | `titan` | titan | `/home/shectory/workspaces/titan` |
| smain | `nurse` | nurse | `/home/shectory/workspaces/nurse` |
| smain | `guilya` | guilya | `/home/shectory/workspaces/guilya` |
| smain | `jobsearch-scanner` | jobsearch-scanner | `/home/shectory/.openclaw/agents/jobsearch-scanner` |
| smain | `resume-editor` | resume-editor | `/home/shectory/workspaces/resume-editor` |
| smain | `interview-coach` | interview-coach | `/home/shectory/workspaces/interview-coach` |
| smain | `inbox` | inbox | `/home/shectory/workspaces/inbox` |
| smain | `klod-access` | klod-access | `/home/shectory/klod-access` |
| smain | `eshkola` | eshkola | `/home/shectory/workspaces/eshkola` |
| smain | `fed-backup` | fed-backup | `/home/shectory/workspaces/infra/backup` |
| vibe | `virtual-boris` | VBoris2 | `/home/shectory/workspaces/virtual-boris` |
| vibe | `inbox` | Inbox | `/home/shectory/workspaces/inbox` |
<!-- AUTO:agents END -->

---

## 14. События за последние 24ч (AUTO)

<!-- AUTO:news BEGIN -->
*за последние 24ч новостей не было*
<!-- AUTO:news END -->

---

## 15. Бэкап федерации (FEDBACKUP)

За резервное копирование федерации отвечает агент **FEDBACKUP** (`fed-backup`, node `smain`).
Пиши ему при любом изменении, влияющем на охват бэкапа (см. «Когда писать» ниже).

### Что бэкапится
- `~/workspaces` каждого узла (репо), sanitized-конфиги, дампы БД (sqlite `.backup`, redis, poste-mail), манифесты БЕЗ значений, vscode-remote.
- Инкрементально (rsync `--link-dest`, hardlink-снапшоты), GFS 6 daily / 5 weekly / 4 monthly, на `smain`.
- Медиа/temp — одна FULL-копия, без версий.
- Последний снапшот шифруется (gpg AES-256, пароль `BACKUP_ZIP_PASS` из Keymaster) и уходит offsite в Google Drive (`BACKUP_URL`).
- Скрипт и DR-ранбук: `smain:~/workspaces/infra/backup/{federation-backup.sh, RESTORE_PROMPT.md}`.

### Чего в бэкапе НЕТ (сознательно, §7)
Сырых LLM-ключей, паролей БД/почты/GitHub, приватных ssh-ключей, `.env`, `openclaw.json`, `.keymaster`.
При восстановлении секреты пере-провижинятся через Keymaster (см. RESTORE_PROMPT.md).

### Что исключается как регенерируемое
`node_modules`, `venv`, `build`/`dist`/`target`, кеши, SDK и всё, что качается с сети производителя (архивы/инсталляторы).

### Когда писать FEDBACKUP (mandatory)
Немедленно сообщай FEDBACKUP, если у тебя:
- **arch-change** — новый сервис/БД/том/путь данных, переезд репо, смена стораджа;
- **backup-gap** — заметил, что что-то важное НЕ попадает в бэкап;
- **new-resource** — появился новый ресурс, требующий бэкапа (БД, стор, загруженный контент, том docker).

### Как писать (прямая доставка в inbox FEDBACKUP)
```
POST http://10.66.0.1:9090/api/agent/fed-backup/message?from=<agent_id>
Content-Type: text/plain
Body:  news event=backup-gap
       ts=<YYYY-MM-DD HH:MM MSK>
       path=<абс.путь>
       what=<что>
       why=<зачем бэкапить>
       node=<где>
```

`event` = `backup-arch-change` | `backup-gap` | `backup-new-resource`.

FEDBACKUP поллит свой файловый inbox `~/.federation-inbox/fed-backup/inbox.jsonl` на `smain`, забирает эти события и расширяет охват. **Что не сообщено FEDBACKUP — не бэкапится.**

Note: `message` можно слать и в query (`?message=<url-encoded>`) — но news-payload обычно длинные, лучше через body. Оба варианта поддерживаются с 2026-07-25.

## 16. SMS-шлюз (единый канал критичных SMS-алертов)

За доставку SMS отвечает **Android-шлюз в LAN** `shevbo-pi` (`192.168.1.128:8080`, приложение SMS Gateway в Local Server mode, стационарный ethernet 100Мбит, активная SIM с балансом). Владелец сервиса — Klod-Access.

### Когда использовать
- Критичные alert Боре, где ТГ/email могут быть заблокированы (роуминг, no-internet, полёт)
- OTP на регистрацию/логин (garden-manager-app — приоритет)
- Любое сообщение, где нужно подтверждение доставки на GSM-канал

**НЕ использовать** для массовых рассылок клиентам без согласования с Борей — SIM одна, оператор может рейт-лимитить.

### Как отправить (агент на smain)
```bash
/home/shectory/bin/send-sms.sh "+7XXXXXXXXXX" "текст сообщения"
# exit 0 = Delivered (подтверждён GSM-оператором)
# exit 1 = failed / auth error / no creds
# exit 2 = timeout 90с (Pending слишком долго)
# audit: ~/logs/sms/audit.jsonl
```

### Как отправить (агент не на smain — sdev/vibe/hoster)
```bash
ssh smain '/home/shectory/bin/send-sms.sh "+7XXXXXXXXXX" "текст"'
```

### Приоритет миграции
- **stl** (stl-morning-sms.sh, stl-watchdog.sh) — переведён 2026-08-05
- **garden-manager-app** — `src/lib/sms.ts` (SMS-OTP) должен уйти со стороннего провайдера на этот шлюз
- Все прочие — по мере появления SMS-потребности

### Мониторинг здоровья
`sms-gateway-doctor.sh` (cron */5 на smain) следит за `/health`, Basic Auth, счётчиком `messages:failed`, батареей. Алерт в ТГ Боре с дедупом 30 мин. Журнал: `~/logs/sms/doctor.jsonl`.

### FAQ для агентов
- **«Мне надо SMS в другой номер»** — просто передай его первым аргументом
- **«Мне нужен fallback если SMS не дошёл»** — вызывающий сам решает: exit != 0 → send_tg("SMS не доставлена, ...") или другой канал
- **«Как получить креды напрямую»** — не надо, всегда через `send-sms.sh`. Библиотека сама берёт из Keymaster (`smsgateway_*`)

---

— Klod-Access
