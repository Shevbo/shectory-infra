# InterviewCoach v2 — Refactor Design

**Date:** 2026-05-29
**Author:** Claude (Executive Advisor) + Boris
**Project:** `~/workspaces/interview-coach`
**Status:** Approved for implementation

## Problem

Inцидент 27-29.05 с подготовкой и разбором интервью с Salmon показал хронические сбои interview-coach:

1. **Утечка протокола в чат** — `<tool_code>print(default_api.web_search(...))`, `Brining...`, `🧾 Session History`, `🧰 Process: running` уходят пользователю как текст.
2. **Зависания на часы** — `web_search` без таймаута («ищу 5 часов»), эскалация к Клоду висит сутки на 403.
3. **Не выполнено базовое задание** — на просьбу «как сграбить запись Teams 18:00» ответа не было вообще.
4. **Скачивание не-того файла** — Cloud Mail.ru вернул HTML-заглушку 16KB, Coach уверенно отчитался «это не запись интервью».
5. **Цикл извинений** — 15 одинаковых сообщений за 12 минут (29.05 10:51–11:03).
6. **Путаница контекста** — после ссылки Google Drive отвечает советом про mail.ru.
7. **Confidence theatre** — десятки «понял, запускаю» без единого результата.

**Корневая причина:** LLM-driven media handling без playbook + flash-модель без reasoning + отсутствие outbound dedup + сломанный escalation канал к Клоду (на момент инцидента 27.05; сейчас починен, но требует страховки).

## Scope

**В скоупе:**
1. Новый `process_media.py` — детерминированный playbook для media-задач (detect → download → validate → parse → analyze).
2. Validation gate: magic bytes + size + duration. Фикс инцидента с 16KB HTML.
3. Новый `escalate.sh` — multi-channel эскалация (ask-claude → inbox → TG alert).
4. Переписанный AGENTS.md для Coach: result-only, banned phrases, запрет на собственные downloads.
5. Смена модели Coach: `deepseek-v4-flash` → `deepseek-v4-pro` (fallback `gemini-2.5-pro`).
6. Ограничение tools (если поддерживается): запрет `web_search`, `wget`, `curl` к внешним URL.
7. Outbound sanitizer (prompt-level) против утечек `<tool_code>` / служебных строк.
8. Tests: unit на providers/validators/full flow + manual E2E smoke на Salmon-файле.

**Не в скоупе (явный YAGNI):**
- Mock-интервью / разведка компании / разбор вопросов — режимы работают нормально, **не трогаем**.
- `parse_voice.py` — не меняем, только обёртка.
- Общий escalation framework для всех агентов (ResumePro/Titan/Nurse/VBoris) — это Phase 2 после стабилизации Coach.
- Web search как источник информации — отрубаем как причину зависаний; знание берётся из LLM или эскалируется к Клоду.
- Поддержка новых файлообменников (только то, что уже есть: GDrive, Mail.ru, Yandex.Disk, Dropbox, OneDrive, Telegram, direct URL).

## Architecture

```
┌────────────────────────────────────────────────────┐
│ Telegram (Boris) — @shectory_interview_bot          │
└─────┬───────────────────────────────────────▲──────┘
      │ media / text                          │ ≤2 messages per task
      ▼                                       │
┌────────────────────────────────────────────────────┐
│ interview-coach (deepseek-v4-pro thinking=high)     │
│  • LLM-обёртка                                      │
│  • outbound sanitizer (prompt + post-filter)        │
└─────┬──────────────────────────▲────────────▲──────┘
      │ subprocess               │ JSON       │
      ▼                          │ stdout     │
┌─────────────────────┐  ┌───────┴──────┐  ┌──┴──────────────┐
│ process_media.py    │  │ voice-parser │  │ escalate.sh     │
│ (NEW)               │  │ (existing,   │  │ (NEW)           │
│ state machine       │  │ unchanged)   │  │ ask-claude →    │
│ detect+dl+validate+ ├─▶│ parse_voice  │  │ inbox →         │
│ parse+analyze       │  │ Gemini       │  │ TG alert        │
└─────────────────────┘  └──────────────┘  └─────────────────┘
```

## Components

### 1. `~/skills/voice-parser/scripts/process_media.py` (NEW, ~250 LOC)

Точка входа для всех media-задач Coach.

