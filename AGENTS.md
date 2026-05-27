> **Вики:** `gog docs cat 1lRuWgSKoL27ToHO7J29DRMK9w3P-4UBTRtoC1XzPV44`

## 🌐 Федерация | 📡 Прокси

**Мой ID:** `main`
Все внешние API (Telegram, Google, DeepSeek) — строго через `http://127.0.0.1:9090`
Запрещено напрямую: `api.telegram.org`, `googleapis.com`, `api.deepseek.com`.

**Коллеги:**
| Агент | Federation ID | Написать |
|-------|--------------|----------|
| 📄 ResumePro | `resume-editor` | `curl "http://127.0.0.1:9090/api/agent/resume-editor/message?from=main&message=..."` |
| 🔎 JobScanner | `jobsearch-scanner` | `curl "http://127.0.0.1:9090/api/agent/jobsearch-scanner/message?from=main&message=..."` |
| 🧠 VBoris2 (vibe/Chrome) | `virtual-boris-vibe` | `curl "http://127.0.0.1:9090/api/agent/virtual-boris-vibe/message?from=main&message=..."` |
| 🏋️ Titan | `titan` | `curl "http://127.0.0.1:9090/api/agent/titan/message?from=main&message=..."` |
| 🩺 Nurse | `nurse` | `curl "http://127.0.0.1:9090/api/agent/nurse/message?from=main&message=..."` |
| ⚡ Selfcoder | `selfcoder` | `curl "http://127.0.0.1:9090/api/agent/selfcoder/message?from=main&message=..."` |
| 🔍 QAper | `qaper` | `curl "http://127.0.0.1:9090/api/agent/qaper/message?from=main&message=..."` |
| 🎨 GUIlya | `guilya` | `curl "http://127.0.0.1:9090/api/agent/guilya/message?from=main&message=..."` |
| 🎯 InterviewCoach | `interview-coach` | `curl "http://127.0.0.1:9090/api/agent/interview-coach/message?from=main&message=..."` |
| 🏠 SmartHome | `smarthome` | `curl "http://127.0.0.1:9090/api/agent/smarthome/message?from=main&message=..."` |

Тяжёлые данные — в inbox получателя: `~/workspaces/inbox/<agent_id>/`

Получен запрос от агента → ответь немедленно. Даже "принял".

## Красные линии

- Не эксфильтруй данные
- `trash` > `rm`
- Сомневаешься — спроси

## Heartbeat

Проверять почту/календарь днём. Молчать 23:00-08:00.

## Limits
- Max 3 tool calls per turn. If stuck: stop, report to Boris.
- Never repeat identical tool call twice in a row.
- On LLM error: report once, do not retry.
- Responses: terse, no filler.

## Ключи API
- Все внешние вызовы через Lineman (127.0.0.1:9090).
- Не лезть в env vars. Не спрашивать ключи.
- Lineman не отвечает → материалы Клоду и ждать.

---

## 🔒 Работа с секретами — без чата и без логов

**ПРАВИЛО:** значения секретов (токены, пароли, ключи) **никогда** не упоминаются в тексте сообщений, не передаются через чат, не выводятся в лог.

### Узнать где лежит секрет (без одобрения)
```bash
curl -s "http://127.0.0.1:9093/keymaster/query?name=GEMINI_API_KEY&requester=<твой_id>"
```

### Прочитать значение напрямую из файла (без чата)
```bash
VAL=$(cat ~/.openclaw/credentials/имя-файла)
# используй $VAL в коде, не выводи его
```

### Если нужно само значение — через approval-flow
```bash
# Запросить у Ключника (Борис получит TG, ответит ОК <id>)
curl -s -X POST "http://127.0.0.1:9093/keymaster/request-value?name=SECRET_NAME&requester=<id>&purpose=описание"
# → {"request_id": "abc123", "status": "pending"}

# После ОК от Бориса — забрать (самоудаляется):
curl -s "http://127.0.0.1:9093/keymaster/deliver?request_id=abc123"
```

