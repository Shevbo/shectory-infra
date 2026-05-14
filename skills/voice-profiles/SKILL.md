---
name: voice-profiles
description: Manage TTS voice profiles — create, edit, test, assign to agent roles. Use when the user mentions голоса, голосовые профили, роли голосов, медсестра, TTS voice, voice roles, /voices.
---

# Voice Profiles

Система управления голосами TTS с привязкой к ролям агентов.

## Хранилище

Все профили голосов и роли хранятся в `~/.openclaw/voices.json`.

Структура:
```json
{
  "voices": {
    "medsestra": {
      "name": "Медсестра",
      "description": "Заботливая медсестра психологической поддержки",
      "provider": "google",
      "model": "gemini-2.5-flash-preview-tts",
      "voiceName": "Kore",          // конкретный голос Gemini
      "prompt": "Speak in a calm...", // стиль речи (audio-profile-v1)
      "assignedTo": ["nurse"],       // к каким ролям привязан
      "createdAt": "2026-05-07T00:00:00Z",
      "updatedAt": "2026-05-07T00:00:00Z"
    }
  },
  "roles": {
    "nurse": {
      "voiceId": "medsestra",
      "systemPrompt": "Ты — медсестра..." // системный промпт для агента
    }
  }
}
```

## Доступные голоса Gemini

| Голос | Характер | Для кого |
|---|---|---|
| Kore | Нейтральный, женский, тёплый | Медсестра, поддержка |
| Puck | Энергичный, молодой | Помощник, активный |
| Fenrir | Низкий, мужской, уверенный | Разработчик, техлид |
| Charon | Глубокий, спокойный | Наставник, коуч |
| Aoede | Мягкий, мелодичный | Творчество, сторителлинг |
| Algieba | Уверенный, повествовательный | Новости, лекции |
| Dipper | Дружелюбный, разговорный | Друг, собеседник |

## Команды управления (через exec)

```bash
python3 ~/skills/voice-profiles/scripts/voices.py list           # список всех профилей
python3 ~/skills/voice-profiles/scripts/voices.py show <id>      # детали профиля
python3 ~/skills/voice-profiles/scripts/voices.py create <id> <name> <voice>  # создать
python3 ~/skills/voice-profiles/scripts/voices.py set-prompt <id> <prompt>    # промпт
python3 ~/skills/voice-profiles/scripts/voices.py set-voice <id> <voice>      # сменить голос
python3 ~/skills/voice-profiles/scripts/voices.py assign <id> <role>          # привязать к роли
python3 ~/skills/voice-profiles/scripts/voices.py delete <id>                 # удалить
python3 ~/skills/voice-profiles/scripts/voices.py test <id> [текст]           # тест TTS
python3 ~/skills/voice-profiles/scripts/voices.py roles                       # список ролей
python3 ~/skills/voice-profiles/scripts/voices.py voices                      # доступные голоса
```

## Поток отправки голоса (оптимизированный)

Когда нужно отправить голосовое:

1. Отправить в Telegram: `"🎵 Слушаю... готовлю ответ..."` (сохранить message_id)
2. Сгенерировать TTS аудио (через Gemini TTS API)
3. Удалить текстовое сообщение через `deleteMessage`
4. Отправить голосовое через `sendVoice`

Использовать `~/skills/voice-profiles/scripts/tts_flow.py send <chat_id> <text>`.

## Как привязать голос к агенту

В конфиге агента переопределить TTS:
```json5
{
  agents: {
    list: [{
      id: "nurse-agent",
      tts: {
        personas: {
          medsestra: {
            provider: "google",
            providers: {
              google: { voiceName: "Kore", promptTemplate: "audio-profile-v1" }
            }
          }
        }
      }
    }]
  }
}
```

## Telegram кнопка "Голоса ролей"

Кнопка отправляет `/voices`. Агент вызывает `voices.py list` и показывает результат.
Управление: `/voices show medsestra`, `/voices set-prompt medsestra <новый промпт>`, `/voices test medsestra`.
