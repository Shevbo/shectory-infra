# Censor Autopilot — Design Spec
Date: 2026-05-26

## Problem

Lineman-прокси фиксирует аномалии LLM-агентов: петли ретраев, бесконтрольный рост контекста, расточительные токены. Текущий Censor только _отчитывается_ раз в 30 мин. Аномалии живут и тратят деньги пока никто не смотрит.

Пример: 2026-05-26 07:00-07:30 — OpenClaw personal assistant на smain сделал 154 запроса с одинаковым 69KB контекстом, потратив 2.76M токенов впустую. Retry rate 76%.

## Цель

Система сама обнаруживает аномалию, находит root cause через Claude Opus, применяет фикс, делает git commit и сообщает Борису в Telegram.

---

## Архитектура

```
[Lineman DB] → [censor_exporter daemon] → [~/logs/censor/YYYY-MM-DD.jsonl]
                                                    ↓
                               [censor_watchdog.py] ← cron */10 * * * *
                                        ↓ аномалия!
                               [censor_investigator.py]
                                        ↓
                               тянет request_body из Lineman DB
                               читает конфиги: openclaw, lineman, pm2
                                        ↓
                               [Claude Opus API]
                                        ↓
                               structured JSON: root_cause + patches[]
                                        ↓
                               [patch_applier.py] → файлы → git commit
                                        ↓
                               ~/logs/censor/fixes.jsonl (KPI до/после)
                                        ↓
                               Telegram: "Починил X, вот diff"
```

Существующий `censor_analyzer.py` продолжает работать параллельно, но с новым расписанием: раз в 6 часов (сводный отчёт).

---

## Компоненты

### 1. `censor_watchdog.py`

Запускается cron `*/10 * * * *`. Быстрый — читает только последние 10 мин JSONL, считает метрики по агентам. Если ни один порог не превышен — выходит без действий (0 токенов потрачено).

**Пороги срабатывания (хотя бы один):**

| Метрика | Порог |
|---------|-------|
| retry_rate у агента | > 50% за окно |
| session_tokens у агента | > 200K за окно |
| error_rate у агента | > 25% за окно |
| tokens_in от агента | > 800K за 10 мин |

**Дедупликация:** если для агента уже запущено расследование (есть запись в `active_investigations.json` моложе 30 мин) — пропустить.

При срабатывании: вызвать `censor_investigator.py --agent <key> --since <ts>`.

---

### 2. `censor_investigator.py`

Вызывается watchdog. Делает три шага:

**Шаг 1 — Сбор доказательств:**
- Из Lineman DB: последние 20 request_body проблемного агента (полные тела, не truncated)
- Метрики аномалии: retry_rate, token count, timing
- Diff между первым и последним телом запроса (что изменилось, если что-то)

**Шаг 2 — Сбор конфигов:**

Читает всё что может быть причиной (полные файлы):
- `~/.openclaw/agents/*/agent/config.json`
- `~/.openclaw/agents/*/agent/system-prompt.md` (или аналог)
- `~/.openclaw/agents/*/agent/auth-profiles.json` (без значений ключей — только структура)
- `~/.openclaw/openclaw.json` (модели, провайдеры — без ключей)
- `~/workspaces/infra/lineman/config.json`
- `~/.pm2/dump.pm2` (список процессов)

**Шаг 3 — Вызов Opus:**

Промпт содержит: метрики аномалии + тела запросов + конфиги.

Opus возвращает строго JSON:

```json
{
  "root_cause": "Описание причины петли (1-3 предложения)",
  "severity": "critical|high|medium",
  "patches": [
    {
      "file": "/absolute/path/to/file",
      "description": "Что меняем и почему",
      "type": "json_key|text_replace|file_append",
      "old": "старое значение или строка",
      "new": "новое значение или строка"
    }
  ],
  "restart_pm2": ["process-name-if-needed"],
  "expected_improvement": "retry_rate: 76% → <5%, экономия ~2.5M токенов/час"
}
```

