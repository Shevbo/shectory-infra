# Shectory Portal — Единая система моделей + агент-аналог на OpenClaw

Дата: 2026-06-19
Статус: design, утверждён контур (Боря: «ОК» 2026-06-19)
Кодовая база: `~/workspaces/projects/CursorRPA/shectory-portal` (LIVE-портал, БД `project_shectory_portal`), Lineman `~/workspaces/infra/lineman`, OpenClaw `~/.openclaw/openclaw.json`

## Контекст и проблема

Портальный чат проекта сейчас работает через cursor-agent CLI (backend `cursor_cli`, дефолт-модель `gemini-3-flash`) с паттерном executor+auditor. Выбор моделей разрознен:
- Провайдеры в таблице `model_providers` (anthropic, deepseek, gemini, ollama, openai, openrouter), пер-проектные модели в `project_models` (с флагом `use_proxy`, `weight`).
- Роли исполнителя/аудитора заданы плоскими ключами в `portal_settings`: `SHECTORY_EXECUTOR_BACKEND`, `SHECTORY_EXECUTOR_AGENT_MODEL_ID`, `SHECTORY_AUDITOR_*`.
- `use_proxy` гонит трафик через **захардкоженный BrightData-прокси** (`src/lib/proxy-fetch.ts`, секреты прямо в коде) — нарушение политики «секреты только у Ключника» и политики «LLM строго через Lineman».
- LM Studio как провайдер отсутствует.

Нужно: единый каталог моделей, выбор моделей в настройках по двум ролям **chat** и **think**, весь LLM-трафик строго через Lineman, и агент-аналог cursor-agent на pro-моделях через Lineman (cursor_cli — запарковать).

## Цели

1. Полный каталог моделей всех провайдеров, маршрут только через Lineman.
2. Две именованные роли `chat` и `think`, назначаемые в `/settings`, применяемые во всех точках LLM-вызова.
3. Агент-исполнитель проекта работает через OpenClaw на pro-моделях (gemini-3.1-pro primary, deepseek-v4-pro fallback) с родными tools/skills/MCP, трафик через Lineman.
4. `cursor_cli` сохранён как запаркованная (не дефолтная) опция backend.
5. Удалить BrightData и любые секреты из кода портала.

## Не-цели (YAGNI)

- OAuth Claude-подписки через Lineman (исследовано 2026-06-19: ToS-риск бана аккаунта, отклонено).
- Claude как дефолтный агент (дорого; модели Claude остаются в каталоге как опция роли).
- Переписывание системы аудитора/очереди/чеклистов — переиспользуем как есть.
- Стриминг токенов от OpenClaw в UI (этап 2, если понадобится).

---

## Subsystem A — Каталог моделей и роли chat/think через Lineman

### A1. Каталог моделей

Решение: каталог — **константа в коде** `src/lib/model-catalog.ts` (массив `{provider, modelId, label, tier}`), без новой таблицы. Провайдеры уже есть в `model_providers`; добавляется только строка `lm-studio` (baseUrl — Lineman-маршрут `lm-studio`, без apiKeyRef, локальный). Роли (A2) и backend хранят строки provider+model_id, валидируемые против каталога. Это убирает миграцию каталога и риск рассинхрона БД.

Полный каталог:

| Провайдер | model_id | Лейбл |
|-----------|----------|-------|
| gemini | gemini-2.5-flash | Gemini 2.5 Flash |
| gemini | gemini-3.0-flash | Gemini 3.0 Flash |
| gemini | gemini-2.5-pro | Gemini 2.5 Pro |
| gemini | gemini-3.1-pro-preview | Gemini 3.1 Pro |
| deepseek | deepseek-chat | DeepSeek Flash (chat) |
| deepseek | deepseek-reasoner | DeepSeek Pro (reasoner) |
| anthropic | claude-haiku-4-5-20251001 | Claude Haiku 4.5 |
| anthropic | claude-sonnet-4-6 | Claude Sonnet 4.6 |
| anthropic | claude-opus-4-8 | Claude Opus 4.8 |
| lm-studio | qwen3.5-9b | Qwen 3.5 9B (local) |
| lm-studio | deepseek-r1-14b | DeepSeek R1 14B (local) |
| lm-studio | gemma-4-26b | Gemma 4 26B (local) |

Точные model_id LM Studio и deepseek-pro сверяются с Lineman `config.json` и `klod_ask.py MODEL_PRESETS` на этапе реализации (не угадывать).

