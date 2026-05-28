# voice-parser — Транскрипция и анализ аудио/видео через Gemini

Единый скилл для всех агентов федерации. Принимает любой аудио или видеофайл, отдаёт транскрипцию или структурированный анализ.

## Поддерживаемые форматы

| Тип | Форматы |
|-----|---------|
| Аудио | `.ogg` `.mp3` `.wav` `.m4a` `.webm` `.opus` |
| Видео | `.mp4` `.mov` `.mkv` `.avi` `.3gp` |

Лимит размера: нет. Маленькие файлы (< 19MB аудио) — через inline. Большие и все видео — через Gemini File API.

## Три точки входа

### 1. Файл уже на диске

```bash
python3 /home/shectory/skills/voice-parser/scripts/parse_voice.py <путь_к_файлу> [mode]
```

### 2. Telegram file_id (от бота)

```bash
python3 /home/shectory/skills/voice-parser/scripts/download_and_parse.py <file_id> \
    --message-id=<msg_id> --account-id=<bot_id> [mode]
```

Автоматически откатывается на Telethon если файл > 20MB.

### 3. URL с любого файлообменника

```bash
python3 /home/shectory/skills/voice-parser/scripts/download_from_url.py <url> [mode]
```

Поддерживает: Google Drive, Yandex.Disk, Dropbox, OneDrive, любой прямой HTTP(S) URL.
Аргумент `download_and_parse.py` тоже принимает URL — автоматически роутит сюда.

## Режимы анализа (mode)

| Mode | Описание |
|------|---------|
| `transcribe` | Только транскрипция слово в слово (default) |
| `interview` | Разбор записи собеседования: вопрос/ответ + оценка + следующие шаги |
| `workout` | Анализ тренировочного видео: техника, ошибки, рекомендации |
| `monologue` | Транскрипция монолога + краткая выжимка + структура + эмоциональный тон |

Или передай произвольный промпт строкой вместо mode.

## Примеры по агентам

### interview-coach — запись собеседования

```bash
# Диктофонная запись с любого хостинга:
python3 /home/shectory/skills/voice-parser/scripts/download_from_url.py \
    "https://disk.yandex.ru/d/abcXYZ123" interview

# Запись Zoom (mp4) из Telegram:
python3 /home/shectory/skills/voice-parser/scripts/download_and_parse.py \
    <file_id> --message-id=<id> --account-id=interview-coach interview
```

### titan — видео тренировки

```bash
# Видео с Google Drive:
python3 /home/shectory/skills/voice-parser/scripts/download_from_url.py \
    "https://drive.google.com/file/d/ABC.../view" workout

# Видео из Telegram (mp4):
python3 /home/shectory/skills/voice-parser/scripts/download_and_parse.py \
    <file_id> --message-id=<id> --account-id=titan workout
```

### nurse — голосовые монологи

```bash
# Большое голосовое из Telegram:
python3 /home/shectory/skills/voice-parser/scripts/download_and_parse.py \
    <file_id> --message-id=<id> --account-id=nurse monologue

# Аудиофайл по ссылке:
python3 /home/shectory/skills/voice-parser/scripts/download_from_url.py \
    "https://www.dropbox.com/s/xxx/memo.mp3?dl=0" monologue
```

## Форматы входящего медиа в чате

Агенты получают медиа в одном из форматов:

**Формат A — файл уже скачан (предпочтительный):**
```
[media attached: /home/shectory/.openclaw/media/inbound/XXXXX.ogg (audio/ogg)]
```
→ `python3 /home/shectory/skills/voice-parser/scripts/parse_voice.py <путь> [mode]`

**Формат B — file_id (файл не скачан):**
```
<media:audio> [file_id:XXXXXXXXXXXXX]
```
→ найти `message_id` в метаданных, запустить `download_and_parse.py`

**Формат C — URL с файлообменника:**
```
https://disk.yandex.ru/d/... или https://drive.google.com/... или любой https://
```
→ `python3 /home/shectory/skills/voice-parser/scripts/download_from_url.py <url> [mode]`

## Расположение скриптов

```
~/skills/voice-parser/scripts/
  parse_voice.py          — основной парсер (Gemini)
  download_and_parse.py   — Telegram file_id → парсинг (+ URL routing)
  download_from_url.py    — любой URL → скачать → парсинг
  download_telethon.py    — Telethon fallback для файлов >20MB
  setup_telethon_session.py — одноразовая авторизация Telethon
```

## Диагностика

| Проблема | Причина | Решение |
|---------|---------|---------|
| `gog not found` | gog не установлен | `which gog`; эскалировать к Клоду |
| `File API upload error` | Lineman недоступен или Gemini key | проверить `:9090` |
| `wget failed` | прямая ссылка недействительна | проверить URL в браузере |
| `Telethon auth required` | нет сессии | `python3 setup_telethon_session.py` |
| Видео парсится без анализа | не передан mode | добавить `workout`/`interview` |