**Usage:**
```bash
python3 process_media.py <url-or-path> [--mode=interview|monologue|transcribe] [--out=path]
```

**Output (stable JSON to stdout):**
```json
{
  "status": "ok",
  "stage": "analyzed",
  "provider": "gdrive",
  "file_path": "/home/shectory/.openclaw/media/inbound/<uuid>.mp4",
  "size_bytes": 215443212,
  "duration_seconds": 1842,
  "mime": "video/mp4",
  "transcript_path": "/home/shectory/.openclaw/media/transcripts/<uuid>.md",
  "summary": "Первые 200 симв транскрипта",
  "reason": null,
  "should_escalate": false
}
```

State machine: `init → detected → downloaded → validated → parsed → analyzed → done` (или `failed` на любом шаге с конкретным `reason` и `should_escalate`).

**Provider detection** (regex):

| Provider | URL pattern | Downloader |
|---|---|---|
| `gdrive` | `drive.google.com/file/d/(\w+)` или `?id=(\w+)` | `https://drive.google.com/uc?export=download&id=<ID>&confirm=t` (публичный, без OAuth) |
| `mailru` | `cloud.mail.ru/public/(\w+)/(.+)` | существующий из `0bd3e72` |
| `yadisk` | `disk.yandex.ru/d/` или `yadi.sk/d/` | существующий |
| `dropbox` | `dropbox.com/s/` | existing, `?dl=1` |
| `onedrive` | `1drv.ms` или `onedrive.live.com` | existing |
| `telegram` | `[file_id:...]` или `[media attached:...]` | parse from prompt context |
| `direct` | всё остальное | `requests.get` через Lineman |

**Validation gate (фикс главного бага):**
- `python-magic` или `file --mime-type` → должно быть `audio/*` или `video/*`
- `os.path.getsize` ≥ 100 KB
- `ffprobe -v error -show_entries format=duration` ≥ 30 сек (warning если <30, не fail)
- Если mime = `text/html` → **fail** с `reason="downloaded HTML page instead of media (likely needs login or wrong URL)"`, `should_escalate=true`

**Парсинг:** делегируем существующему `parse_voice.py` через **import** (`from parse_voice import parse_audio`), не через subprocess — даёт прямой доступ к structured result и упрощает тестирование. Mode = `interview` по умолчанию для Coach.

**Анализ:** parse_voice уже даёт interview-разбор по своим промптам. process_media принимает результат и собирает финальный JSON.

### 2. `~/scripts/escalate.sh` (NEW, ~50 LOC)

Multi-channel эскалация с fallback.

**Usage:**
```bash
~/scripts/escalate.sh <agent_id> "<question>" [context_file]
```

**Логика:**
1. `ask-claude.sh "<question>" [context]` с таймаутом 30с. На успех — печатает ответ и exit 0.
2. На fail (timeout/non-zero) — пишет `~/workspaces/claude-inbox/TASK_$(date +%s)_<AGENT>.md` с body = question + context, exit 0 (без ответа).
3. Если inbox недоступен (write fail) — `curl -X POST http://127.0.0.1:9090/api/tg/send` с alert «Эскалация <agent_id> не прошла». Exit 1.
4. **Дедуп:** если sha256(question) уже эскалировалось за последние 60 минут (state file `~/.cache/escalate-recent.json`) — skip, exit 0.

### 3. `~/workspaces/interview-coach/AGENTS.md` (REWRITE)

Target size: 6-7 KB (с запасом до 12 KB лимита).

Структура:
- **Кто я** (5 строк) — InterviewCoach, готовит к C-level интервью
- **Профиль Бориса** (ссылка на `~/workspaces/resume-editor/boris-profile.md`)
- **Правило #1 — Media** (явное): любой URL/file_id/media → один вызов `process_media.py`. Coach не делает `wget`/`curl`/собственного download.
- **Правило #2 — Verbosity (result-only)**: на задачу ≤2 сообщения. Первое — старт («Запускаю разбор, жди 2-3 мин»). Второе — результат или ошибка. Точка.
- **Правило #3 — Banned phrases** (явный список): «понял», «сорян», «разбираюсь», «бегу», «погнали», «секундочку», «сейчас», «давай ещё раз», «извини», «прости», «моя ошибка», «попробую снова». Эти слова **запрещены** в исходящих.
- **Правило #4 — No cycles**: одна попытка любого инструмента, fail → эскалация, не retry.
- **Режимы работы** (mock / разведка / разбор) — сохраняем как есть.
- **Эскалация** — один способ: `~/scripts/escalate.sh interview-coach "<вопрос>"`.

