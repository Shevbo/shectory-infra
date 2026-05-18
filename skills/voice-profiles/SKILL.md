---
name: voice-profiles
description: Manage TTS voice profiles — create, edit, test, assign to agent roles. Use when the user mentions голоса, голосовые профили, роли голосов, медсестра, TTS voice, voice roles, /voice, /voices.
---

# Voice Profiles

Система управления голосами TTS с привязкой к ролям агентов.

## ⚠️ ОБЯЗАТЕЛЬНОЕ ПРАВИЛО

**Команда `/voice`** — пользователь хочет управлять голосами. 
НЕ говори "я не могу". Сразу показывай список голосов через скрипты.

## Команда /voice — ОБРАБОТКА

Когда пользователь пишет `/voice` или `/voices`:

1. **Покажи ТОЛЬКО голос текущего агента** (не всех агентов системы):
   ```bash
   python3 ~/skills/voice-profiles/scripts/voices.py show tank
   ```
2. Формат вывода: пол голоса + его описание
3. Если пользователь явно запросил список (`/voice list all` или `/voice all`) — только тогда показывать всех
4. Предложи действия: `set-voice <id> <голос>`, `set-prompt <id> <текст>`, `test <id> <текст>`

## /voice on/off — Переключение голосовых ответов

Когда пользователь пишет `/voice on`, `/voice off`, или `/voice` без аргументов:

**`/voice`** — показать текущее состояние:
```bash
python3 ~/skills/voice-profiles/scripts/voice_toggle.py status <agent_id>
```
Ответь: "Голосовые ответы: **включены**" или "Голосовые ответы: **выключены**"

**`/voice on`**:
```bash
python3 ~/skills/voice-profiles/scripts/voice_toggle.py set <agent_id> on
```
Ответь: "Голосовые ответы включены. Теперь я буду отвечать голосом."

**`/voice off`**:
```bash
python3 ~/skills/voice-profiles/scripts/voice_toggle.py set <agent_id> off
```
Ответь: "Голосовые ответы выключены."

**Важно:** замени `<agent_id>` на твой реальный ID из openclaw.json (для медсестры это `nurse`, для GUIlya это `guilya`, и т.д.). Твой ID совпадает с именем твоего воркспейса.

## Автоматическая генерация голоса при ответе

⚠️ Применяй при КАЖДОМ ответе пользователю (не только при /voice).

После того как сформулировал текст ответа:

1. Проверь состояние голоса:
```bash
python3 ~/skills/voice-profiles/scripts/voice_toggle.py check <agent_id>
```

2. Если exit code **0** (голос включён) — сгенерируй TTS:
```bash
python3 ~/skills/voice-profiles/scripts/tts_flow.py generate-agent <agent_id> "<текст ответа>"
```
Выведи только MEDIA-строку:
```
MEDIA:/home/shectory/.openclaw/media/tts/tts_<timestamp>.ogg[[audio_as_voice]]
```

3. Если exit code **1** (голос выключен) — отвечай обычным текстом.

**Для длинных ответов (> 500 символов):** озвучивай краткую версию (2-3 предложения), полный текст добавляй отдельным сообщением.

### Выбор голоса
```bash
# Показать доступные голоса Gemini
python3 ~/skills/voice-profiles/scripts/voices.py voices

# Сменить голос профиля
python3 ~/skills/voice-profiles/scripts/voices.py set-voice <id> <voiceName>
# Пример: python3 ~/skills/voice-profiles/scripts/voices.py set-voice tank Charon
```

### Редактирование промпта
```bash
# Показать текущий промпт
python3 ~/skills/voice-profiles/scripts/voices.py show <id>

# Установить новый промпт
python3 ~/skills/voice-profiles/scripts/voices.py set-prompt <id> "Новый стиль речи..."
```
Промпты находятся в wiki / Google Docs для редактирования, но через `/voice` можно установить напрямую.

### Тестирование голоса
```bash
# Сгенерировать тестовый голос
python3 ~/skills/voice-profiles/scripts/tts_flow.py generate <id> "Текст для озвучки"
# Результат: MEDIA:...ogg[[audio_as_voice]] — отправь пользователю
```

## Хранилище

Все профили голосов и роли хранятся в `~/.openclaw/voices.json`.

## Доступные голоса Gemini (30)

### ♀ Женские
- **Achernar** — ♀ Женский
- **Aoede** — ♀ Мягкий, мелодичный
- **Autonoe** — ♀ Женский
- **Callirrhoe** — ♀ Женский
- **Despina** — ♀ Женский
- **Erinome** — ♀ Женский
- **Gacrux** — ♀ Женский
- **Kore** — ♀ Тёплый, нейтральный
- **Laomedeia** — ♀ Женский
- **Leda** — ♀ Женский
- **Pulcherrima** — ♀ Женский
- **Sulafat** — ♀ Женский
- **Vindemiatrix** — ♀ Женский
- **Zephyr** — ♀ Женский

### ♂ Мужские
- **Achird** — ♂ Мужской
- **Algenib** — ♂ Мужской
- **Algieba** — ♂ Уверенный, повествовательный
- **Alnilam** — ♂ Мужской
- **Charon** — ♂ Глубокий, спокойный
- **Enceladus** — ♂ Мужской
- **Fenrir** — ♂ Низкий, уверенный
- **Iapetus** — ♂ Мужской
- **Orus** — ♂ Мужской
- **Puck** — ♂ Энергичный, молодой
- **Rasalgethi** — ♂ Мужской
- **Sadachbia** — ♂ Мужской
- **Sadaltager** — ♂ Мужской
- **Schedar** — ♂ Мужской
- **Umbriel** — ♂ Мужской
- **Zubenelgenubi** — ♂ Мужской

## Команды управления (через exec)

```bash
python3 ~/skills/voice-profiles/scripts/voices.py list           # список всех профилей
python3 ~/skills/voice-profiles/scripts/voices.py show <id>      # детали профиля
python3 ~/skills/voice-profiles/scripts/voices.py create <id> <name> <voice>  # создать
python3 ~/skills/voice-profiles/scripts/voices.py set-prompt <id> <prompt>    # промпт
python3 ~/skills/voice-profiles/scripts/voices.py set-voice <id> <voice>      # сменить голос
python3 ~/skills/voice-profiles/scripts/voices.py assign <id> <role>          # привязать к роли
python3 ~/skills/voice-profiles/scripts/voices.py delete <id>                 # удалить
python3 ~/skills/voice-profiles/scripts/voices.py roles                       # список ролей
python3 ~/skills/voice-profiles/scripts/voices.py voices                      # доступные голоса
```

## Генерация голоса (TTS)

```bash
# Сгенерировать OGG аудиофайл, вывести MEDIA: для отправки
python3 ~/skills/voice-profiles/scripts/tts_flow.py generate <persona> <text>
# Результат: MEDIA:/путь/к/файлу.ogg[[audio_as_voice]]
# Отправь пользователю этот MEDIA результат
```

После генерации отправь пользователю голосовое сообщение, используя:
- `MEDIA:путь[[audio_as_voice]]` в тексте ответа

## Telegram кнопка "Голоса ролей"

Кнопка отправляет `/voices`. Агент вызывает `voices.py list` и показывает результат.
Управление: `/voices show medsestra`, `/voices set-prompt medsestra <новый промпт>`, `/voices test <id> <текст>`.
