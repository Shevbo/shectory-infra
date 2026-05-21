# Voice Engine Redesign — gemini-live-service

Date: 2026-05-21
Status: Approved

## Problem

1. TTS генерируется очень долго (Gemini Native Audio — последовательный).
2. Переключатель "Говорю" сбрасывается в "Молчу" через ~10 сек из-за `turn_complete` в Gemini Native Audio.
3. Нет хранения аудио диалогов для последующего прослушивания.

## Solution

Заменить Gemini Native Audio на pipeline: **ASR → DeepSeek → Gemini TTS (стриминг)**.

---

## Section 1: Architecture

```
Браузер
  ├── [Говорю] → буфер PCM → audio_end (ручной или VAD 45s)
  └── WebSocket ──────────────────────────────────────────────────────┐
                                                                       │
Server (voice_ws.py)                                                   │
  ├── audio_end → asr.py → asr_gemini.py (Gemini Flash, iProyal)     │
  ├── text → llm.py → DeepSeek (compact summaries context ~500 tok)   │
  ├── response → tts.py → Gemini TTS stream → tts_chunk × N          │
  └── gdrive.py → MP3 + TXT upload → audioGdriveId в БД              │
                                                                       │
WebSocket protocol:                                                    │
  client→server: audio_start | audio_chunk | audio_end               │
  server→client: thinking | big_input | tts_chunk | turn_complete     │
```

Клиент буферизует все audio_chunk в памяти — не отправляет на сервер до audio_end.

---

## Section 2: Memory & Storage

### Prisma — новые поля

```prisma
model Turn {
  // существующие поля...
  summary       String?   // NEW: 1 предложение для DeepSeek контекста
  audioGdriveId String?   // NEW: Google Drive file ID папки тёрна
}

model Session {
  // существующие поля...
  audioGdriveId String?   // NEW: Drive ID папки сессии (переиспользует audioStoragePath логически)
}
```

### Google Drive структура

```
nurse-dialogs/YYYY-MM/<session_id>/
  turn_001_user.mp3
  turn_001_user.txt        # полный транскрипт
  turn_001_nurse.mp3
  turn_001_nurse.txt       # полный текст ответа
  turn_002_user.mp3
  turn_002_user.txt
  ...
  session_transcript.txt   # склейка всех turn.txt по порядку
  session_full.mp3         # опционально, постсессионная склейка
```

Формат аудио: **MP3** (не OGG).

### DeepSeek контекст

~500 токенов: последние 10 `turn.summary` + `session.summary` предыдущих сессий.
Полный текст хранится в БД и Drive — для восстановления истории клиента в терапии.

---

## Section 3: Client Changes (app.js / audio.js)

### Новые состояния UI

| Состояние | Цвет | Текст | Переход |
|---|---|---|---|
| `listening` | красный | Слушаю | нажатие переключателя → `speaking` |
| `speaking` | зелёный | Говорю | audio_end → `thinking` |
| `thinking` | синий | Думаю... | первый tts_chunk → `playing` |
| `playing` | фиолетовый | Отвечаю | turn_complete → `listening` |

### VAD

- 45s тишины (RMS < порог) → автоматически `audio_end`
- Минимальная длина записи: 1 секунда (игнорировать короче)

### Буферизация

`MicRecorder` собирает все PCM-чанки в массив. При `audio_end` отправляет весь буфер одним WebSocket-сообщением (или чанками с флагом `last:true`).

### Защита от сброса состояния

`turn_complete` переводит только из `playing` → `listening`. Состояние `speaking` сервер не трогает.

---

## Section 4: Server Changes

### Новые файлы

```
src/services/
  asr.py     # subprocess → asr_gemini.py, PCM → text
  llm.py     # DeepSeek API, compact context → response text
  tts.py     # Gemini TTS stream, PCM → MP3 chunks
  gdrive.py  # Google Drive API v3, upload MP3 + TXT
```

### voice_ws.py — цикл тёрна

```python
async def handle_turn(ws, session, audio_chunks):
    text = await asr.transcribe(audio_chunks)
    if not text.strip():
        await ws.send_json({"type":"error","message":"не расслышала"})
        return

    user_turn = await db.save_turn(role="user", text=text, session_id=session.id)

    word_count = len(text.split())
    if word_count > 300:
        minutes = max(1, word_count // 150)
        await ws.send_json({"type":"big_input","minutes":minutes})

    context = await db.get_context_summaries(session.id)
    response_text = await llm.generate(context, text)

    await ws.send_json({"type":"thinking"})
    async for pcm_chunk in tts.stream(response_text):
        await ws.send_json({"type":"tts_chunk","data": base64(pcm_chunk)})

    nurse_turn = await db.save_turn(role="nurse", text=response_text, session_id=session.id)
    await gdrive.upload_turn(session, user_turn, nurse_turn)

    await ws.send_json({"type":"turn_complete"})
```

### Модели

| Компонент | Модель | Примечание |
|---|---|---|
| ASR | `gemini-2.5-flash` | через `asr_gemini.py`, iProyal прокси |
| LLM | `deepseek-v4-flash` (отладка) / `deepseek-v4-pro` (прод) | compact summaries context |
| TTS | `gemini-2.5-flash-preview-tts` | стриминг, голосовой профиль медсестры |

---

## Section 5: Error Handling

Минимальный набор — детали будут добавляться по мере возникновения ошибок:

- ASR пустой результат → `{type:"error"}` клиенту, тёрн не сохраняется
- DeepSeek таймаут → 1 retry, затем `{type:"error"}`
- Google Drive недоступен → сохранить тёрн в БД без `audioGdriveId`, Drive-upload в фоновую очередь
- WebSocket disconnect → сохранить частичный тёрн, Drive-upload пропустить

---

## Out of Scope

- Синтез речи пользователя (клиент пишет в Drive своё аудио — уже есть через буфер)
- Автоматическая склейка `session_full.mp3` — постсессионная задача, отдельный тикет
- Ошибки Drive — подробная логика retry-очереди откладывается