### 4. Coach model config (openclaw.json)

```json
{
  "id": "interview-coach",
  "model": {
    "primary": "deepseek/deepseek-v4-pro",
    "fallbacks": ["google/gemini-2.5-pro"],
    "thinking": "high"
  },
  // "thinking: high" применяется провайдером если поддерживается
  // (gemini-2.5-pro имеет thinking; deepseek-v4-pro — reasoning model по умолчанию)
  // если поле игнорируется — это безопасный no-op
  "tools": {
    "deny": ["web_search"]
  }
}
```

(Если `tools.deny` не поддерживается gateway — запрет реализуется через prompt-rules в AGENTS.md.)

### 5. Outbound sanitizer

**Уровень AGENTS.md prompt:**

```
Перед отправкой ЛЮБОГО сообщения проверяй текст. Если в нём есть:
  • <tool_code>, default_api., print(, ```python
  • Brining..., 🧾 Session History, 🧰 Process:
  • [media attached:, [file_id:
→ удали эти куски ИЛИ вообще не отправляй.

Если после очистки текст короче 5 символов — не отправляй.
```

Это soft защита (LLM может проигнорить). Hard защита — `process_media.py` возвращает структурированный результат, у Coach нет повода генерировать tool_code в выводе.

## Data flow

### Сценарий 1 — Media (URL / file_id / attachment)

1. Coach получает сообщение → одно исходящее: `"Запускаю разбор интервью. Жди 2-3 минуты."`
2. Coach вызывает: `python3 ~/skills/voice-parser/scripts/process_media.py "<url>" --mode=interview`
3. Subprocess timeout = 300 секунд (5 минут).
4. На stdout — JSON. Coach парсит:
   - `status=ok` → формирует второе сообщение:
     ```
     ✅ Разбор готов
     📝 Транскрипт: <первые 200 симв>...
     💪 Сильно: <2-3 пункта из summary>
     ⚠️ Улучшить: <2-3 пункта>
     🎯 Следующий шаг: <конкретно>
     ```
   - `status=failed` + `should_escalate=true` → `escalate.sh interview-coach "<reason>"`, второе сообщение: `"❌ <reason>. Передал Клоду."`
   - `status=failed` + `should_escalate=false` → второе сообщение: `"❌ <reason>. <конкретный совет: перезалей в TG напрямую и т.д.>"`
5. Subprocess crash (exit code != 0, stdout empty) → как failed + escalate.
6. Subprocess timeout → kill -9, как failed + escalate с reason `"process_media timed out after 5 min"`.

### Сценарий 2 — Text (mock, разведка, вопрос)

Coach работает LLM-only по существующим режимам. Outbound sanitizer применяется. **Не вызывает** `process_media.py`.

### Сценарий 3 — Text про media без URL

Например: «Как записать Teams завтра?» Coach отвечает из LLM-знаний (Stream / OBS / Camtasia / Riverside) — без `web_search`. Если реально нужны актуальные данные → один `escalate.sh interview-coach "<question>"` к Клоду.

## Error handling

### process_media.py (Python level)

| Стадия | Ошибка | Действие | should_escalate |
|---|---|---|---|
| detect | unknown provider | `failed`, `reason="unsupported host: <domain>"` | true |
| download | HTTP 403/404 | retry 1 раз с другим UA, потом fail | true |
| download | timeout (>120s для 200MB) | abort, fail | true |
| download | size = 0 или <1 KB | fail `"empty download, likely auth required"` | true |
| validate | mime не audio/video | fail `"downloaded non-media: <mime>"` | true |
| validate | size < 100 KB | fail `"file too small: <N> bytes"` | true |
| validate | duration < 30s | warning, продолжаем | false |
| parse | Gemini 5xx | retry 2 раза exponential backoff | false |
| parse | Gemini quota | fail `"gemini quota exceeded"` | true |
| any | unexpected exception | log traceback в `~/logs/process_media.log`, return failed | true |

### Coach (LLM level)

- exit code ≠ 0 + stdout пуст → `escalate.sh` + сообщение Боре «Передал Клоду»
- timeout >5 минут → kill процесса + та же эскалация
- любая ошибка от tool → одна попытка эскалации, **без retry того же tool**

### escalate.sh

- ask-claude.sh fail (timeout 30c / non-zero) → step 2 (inbox)
- inbox write fail → step 3 (TG alert)
- TG send fail → log + exit 1 (Coach сам уведомит Борю)
- dedup hash 60 минут

## Testing

### Unit (pytest)

`~/skills/voice-parser/tests/`:
- `test_process_media.py` — провайдеры + полный flow с mocked HTTP (`responses`)
- `test_validators.py` — magic bytes / size / duration
- `test_providers.py` — detection per URL pattern

Фикстуры:
- `fake_html_as_media.html` — 16 KB HTML, симулирует Mail.ru заглушку
- `real_audio_small.mp3` — 100 KB валидный mp3 (синтез `ffmpeg -f lavfi -i sine`)
- `real_video_small.mp4` — 200 KB валидное видео
- `gdrive_response.html`, `mailru_response.json`, `yadisk_redirect.txt` — captured responses

**Обязательные тесты:**
- `test_detect_provider_gdrive` / `_mailru` / `_unknown`
- `test_validate_rejects_html` — фикстура 16KB HTML → status=failed, reason содержит "non-media"
- `test_validate_rejects_tiny` — 500 байт → failed "too small"
- `test_validate_accepts_real_audio` — fixture mp3 → ok
- `test_full_flow_local_file` — путь к real_audio_small.mp3 → parsed
- `test_failed_download_returns_json` — mock 403 → status=failed, should_escalate=true, валидный JSON на stdout
- `test_gdrive_public_download_uc_endpoint` — mock на `uc?export=download&id=<ID>` → returns bytes

**escalate.sh tests** (bash, mock каналы через переопределение PATH):
- `test_ask_claude_success` — успех на step 1
- `test_inbox_fallback_when_ask_claude_fails` — step 1 fail → step 2 ok
- `test_tg_alert_when_inbox_fails` — оба упали → TG
- `test_dedup_within_60min` — повтор того же hash → skip

### Manual E2E smoke

1. **process_media.py на Salmon-файле** (тот самый GDrive из инцидента):
   ```bash
   python3 ~/skills/voice-parser/scripts/process_media.py \
       "https://drive.google.com/file/d/1f3uPuKuY5selelkxvVzjiFtY3SoYOMyc/view?usp=drive_link" \
       --mode=interview
   ```
   Ожидаем: JSON с `status=ok`, `transcript_path` существует, `summary` непустой.

2. **escalate.sh ping:**
   ```bash
   ~/scripts/escalate.sh interview-coach "test ping respond OK"
   ```
   В течение 30с — ответ Клода в stdout.

3. **Coach E2E:** после restart gateway Боря шлёт Coach сообщение «привет, тестовая фраза» → ровно одно сообщение в ответ, без `<tool_code>`, без banned-фраз.

4. **Coach media E2E:** Боря шлёт Salmon-ссылку → 2 сообщения: «Запускаю разбор» + результат с транскриптом.

## Rollout

1. Ветка `feat/interview-coach-v2` от `/home/shectory` (репо ~).
2. Создать `process_media.py` TDD-стилем (тест → код → тест зелёный → коммит).
3. Реализовать GDrive public-download fix в `process_media.py` (НЕ через OAuth, через `uc?export=download&id=`).
4. Создать `escalate.sh` TDD-стилем.
5. Переписать AGENTS.md.
6. Обновить `openclaw.json`: model + `tools.deny`.
7. Restart `openclaw-gateway.service`.
8. Прогнать manual E2E smoke (4 шага выше).
9. Сообщить Боре «Coach v2 готов, протестируй».
10. Один день мониторинга. Если ок — merge в master, push.

## Rollback

`git revert <merge-commit>` + восстановить `model.primary=deepseek-v4-flash` в `openclaw.json` + restart gateway. Старый AGENTS.md в git history. `process_media.py` остаётся как опциональный (Coach просто не зовёт его).

## Метрики успеха (через 1 неделю)

- Сообщений Coach на одну media-задачу: было 15-30, цель ≤3.
- Время от media → результат: было ∞ (не доехало), цель ≤4 минуты для 200 MB AVI.
- Циклов извинений: 0.
- Утечек `<tool_code>` / служебных строк: 0.

## Open questions

None at spec-approval time.