Если Opus не может найти однозначную причину — возвращает `patches: []` и описание в `root_cause`. В этом случае система только отправляет аналитику в Telegram без правок.

---

### 3. `patch_applier.py`

Получает структуру от Opus. Для каждого патча:

1. Создать backup: `{file}.censor-backup-{timestamp}`
2. Применить изменение по типу:
   - `json_key` — загрузить JSON, найти ключ по пути, заменить, сохранить
   - `text_replace` — str.replace(old, new) в тексте файла
   - `file_append` — дописать строку в конец
3. Если файл JSON — validate после правки. При невалидном JSON — откатить из backup.
4. Если `restart_pm2` не пустой — выполнить `pm2 restart <name>` через start.sh окружение.

После всех патчей:
```bash
git add <changed_files>
git commit -m "censor-autopilot: fix <agent> — <root_cause_short>\n\nMetrics before: retry=76%, tokens=2.7M/30min\nExpected after: <expected_improvement>"
```

Результат пишется в `~/logs/censor/fixes.jsonl`:
```json
{
  "ts": "2026-05-26T07:45:00Z",
  "agent": "smain:?",
  "root_cause": "...",
  "patches_applied": 2,
  "files_changed": [...],
  "commit": "abc1234",
  "metrics_before": {"retry_rate": 0.76, "tokens_per_10min": 2700000},
  "metrics_after": null
}
```

`metrics_after` заполняется при следующем прогоне watchdog для этого агента (через 10-20 мин).

---

### 4. Изменения в `censor_analyzer.py`

- `WINDOW_MINUTES`: 30 → 360
- Crontab: `*/30 * * * *` → `0 */6 * * *`
- Заголовок отчёта обновить на "last 6h"

---

### 5. Telegram-уведомление

**При срабатывании (аномалия найдена, фикс применён):**
```
[Autopilot] Аномалия: smain:? retry=76% (2.7M tok/30min)
Root cause: OpenClaw agent — нет exit condition при tool_call failure
Исправил:
  ~/.openclaw/agents/main/agent/config.json
    max_iterations: null → 15
  ~/.openclaw/agents/main/agent/config.json
    tool_error_exit: false → true
Коммит: abc1234
Ожидаемо: retry_rate 76% → <5%
```

**При аномалии без чёткого фикса:**
```
[Autopilot] Аномалия: smain:? retry=76% (2.7M tok/30min)
Opus: [описание root cause]
Автофикс не применён — причина неоднозначна.
Требует ручного разбора: ~/logs/censor/reports/...
```

**6-часовой отчёт (из analyzer):**
```
Censor 12:00 (6h)
Запросов: 2400 | Tokens in: 45M
  smain:?: 38M tok [retries:12 growth:3x]
  sdev:coder: 5M tok [ok]
...
[краткий анализ DeepSeek]
```

---

## Файловая структура

```
~/workspaces/infra/censor/
  censor_exporter.py      — существующий, не трогать
  censor_analyzer.py      — изменить: 360 мин, cron 6h
  censor_watchdog.py      — новый
  censor_investigator.py  — новый
  patch_applier.py        — новый
  active_investigations.json  — runtime state (дедуп)
  state.json              — существующий
~/logs/censor/
  fixes.jsonl             — новый: KPI трекинг фиксов
  reports/                — существующий
```

---

## Модели

- **Watchdog**: без LLM (только арифметика)
- **Investigator**: Claude Opus (claude-opus-4-7) — только при аномалии
- **Analyzer**: DeepSeek Pro — каждые 6 часов

Opus вызывается через Lineman: `POST http://localhost:9090/proxy/anthropic/v1/messages` — нужно добавить anthropic в Lineman providers, либо вызывать напрямую через Anthropic SDK с ключом из openclaw.json.

---

## KPI Success Criteria

- `retry_rate` проблемного агента падает до < 10% в течение 2 прогонов watchdog после фикса
- Суммарный `tokens_in` за день не растёт неконтролируемо (трекинг в fixes.jsonl)
- Ни один агент не тратит > 1M токенов/час без явного основания
