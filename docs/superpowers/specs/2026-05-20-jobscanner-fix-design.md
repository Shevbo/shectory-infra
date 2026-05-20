# JobScanner Fix — Design Spec

**Date:** 2026-05-20
**Sprint:** Boris_Sprints/Sprint_01, блок 1

## Problem

JobScanner cron jobs (06:00 и 17:00 MSK) падают и отключены. Три корневые причины:

1. `TOOLS.md` направляет агента на `scan.py` — старый скрипт с мёртвым хардкоженым прокси
2. После ошибок оба cron job отключены (`enabled: false`) вручную OpenClaw
3. `TOOLS.md` содержит hardcoded proxy credentials — нарушение security protocol

Дополнительный симптом: последняя ошибка `"Google Generative AI API error (404)"` — возможен неверный Google baseUrl в конфигурации агента.

## Scope

**Включено:**
- Исправить TOOLS.md (скрипт, убрать прокси)
- Проверить Google baseUrl для jobsearch-scanner
- Dry-run scan_v4.py
- Включить оба cron job

**Не включено:** рефактор scan_v4.py, изменение модели, логики доставки отчётов

## Design

### 1. TOOLS.md — исправить точку входа

Заменить `scan.py` на `bash run_scan.sh` как единственную команду запуска.
`run_scan.sh` уже делает `unset http_proxy/https_proxy` + `exec python3 scan_v4.py`.

Удалить секцию `## Прокси` (строка `http://g3FLjE:v5aJS3@...`).

Итоговая секция скриптов:
```
## Скрипты
- `bash run_scan.sh` — запуск сканера (все источники, через Lineman)
- `bash run_scan.sh --dry-run` — тестовый прогон без отправки
- `reports/` — архив отчётов
- `seen-jobs.json` — дедупликация
```

### 2. Проверить Google baseUrl

Убедиться что в `~/.openclaw/openclaw.json` → `providers.google.baseUrl` содержит `/v1beta`.
Без `/v1beta` все вызовы Gemini возвращают 404.

Эта проверка read-only — если baseUrl корректен, ничего не трогаем.

### 3. Dry-run

```bash
cd ~/workspaces/jobsearch && bash run_scan.sh --dry-run
```

Успех = скрипт завершается без Python exception. Если падает — диагностировать scan_v4.py отдельно перед включением кронов.

### 4. Включить cron jobs

В `~/.openclaw/cron/jobs.json` установить `"enabled": true` для:
- `e8e34b8f-876a-4fe9-860a-83c7c90bc453` (Job Scan Morning, 06:00 MSK)
- `3e5a4848-99e1-4ba0-a385-291708b17ef2` (Job Scan Evening, 17:00 MSK)

OpenClaw подхватывает изменения автоматически (hot reload).

## Success Criteria

- `bash run_scan.sh --dry-run` завершается без exception
- Оба cron job `enabled: true` в jobs.json
- TOOLS.md не содержит credentials
- TOOLS.md ссылается на `run_scan.sh`, не на `scan.py`
- Следующий запуск по расписанию не возвращает "run python3 scan.py failed"
