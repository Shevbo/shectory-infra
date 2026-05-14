---
name: youtube-parse
description: Разбор YouTube видео — субтитры, ссылки из описания, структурный конспект → Google Docs. Используй при командах "разбери видео", "спарси ютюб", "youtube parse", "yt lecture".
---

# youtube-parse

Скилл для автоматического разбора YouTube лекций.

## Инструменты

- **yt-dlp** — получение метаданных и субтитров (установлен: `python3 -m yt_dlp`)
- **gog** — Google Drive/Docs API
- **curl + grep** — извлечение ссылок из HTML

## Прокси

Для YouTube API нужен прокси. Использовать:
```bash
export HTTPS_PROXY="http://USER:PASS@PROXY_HOST:PORT"
```

## Workflow

### Шаг 1: Получить метаданные видео
```bash
export HTTPS_PROXY="http://USER:PASS@PROXY_HOST:PORT"
python3 -m yt_dlp --dump-json "URL" > /tmp/video_meta.json
python3 -c "
import json
d = json.load(open('/tmp/video_meta.json'))
print('Title:', d['title'])
print('Channel:', d.get('channel'))
print('Description:', d.get('description')[:500])
"
```

### Шаг 2: Скачать субтитры
```bash
python3 -m yt_dlp --write-auto-sub --skip-download --sub-lang ru -o "/tmp/lecture" "URL"
# Если нет русских — английские:
python3 -m yt_dlp --write-auto-sub --skip-download -o "/tmp/lecture" "URL"
```

### Шаг 3: Извлечь все ссылки из описания
```bash
curl -sL "URL_видео" | grep -oP 'https?://[^"&\\ ]+' | sort -u | grep -v "youtube\|google\|ytimg\|schema\|w3"
```

### Шаг 4: Создать папку на Google Drive
```bash
gog drive mkdir "полезное с ютюб"
# Запомнить ID папки
```

### Шаг 5: Собрать Markdown-документ
Структура:
```markdown
# Тема видео
**Источник:** URL
**Канал:** ...
**Дата разбора:** YYYY-MM-DD

## Ключевые идеи
[кратко]

## Основная тема (детально)
[структурированный конспект из субтитров]

## Ресурсы из видео
| Ресурс | Тип | Описание |

## Идеи для применения
[выводы]
```

### Шаг 6: Загрузить в Google Docs
```bash
gog docs create "Название" --file /tmp/result.md --parent <folderId> -j
```

### Шаг 7: Записать результат
Файл: `~/workspaces/claude-outbox/youtube_lecture_result.md`

## Особые случаи

- **Если субтитров нет** — использовать описание + комментарии
- **Если ссылка редиректит** — пройти по цепочке через `curl -sIL`
- **Для поиска конкретных тем** в субтитрах — grep по VTT файлу или Python-скрипт