### A2. Роли chat / think

Новые ключи в `portal_settings` (реестр в `src/lib/portal-settings-registry.ts`, группа `ai`):
- `ROLE_CHAT_PROVIDER`, `ROLE_CHAT_MODEL_ID`
- `ROLE_THINK_PROVIDER`, `ROLE_THINK_MODEL_ID`

Дефолты: chat = `gemini / gemini-2.5-flash`, think = `gemini / gemini-2.5-pro`.

Хелпер `src/lib/model-roles.ts`:
```
resolveRole(role: "chat" | "think"): { provider, modelId }
```
Читает настройки, фолбэк на дефолт.

### A3. Единый LLM-клиент через Lineman

Новый `src/lib/lineman-llm.ts` — ЕДИНСТВЕННАЯ точка LLM-вызовов портала:
```
askLLM({ role | provider+modelId, prompt, maxTokens, timeoutMs }): { ok, text, model, provider, error }
```
- Зовёт `POST http://127.0.0.1:9090/api/klod/ask` `{ agent:"portal", prompt, model_hint, max_tokens }`.
- `model_hint` маппится: gemini→`gemini-flash`/`gemini-pro` пресеты или прямой provider/model; deepseek-chat→`deepseek-fast`; deepseek-reasoner→`deepseek-reason`; anthropic→`fast/normal/deep`; lm-studio→через `/proxy/lm-studio` (klod_ask пресета может не быть — добавить в Lineman, см. C1).
- Извлечение текста для reasoning-моделей (deepseek-reasoner): если `content` пуст — взять `reasoning_content` (логика на стороне Klod-gateway, см. C2).

`src/lib/proxy-fetch.ts` (BrightData) — **удаляется**. Все вызовы переводятся на `lineman-llm.ts`. Флаг `project_models.use_proxy` теряет смысл (всё через Lineman) — оставить колонку, но в UI убрать тумблер BrightData; трактовать «proxy» как «через Lineman» (всегда true де-факто).

### A4. Точки применения ролей

| Точка | Файл | Роль |
|-------|------|------|
| Аудитор реплик | `scripts/agent-chat-runner.mjs` (auditor) | think |
| Генерация инж-промпта | `src/app/api/project/backlog/[id]/generate-engineering-prompt/route.ts` | think |
| Извлечение чеклиста | `src/app/api/project/backlog/checklist/extract/route.ts` | chat |
| Тест модели | `src/app/api/admin/models/test-chat/route.ts` | (выбранная вручную) |

### A5. UI настроек

`/settings` (`src/components/PortalSettingsClient.tsx`), секция «AI/Модели»:
- Два дропдауна: «Роль chat» и «Роль think» — выбор из каталога (provider + model).
- Дропдаун backend агента: `openclaw` (дефолт) | `cursor_cli` (запаркован) | `gemini_api`.
- Убрать тумблеры BrightData proxy.

---

## Subsystem B — Агент-исполнитель на OpenClaw (pro-модели через Lineman)

### B1. Backend `openclaw`

Новое значение `SHECTORY_EXECUTOR_BACKEND = openclaw` (добавить в enum реестра). `cursor_cli` и `gemini_api` остаются в enum (запаркованы). Дефолт переключается на `openclaw`.

### B2. Per-project OpenClaw-агент

Портал управляет OpenClaw-агентами проектов так же, как уже управляет systemd-юнитами ТГ-ботов (`src/lib/project-bot.ts`). Новый `src/lib/openclaw-agent.ts`:
- `ensureProjectAgent(project)`: гарантирует запись в `~/.openclaw/openclaw.json` → `agents.list`:
  ```json
  {
    "id": "portal-<slug>",
    "name": "<project.name> (portal)",
    "workspace": "<project.workspacePath>",
    "model": { "primary": "gemini/gemini-3.1-pro-preview",
               "fallbacks": ["deepseek/deepseek-v4-pro"],
               "timeoutMs": 120000 }
  }
  ```
  primary/fallback берутся из роли chat, но переопределяются жёстким дефолтом B-агента (gemini-3.1-pro + deepseek-pro), пока пользователь не сменит.
- Hot-reload: OpenClaw подхватывает изменения `openclaw.json` сам.
- Безопасность: модель-конфиг ссылается на провайдеров, которые ходят через Lineman (openclaw.json providers.*.baseUrl → Lineman). Не дублировать секреты.

