---
name: screenshot-reader
description: Premium анализ скриншотов и изображений через Gemini с прокси-обходом. Всегда используй этот навык когда пользователь присылает изображение — немедленно, без отговорок.
---

# Screenshot Reader v2 (Premium)

Анализирует скриншоты и изображения через Gemini Flash с прокси-обходом гео-блокировки. Поддержка fallback, batch, кэширования.

## ⚠️ ОБЯЗАТЕЛЬНОЕ ПРАВИЛО

**При получении любого изображения от пользователя — НЕМЕДЛЕННО запускай этот навык.**
Никаких "моя модель не видит", "расскажи словами", "напиши что там". Сразу запускай скрипт.

## Использование

```bash
# Одиночный скриншот
python3 ~/skills/screenshot-reader/scripts/analyze_screenshot.py /путь/к/изображению.png

# С кастомным промптом
python3 ~/skills/screenshot-reader/scripts/analyze_screenshot.py /путь/к/image.png "Прочитай все диалоги на этом скриншоте"

# Batch — проанализировать все свежие скриншоты
python3 ~/skills/screenshot-reader/scripts/analyze_screenshot.py batch ~/.openclaw/media/inbound/

# Batch с кастомным промптом
python3 ~/skills/screenshot-reader/scripts/analyze_screenshot.py batch "/путь/к/папке/*.png" "Что общего между этими изображениями?"
```

## Telegram / WebChat флоу

Когда пользователь присылает изображение:

1. Файл сохраняется OpenClaw в `~/.openclaw/media/inbound/`
2. **НЕМЕДЛЕННО** запустить анализ:
   ```bash
   python3 ~/skills/screenshot-reader/scripts/analyze_screenshot.py <путь> "опиши подробно"
   ```
3. Результат сохраняется в `~/.openclaw/canvas/analysis_<file>.txt`
4. Выдать ответ пользователю на основе анализа

## Как это работает

1. Берёт изображение по пути
2. Кодирует в base64
3. Отправляет в Gemini через HTTP-прокси
4. Fallback chain: gemini-2.5-flash → gemini-2.0-flash → gemini-2.0-flash-001
5. Возвращает текстовое описание

## Конфигурация

Прокси и API-ключ берутся из `~/.openclaw/openclaw.json`:
```
models.providers.google.apiKey
models.providers.google.request.proxy.url
```

## Автоматический batch по всем новым

```bash
# Проанализировать все непрочитанные изображения в inbound
python3 ~/skills/screenshot-reader/scripts/analyze_screenshot.py batch ~/.openclaw/media/inbound/ "Опиши все изображения подробно"
```
