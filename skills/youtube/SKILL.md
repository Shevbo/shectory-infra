---
name: youtube
description: YouTube Data API v3 — поиск видео, чтение описаний, комментарии. Используй для поиска контента на YouTube и извлечения ссылок из описаний видео.
homepage: https://developers.google.com/youtube/v3
metadata: {"clawdbot":{"emoji":"▶️","requires":{"bins":["python3"],"env":["YOUTUBE_API_KEY"]}}}
---

# youtube — YouTube Data API v3

## Настройка

Нужен API ключ YouTube Data API v3:
1. Открой [Google Cloud Console](https://console.cloud.google.com/) → проект `shectory`
2. APIs & Services → Enable APIs → включи **YouTube Data API v3**
3. APIs & Services → Credentials → Create API Key
4. Добавь в `~/.shectory-assist.env`:
   ```
   YOUTUBE_API_KEY=AIza...
   ```

Все запросы идут через прокси `AGENT_PROXY` (уже настроен в env).

## Команды

### Поиск видео
```bash
YOUTUBE_API_KEY=... python3 ~/skills/youtube/youtube_search.py search "openclaw нутрициолог" -n 10
```

### Полное описание + ссылки из описания
```bash
python3 ~/skills/youtube/youtube_search.py info VIDEO_ID_OR_URL
```

### Поиск + все ссылки из описания (одним шагом)
```bash
python3 ~/skills/youtube/youtube_search.py find-links "230000 долларов openclaw" -n 10
```

### Комментарии к видео
```bash
python3 ~/skills/youtube/youtube_search.py comments VIDEO_ID -n 50
```

## Пример: найти видео с нутрициологом OpenClaw

```bash
python3 ~/skills/youtube/youtube_search.py find-links "openclaw нутрициолог агент" -n 5
python3 ~/skills/youtube/youtube_search.py find-links "230000 долларов openclaw" -n 10
```

## Переменные окружения

| Переменная | Описание | Где взять |
|---|---|---|
| `YOUTUBE_API_KEY` | API ключ YouTube Data API v3 | GCP Console → project shectory |
| `AGENT_PROXY` | Прокси (уже в env) | ~/.shectory-assist.env |