### B3. Поток чата (замена spawn cursor-agent)

`scripts/agent-chat-runner.mjs`, ветка backend=openclaw:
1. Вместо `runAgentPrompt` (spawn cursor-agent) — `POST http://127.0.0.1:9090/api/agent/portal-<slug>/message` с собранным промптом (история + чеклист + RU_TAIL), как сейчас.
2. Дождаться ответа агента (переиспользовать `src/lib/wait-agent-reply.ts` / federation Agent API семантику).
3. Записать reply в `chat_messages` (как сейчас), заменив ⏳-плейсхолдер.
4. Очередь (`processingMsgId`), аудитор (роль think), `[STEP_DONE:]`-чеклисты — без изменений.

Таймаут: `AGENT_PROMPT_TIMEOUT_MS` (есть в настройках). deepseek-pro fallback с учётом истории таймаутов — primary gemini-3.1-pro.

### B4. cursor_cli как запаркованная опция

`src/lib/agent.ts` и ветка `cursor_cli` в runner НЕ удаляются. Доступны через настройку backend. Дефолт — `openclaw`.

---

## Subsystem C — Изменения в Lineman (если нужны)

### C1. LM Studio в Klod-gateway
Если `klod_ask.py MODEL_PRESETS` не содержит lm-studio — добавить пресеты `lmstudio-qwen`, `lmstudio-r1`, `lmstudio-gemma` → provider `lm-studio`, path `/proxy/lm-studio/v1/chat/completions` (OpenAI-совместимо). Сверить с текущим `config.json` маршрутом lm-studio.

### C2. Извлечение reasoning_content
В `klod_ask.py extract_text` для deepseek: если `choices[0].message.content` пуст — вернуть `reasoning_content`. Проверить текущую реализацию (возможно уже есть).

Изменения Lineman делаются по дисциплине Lineman (pytest baseline, smoke, память). C1/C2 — низкий риск, без credentials.

---

## Модель данных (миграции Prisma)

- `model_providers`: добавить строку `lm-studio` (baseUrl, без apiKeyRef — локальный). Единственная миграция данных.
- Каталог моделей — константа в коде (A1), НЕ таблица.
- `portal_settings`: добавить ключи ролей (A2) и `openclaw` в enum backend (значения-строки, без миграции схемы — это key/value).
- Без удаления существующих таблиц/колонок (обратная совместимость).

## Обработка ошибок

- `askLLM` при не-200 от Lineman → `{ ok:false, error }`, в чат пишется явное сообщение «LLM не ответил: <причина>, проверьте Lineman».
- OpenClaw агент не отвечает в таймаут → reply-плейсхолдер заменяется на сообщение об ошибке, `processingMsgId` сбрасывается (очередь не зависает).
- Klod-gateway бюджет (per-agent) исчерпан → 429 → понятное сообщение в UI.

## Тестирование

- Unit: `model-roles.resolveRole` (дефолты, переопределения), `lineman-llm` маппинг model_hint (мок fetch).
- Integration (live, как в этой сессии): минт сессии суперадмина → прогон чата на backend=openclaw → ответ от pro-модели; тест роли think на генерации инж-промпта.
- Lineman: pytest baseline + smoke `/api/klod/ask` для каждого нового пресета.
- Регрессия: cursor_cli ветка по-прежнему работает при переключении backend.

## Решённые архитектурные вопросы

- Каталог моделей — константа в коде (A1), не таблица.
- Агент — **per-project** OpenClaw-агент (B2): workspace связан с проектом, как и per-project ТГ-боты. Общий агент отклонён: OpenClaw фиксирует workspace и модель пер-агент, общий не дал бы работу в нужном каталоге проекта и пер-проектный выбор модели.

## Открытые вопросы (сверить живьём на этапе реализации, не угадывать)

1. Точные model_id для LM Studio (qwen3.5-9b / deepseek-r1-14b / gemma-4-26b) и deepseek-pro — сверить с `lineman/config.json` и `klod_ask.py`.
2. Поддерживает ли Klod-gateway уже lm-studio и извлечение `reasoning_content` (C1/C2) — проверить текущий код Lineman перед правками.
3. Формат федеративного Agent API ответа (`POST /api/agent/{id}/message`) и как `wait-agent-reply.ts` его читает — сверить перед заменой spawn.
