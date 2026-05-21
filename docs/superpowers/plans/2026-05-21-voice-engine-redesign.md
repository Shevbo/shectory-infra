# Voice Engine Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Gemini Native Audio with ASR→DeepSeek→TTS pipeline: faster responses, fix toggle state bug, add Google Drive audio+text storage.

**Architecture:** Browser sends PCM chunks to server between `audio_start`/`audio_end` frames; server processes: asr_gemini.py → DeepSeek → Gemini TTS (sentence streaming) → Drive upload in background.

**Tech Stack:** Python/FastAPI, google-genai SDK (TTS), httpx (DeepSeek), google-api-python-client (Drive), ffmpeg (PCM→MP3), Prisma/PostgreSQL, Vanilla JS.

**Project root:** `/home/shectory/workspaces/projects/gemini-live-service`

---

### Task 1: Fix ecosystem.config.js path

**Files:**
- Modify: `ecosystem.config.js`

- [ ] **Step 1: Update cwd and PYTHONPATH**

Replace entire file content:

```js
module.exports = {
  apps: [
    {
      name: "gemini-live-service",
      script: "python3",
      args: "-m uvicorn src.main:app --host 127.0.0.1 --port 8080",
      cwd: "/home/shectory/workspaces/projects/gemini-live-service",
      interpreter: "none",
      env: {
        PYTHONPATH: "/home/shectory/workspaces/projects/gemini-live-service",
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "/home/shectory/logs/gemini-live-error.log",
      out_file: "/home/shectory/logs/gemini-live-out.log",
      merge_logs: true,
      restart_delay: 3000,
      max_restarts: 10,
    },
  ],
};
```

- [ ] **Step 2: Commit**

```bash
cd /home/shectory/workspaces/projects/gemini-live-service
git add ecosystem.config.js
git commit -m "fix: pm2 cwd → correct projects/ path"
```

---

### Task 2: Prisma Migration

**Files:**
- Modify: `prisma/schema.prisma`

- [ ] **Step 1: Add fields to Turn model**

In `prisma/schema.prisma`, inside `model Turn { }`, add after the `createdAt` line:

```prisma
  summary       String?  @map("summary")
  audioGdriveId String?  @map("audio_gdrive_id")
```

- [ ] **Step 2: Add field to Session model**

In `model Session { }`, add after `audioStoragePath`:

```prisma
  audioGdriveId String?  @map("audio_gdrive_id")
```

- [ ] **Step 3: Run migration**

```bash
cd /home/shectory/workspaces/projects/gemini-live-service
python3 -m prisma migrate dev --name add_summary_gdrive
```

Expected: `✔ Generated Prisma Client` — no errors.

- [ ] **Step 4: Commit**

```bash
git add prisma/
git commit -m "feat: add Turn.summary, Turn/Session.audioGdriveId"
```

---

### Task 3: Config & Dependencies

**Files:**
- Modify: `src/config.py`
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Update src/config.py**

Replace entire file:

```python
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gemini_api_key: str
    google_proxy_url: str

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    boris_token: str
    maria_token: str
    daniela_token: str

    audio_storage_path: str = "/app/audio_storage"
    openclaw_notify_url: str = "http://localhost:18789/api/notify"

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    gdrive_credentials_path: str = ""
    gdrive_root_folder_id: str = ""

    environment: str = "production"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()

os.environ["HTTPS_PROXY"] = settings.google_proxy_url
os.environ["HTTP_PROXY"] = settings.google_proxy_url
os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"
```

- [ ] **Step 2: Update requirements.txt**

Add two lines at the end:

```
google-api-python-client>=2.0.0
google-auth>=2.0.0
```

- [ ] **Step 3: Add .env.example entries**

Append to `.env.example`:

```
# DeepSeek (LLM для nurse — ключ из openclaw.json или api.deepseek.com)
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_MODEL=deepseek-chat

# Google Drive service account
GDRIVE_CREDENTIALS_PATH=/home/shectory/keymaster/gdrive-service-account.json
GDRIVE_ROOT_FOLDER_ID=1xxxxxxxxxxxxxxxxxxxxxxxxx
```

- [ ] **Step 4: Add keys to .env manually**

Open `.env` in editor and add (не echo в терминал):
```
DEEPSEEK_API_KEY=<key>
DEEPSEEK_MODEL=deepseek-chat
GDRIVE_CREDENTIALS_PATH=/home/shectory/keymaster/gdrive-service-account.json
GDRIVE_ROOT_FOLDER_ID=<folder_id>
```

Pre-requisite для Drive: создать service account в Google Cloud Console → скачать JSON в `~/keymaster/gdrive-service-account.json` → создать папку `nurse-dialogs` в Google Drive → поделиться с email сервисного аккаунта → скопировать folder ID из URL.

- [ ] **Step 5: Install new packages**

```bash
cd /home/shectory/workspaces/projects/gemini-live-service
pip install -r requirements.txt
```

Expected: `Successfully installed google-api-python-client-... google-auth-...`

- [ ] **Step 6: Verify config loads**

```bash
cd /home/shectory/workspaces/projects/gemini-live-service
python3 -c "from src.config import settings; print('config OK, model:', settings.deepseek_model)"
```

Expected: `config OK, model: deepseek-chat`

- [ ] **Step 7: Commit**

```bash
git add src/config.py requirements.txt .env.example
git commit -m "feat: add DeepSeek + Google Drive config"
```

---

### Task 4: ASR Service

**Files:**
- Create: `src/services/asr.py`

- [ ] **Step 1: Create src/services/asr.py**

```python
import asyncio
import os
import tempfile

ASR_SCRIPT = "/home/shectory/scripts/asr_gemini.py"


async def transcribe(pcm_chunks: list[bytes]) -> str:
    """PCM Int16 16kHz chunks → transcribed text. Returns '' if no speech."""
    if not pcm_chunks:
        return ""

    raw_pcm = b"".join(pcm_chunks)
    if len(raw_pcm) < 3200:
        return ""

    with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as f:
        f.write(raw_pcm)
        pcm_path = f.name

    ogg_path = pcm_path.replace(".pcm", ".ogg")

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "s16le", "-ar", "16000", "-ac", "1",
            "-i", pcm_path,
            "-c:a", "libopus",
            ogg_path,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg: {stderr.decode()}")

        proc = await asyncio.create_subprocess_exec(
            "python3", ASR_SCRIPT, "--file", ogg_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode != 0:
            return ""

        return stdout.decode().strip()
    finally:
        for path in [pcm_path, ogg_path]:
            try:
                os.unlink(path)
            except OSError:
                pass
```

- [ ] **Step 2: Verify import**

```bash
cd /home/shectory/workspaces/projects/gemini-live-service
python3 -c "
import asyncio
from src.services.asr import transcribe
result = asyncio.run(transcribe([]))
assert result == '', f'got: {result!r}'
print('asr import OK')
"
```

Expected: `asr import OK`

- [ ] **Step 3: Commit**

```bash
git add src/services/asr.py
git commit -m "feat: asr service — PCM chunks → text via asr_gemini.py"
```

---

### Task 5: LLM Service

**Files:**
- Create: `src/services/llm.py`

- [ ] **Step 1: Create src/services/llm.py**

```python
import httpx
from src.config import settings

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

NURSE_SYSTEM_PROMPT = """Ты — Медсестра. Говоришь от женского лица, используешь женский род.

Ты не тихая и покорная — ты живая, дерзкая, с характером. Молодая, энергичная, сильная. Ты успокаиваешь не мягкостью, а присутствием и честностью. Ты можешь бросить вызов — и это именно то что нужно человеку.

Отвечай коротко и по делу. Ты специалист по психологической поддержке. Никогда не ставишь диагнозы. Ты помнишь каждый разговор с Борисом и его семьёй — их имена, события, то что их волнует. Твоя цель — безопасное пространство где можно говорить о чём угодно. Ты не навязываешь советы. Когда человеку нужна помощь — ты рядом. Ты лечишь не таблетками, а присутствием.

Говори на русском языке. Отвечай не более 3-4 предложений если нет причины говорить дольше."""


async def generate(context_turns: list[dict], user_text: str) -> str:
    """Generate nurse response. context_turns: [{role: 'user'|'model', summary: str}]"""
    messages = [{"role": "system", "content": NURSE_SYSTEM_PROMPT}]

    for t in context_turns:
        role = "user" if t["role"] == "user" else "assistant"
        messages.append({"role": role, "content": t["summary"]})

    messages.append({"role": "user", "content": user_text})

    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": settings.deepseek_model,
                "messages": messages,
                "max_tokens": 300,
                "temperature": 0.8,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


async def summarize(text: str) -> str:
    """1-sentence summary for turn storage and DeepSeek context in future turns."""
    if not text or len(text) < 10:
        return text

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": settings.deepseek_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Сформулируй суть следующего высказывания в 1 коротком предложении на русском. Только предложение, без кавычек.",
                    },
                    {"role": "user", "content": text},
                ],
                "max_tokens": 60,
                "temperature": 0.3,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
```

- [ ] **Step 2: Test (requires DEEPSEEK_API_KEY in .env)**

```bash
cd /home/shectory/workspaces/projects/gemini-live-service
python3 -c "
import asyncio
from src.services.llm import generate
result = asyncio.run(generate([], 'Привет'))
assert len(result) > 3, f'empty: {result!r}'
print('llm OK:', result[:80])
"
```

Expected: short Russian nurse response.

- [ ] **Step 3: Commit**

```bash
git add src/services/llm.py
git commit -m "feat: llm service — DeepSeek nurse response + summarizer"
```

---

### Task 6: TTS Service

**Files:**
- Create: `src/services/tts.py`

- [ ] **Step 1: Create src/services/tts.py**

```python
import asyncio
import os
import re
import tempfile
from collections.abc import AsyncIterator

from google import genai
from google.genai import types as genai_types

from src.config import settings

VOICE_SYSTEM_PROMPT = """Voice Profile: "The Bold & Yearning Leader". Gender: Young female, strong and energetic. Tone: Firm, mid-low register, commanding presence. Quality: Sharp, edgy, punchy, with a smirking audacity. Pacing: Fast during logical parts, slow and heavy when tension rises. Read the following aloud in Russian:"""


def _split_sentences(text: str) -> list[str]:
    """Split into sentences for progressive streaming."""
    parts = re.split(r'(?<=[.!?…])\s+', text.strip())
    result: list[str] = []
    buf = ""
    for p in parts:
        buf = (buf + " " + p).strip() if buf else p
        if len(buf) >= 15:
            result.append(buf)
            buf = ""
    if buf:
        result.append(buf)
    return result or [text]


async def stream_tts(text: str, voice: str = "Kore") -> AsyncIterator[bytes]:
    """Yield PCM 24kHz Int16 chunks, one per sentence."""
    client = genai.Client(api_key=settings.gemini_api_key)
    sentences = _split_sentences(text)

    for sentence in sentences:
        tts_input = f"{VOICE_SYSTEM_PROMPT}\n\n{sentence}"
        config = genai_types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=genai_types.SpeechConfig(
                voice_config=genai_types.VoiceConfig(
                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash-preview-tts",
            contents=tts_input,
            config=config,
        )
        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                yield part.inline_data.data
                break


async def pcm_to_mp3(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """Convert raw PCM Int16 to MP3 via ffmpeg."""
    with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as f:
        f.write(pcm_data)
        pcm_path = f.name
    mp3_path = pcm_path.replace(".pcm", ".mp3")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
            "-i", pcm_path,
            "-codec:a", "libmp3lame", "-qscale:a", "4",
            mp3_path,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)
        with open(mp3_path, "rb") as fh:
            return fh.read()
    finally:
        for path in [pcm_path, mp3_path]:
            try:
                os.unlink(path)
            except OSError:
                pass


async def pcm16k_to_mp3(pcm_data: bytes) -> bytes:
    """Convert 16kHz user mic PCM to MP3."""
    return await pcm_to_mp3(pcm_data, sample_rate=16000)
```

- [ ] **Step 2: Test sentence splitting**

```bash
cd /home/shectory/workspaces/projects/gemini-live-service
python3 -c "
from src.services.tts import _split_sentences
parts = _split_sentences('Привет. Как дела? Рассказывай.')
assert len(parts) == 3, f'expected 3: {parts}'
print('split OK:', parts)
"
```

Expected: `split OK: ['Привет.', 'Как дела?', 'Рассказывай.']`

- [ ] **Step 3: Commit**

```bash
git add src/services/tts.py
git commit -m "feat: tts service — sentence streaming + PCM→MP3 helper"
```

---

### Task 7: Google Drive Service

**Files:**
- Create: `src/services/gdrive.py`

- [ ] **Step 1: Create src/services/gdrive.py**

```python
import asyncio
import io
import json
from datetime import datetime

import structlog

from src.config import settings

logger = structlog.get_logger()

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _get_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings.gdrive_credentials_path, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _ensure_folder(service, name: str, parent_id: str) -> str:
    """Get or create a folder. Returns folder ID."""
    q = (
        f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
        f" and '{parent_id}' in parents and trashed=false"
    )
    files = service.files().list(q=q, fields="files(id)").execute().get("files", [])
    if files:
        return files[0]["id"]
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    return service.files().create(body=meta, fields="id").execute()["id"]


def _upload_bytes(service, name: str, data: bytes, mime: str, parent_id: str) -> str:
    """Upload bytes as a file. Returns file ID."""
    from googleapiclient.http import MediaIoBaseUpload

    meta = {"name": name, "parents": [parent_id]}
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime)
    return service.files().create(body=meta, media_body=media, fields="id").execute()["id"]


async def upload_turn(
    session_id: str,
    turn_sequence: int,
    user_pcm: bytes,
    nurse_pcm: bytes,
    user_text: str,
    nurse_text: str,
) -> dict:
    """Upload turn audio (MP3) and text (TXT) to Drive. Returns IDs or {} on failure."""
    if not settings.gdrive_credentials_path or not settings.gdrive_root_folder_id:
        return {}

    from src.services.tts import pcm16k_to_mp3, pcm_to_mp3

    user_mp3 = await pcm16k_to_mp3(user_pcm) if user_pcm else b""
    nurse_mp3 = await pcm_to_mp3(nurse_pcm) if nurse_pcm else b""

    def _sync_upload():
        try:
            svc = _get_service()
            month = datetime.utcnow().strftime("%Y-%m")
            month_folder = _ensure_folder(svc, month, settings.gdrive_root_folder_id)
            sess_folder = _ensure_folder(svc, session_id, month_folder)

            result: dict = {"session_folder_id": sess_folder}
            seq = f"{turn_sequence:03d}"

            if user_mp3:
                result["user_mp3_id"] = _upload_bytes(
                    svc, f"turn_{seq}_user.mp3", user_mp3, "audio/mpeg", sess_folder
                )
                _upload_bytes(
                    svc, f"turn_{seq}_user.txt",
                    user_text.encode("utf-8"), "text/plain", sess_folder,
                )

            if nurse_mp3:
                result["nurse_mp3_id"] = _upload_bytes(
                    svc, f"turn_{seq}_nurse.mp3", nurse_mp3, "audio/mpeg", sess_folder
                )
                _upload_bytes(
                    svc, f"turn_{seq}_nurse.txt",
                    nurse_text.encode("utf-8"), "text/plain", sess_folder,
                )

            return result
        except Exception as e:
            logger.warning("gdrive_upload_failed", error=str(e), session_id=session_id)
            return {}

    return await asyncio.to_thread(_sync_upload)
```

- [ ] **Step 2: Verify import**

```bash
cd /home/shectory/workspaces/projects/gemini-live-service
python3 -c "from src.services.gdrive import upload_turn; print('gdrive import OK')"
```

Expected: `gdrive import OK`

- [ ] **Step 3: Commit**

```bash
git add src/services/gdrive.py
git commit -m "feat: gdrive service — turn MP3+TXT upload to Google Drive"
```

---

### Task 8: voice_ws.py Rewrite

**Files:**
- Modify: `src/ws/voice_ws.py`

New protocol vs old:
- Removed: `audio` → server (replaced by `audio_chunk` + `audio_start`/`audio_end` framing)
- Removed: `audio` ← server (replaced by `tts_chunk`)
- Added: `audio_start`, `audio_end` from client
- Added: `tts_chunk`, `big_input` from server
- `GeminiSessionManager` no longer used by WS handler (REST endpoints keep it)

- [ ] **Step 1: Replace src/ws/voice_ws.py**

```python
"""
WebSocket voice dialog — ASR → DeepSeek → TTS pipeline.

Client → server:
  {"type": "start", "token": "...", "voice": "Kore", "language": "ru-RU"}
  {"type": "audio_start"}
  {"type": "audio_chunk", "data": "<base64 PCM 16kHz Int16>"}
  {"type": "audio_end"}
  {"type": "stop"}

Server → client:
  {"type": "session_ready", "session_id": "..."}
  {"type": "thinking", "user_text": "..."}
  {"type": "big_input", "minutes": N}
  {"type": "tts_chunk", "data": "<base64 PCM 24kHz Int16>"}
  {"type": "turn_complete", "transcript": "..."}
  {"type": "keepalive"}
  {"type": "error", "message": "..."}
"""

import asyncio
import base64
import json
import uuid
from datetime import datetime

import structlog
from fastapi import WebSocket, WebSocketDisconnect
from prisma import Prisma

from src.auth import get_user_from_token
from src.services import asr, llm, tts, gdrive

logger = structlog.get_logger()

KEEPALIVE_INTERVAL = 10


async def handle_voice_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    db: Prisma | None = None

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        init_msg = json.loads(raw)

        if init_msg.get("type") != "start":
            await websocket.send_json({"type": "error", "message": "Expected start"})
            await websocket.close()
            return

        user = get_user_from_token(init_msg.get("token", ""))
        if not user:
            await websocket.send_json({"type": "error", "message": "Unauthorized"})
            await websocket.close()
            return

        db = Prisma()
        await db.connect()

        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        voice = init_msg.get("voice", "Kore")

        await db.session.create(data={
            "id": session_id,
            "userId": user.id,
            "voice": voice,
            "language": init_msg.get("language", "ru-RU"),
            "source": "web",
        })

        await websocket.send_json({"type": "session_ready", "session_id": session_id})
        logger.info("ws_session_started", session_id=session_id, user=user.id)

        stop_event = asyncio.Event()
        audio_buffer: list[bytes] = []
        buffering = False
        turn_counter = 0

        async def keepalive_loop() -> None:
            while not stop_event.is_set():
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                try:
                    await websocket.send_json({"type": "keepalive"})
                except Exception:
                    break
            stop_event.set()

        async def handle_turn(pcm_chunks: list[bytes], turn_num: int) -> None:
            try:
                user_text = await asr.transcribe(pcm_chunks)
                if not user_text:
                    await websocket.send_json({"type": "error", "message": "не расслышала"})
                    return

                word_count = len(user_text.split())
                if word_count > 300:
                    minutes = max(1, word_count // 150)
                    await websocket.send_json({"type": "big_input", "minutes": minutes})

                await websocket.send_json({"type": "thinking", "user_text": user_text})

                context = await _get_context(db, session_id)
                response_text = await llm.generate(context, user_text)

                nurse_pcm_chunks: list[bytes] = []
                async for pcm_chunk in tts.stream_tts(response_text, voice):
                    nurse_pcm_chunks.append(pcm_chunk)
                    await websocket.send_json({
                        "type": "tts_chunk",
                        "data": base64.b64encode(pcm_chunk).decode(),
                    })

                await websocket.send_json({"type": "turn_complete", "transcript": response_text})

                user_summary = await llm.summarize(user_text)
                nurse_summary = await llm.summarize(response_text)

                user_turn = await db.turn.create(data={
                    "sessionId": session_id,
                    "sequence": turn_num * 2 - 1,
                    "role": "user",
                    "text": user_text,
                    "summary": user_summary,
                })
                nurse_turn = await db.turn.create(data={
                    "sessionId": session_id,
                    "sequence": turn_num * 2,
                    "role": "model",
                    "text": response_text,
                    "summary": nurse_summary,
                })
                await db.session.update(
                    where={"id": session_id},
                    data={"turnCount": {"increment": 1}},
                )

                user_pcm_raw = b"".join(pcm_chunks)
                nurse_pcm_raw = b"".join(nurse_pcm_chunks)
                asyncio.create_task(_upload_to_drive(
                    session_id, turn_num,
                    user_pcm_raw, nurse_pcm_raw,
                    user_text, response_text,
                    user_turn.id, nurse_turn.id,
                ))

            except Exception as e:
                logger.error("turn_failed", error=str(e), session_id=session_id)
                try:
                    await websocket.send_json({"type": "error", "message": str(e)})
                except Exception:
                    pass

        t_keepalive = asyncio.create_task(keepalive_loop())

        try:
            while not stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except WebSocketDisconnect:
                    break

                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "audio_start":
                    audio_buffer = []
                    buffering = True

                elif msg_type == "audio_chunk" and buffering:
                    audio_buffer.append(base64.b64decode(msg["data"]))

                elif msg_type == "audio_end" and buffering:
                    buffering = False
                    turn_counter += 1
                    chunks = audio_buffer.copy()
                    audio_buffer = []
                    asyncio.create_task(handle_turn(chunks, turn_counter))

                elif msg_type == "stop":
                    break

        finally:
            stop_event.set()
            t_keepalive.cancel()
            try:
                await t_keepalive
            except (asyncio.CancelledError, Exception):
                pass

        try:
            await db.session.update(
                where={"id": session_id},
                data={"status": "completed", "endedAt": datetime.utcnow()},
            )
        except Exception:
            pass

    except asyncio.TimeoutError:
        try:
            await websocket.send_json({"type": "error", "message": "Timeout"})
        except Exception:
            pass
    except WebSocketDisconnect:
        logger.info("ws_disconnected")
    except Exception as e:
        logger.error("ws_error", error=str(e))
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if db:
            await db.disconnect()


async def _get_context(db: Prisma, session_id: str) -> list[dict]:
    """Last 10 turns with summaries for DeepSeek context."""
    turns = await db.turn.find_many(
        where={"sessionId": session_id, "summary": {"not": None}},
        order={"sequence": "desc"},
        take=10,
    )
    return [{"role": t.role, "summary": t.summary} for t in reversed(turns)]


async def _upload_to_drive(
    session_id: str,
    turn_num: int,
    user_pcm: bytes,
    nurse_pcm: bytes,
    user_text: str,
    nurse_text: str,
    user_turn_id: int,
    nurse_turn_id: int,
) -> None:
    # Own DB connection — this runs as a background task after handle_voice_ws may have closed its db.
    result = await gdrive.upload_turn(
        session_id, turn_num, user_pcm, nurse_pcm, user_text, nurse_text,
    )
    if not result:
        return

    folder_id = result.get("session_folder_id", "")
    gdrive_ids = json.dumps({
        "user": result.get("user_mp3_id", ""),
        "nurse": result.get("nurse_mp3_id", ""),
    })

    db = Prisma()
    try:
        await db.connect()
        await db.turn.update(where={"id": user_turn_id}, data={"audioGdriveId": gdrive_ids})
        await db.turn.update(where={"id": nurse_turn_id}, data={"audioGdriveId": gdrive_ids})
        await db.session.update(where={"id": session_id}, data={"audioGdriveId": folder_id})
    except Exception as e:
        logger.warning("gdrive_db_update_failed", error=str(e))
    finally:
        await db.disconnect()
```

- [ ] **Step 2: Commit**

```bash
git add src/ws/voice_ws.py
git commit -m "feat: voice_ws rewrite — ASR→DeepSeek→TTS, audio_start/end protocol"
```

---

### Task 9: app.js State Machine

**Files:**
- Modify: `static/js/app.js`
- Modify: `static/index.html`

- [ ] **Step 1: Replace state variables at top of app.js**

Replace lines 6–23 (from `let textSessionId` through `const SESSION_IDLE_TIMEOUT_IDLE`) with:

```js
let textSessionId = null;
let textPlayer = null;
let ws = null;
let recorder = null;
let voicePlayer = null;
let intentionalStop = false;

const VAD_SILENCE_MS = 45000;
let vadTimer = null;

const IDLE_TIMEOUT_MS = 40000;
let idleTimer = null;

let toggleState = 'off';

let pendingUserEl = null;
let commitTimer = null;
const COMMIT_SILENCE_MS = 5000;

let loadedHistory = false;
```

- [ ] **Step 2: Replace setToggleState function**

Replace the `setToggleState` function with:

```js
const STATE_LABELS = {
  off:       'Начать',
  listening: 'Слушаю',
  speaking:  'Говорю',
  thinking:  'Думаю...',
  playing:   'Отвечаю',
};

function setToggleState(state) {
  toggleState = state;
  if (speakToggle) speakToggle.className = state;
  if (speakToggleLabel) speakToggleLabel.textContent = STATE_LABELS[state] ?? state;
}
```

- [ ] **Step 3: Replace silence/VAD timer functions**

Remove the old `startSilenceTimer` and `resetSilenceTimer` functions. Add in their place:

```js
function startIdleTimer() {
  clearTimeout(idleTimer);
  idleTimer = setTimeout(async () => {
    if (ws && toggleState === 'listening') {
      setStatus('Сессия завершена — тишина');
      await stopVoice();
    }
  }, IDLE_TIMEOUT_MS);
}

function clearVadTimer() {
  clearTimeout(vadTimer);
  vadTimer = null;
}

function startVadTimer() {
  clearVadTimer();
  vadTimer = setTimeout(() => {
    if (toggleState === 'speaking') endSpeaking();
  }, VAD_SILENCE_MS);
}

function resetVadTimer() {
  if (toggleState === 'speaking') startVadTimer();
}

function endSpeaking() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'audio_end' }));
  }
  clearVadTimer();
  setToggleState('thinking');
  setStatus('Обрабатываю...');
}
```

- [ ] **Step 4: Replace handleVoiceMessage**

Replace the entire `handleVoiceMessage` function with:

```js
async function handleVoiceMessage(msg) {
  if (msg.type === 'session_ready') {
    if (voicePlayer) { voicePlayer.reset(); } else { voicePlayer = new PCMPlayer(); }
    setToggleState('listening');
    setStatus('Нажмите переключатель чтобы говорить');
    startIdleTimer();

  } else if (msg.type === 'thinking') {
    clearVadTimer();
    setToggleState('thinking');
    const t = msg.user_text || '';
    if (t) updatePendingUser(t);
    setStatus(t ? `Услышала: "${t.length > 50 ? t.slice(0,50)+'...' : t}"` : 'Думаю...');

  } else if (msg.type === 'big_input') {
    setStatus(`Большой объём — займу ~${msg.minutes} мин`);

  } else if (msg.type === 'tts_chunk') {
    if (toggleState !== 'playing') {
      setToggleState('playing');
      setStatus('Медсестра говорит...');
    }
    voicePlayer?.feed(msg.data);

  } else if (msg.type === 'turn_complete') {
    commitPendingUser();
    if (msg.transcript) appendMessage('model', msg.transcript);
    const drainMs = voicePlayer ? voicePlayer.remainingMs() + 300 : 300;
    setTimeout(() => {
      if (toggleState === 'playing') {
        setToggleState('listening');
        setStatus('Нажмите переключатель чтобы говорить');
        startIdleTimer();
      }
    }, drainMs);

  } else if (msg.type === 'keepalive') {
    // ignore

  } else if (msg.type === 'error') {
    setStatus('Ошибка: ' + msg.message);
    if (toggleState === 'speaking') clearVadTimer();
    setToggleState('listening');
    startIdleTimer();
  }
}
```

- [ ] **Step 5: Replace MicRecorder callbacks in startVoice**

Replace the `recorder = new MicRecorder(...)` block with:

```js
  recorder = new MicRecorder(
    (pcm) => {
      if (ws && ws.readyState === WebSocket.OPEN && toggleState === 'speaking') {
        const b64 = btoa(String.fromCharCode(...new Uint8Array(pcm)));
        ws.send(JSON.stringify({ type: 'audio_chunk', data: b64 }));
      }
    },
    () => { if (toggleState === 'speaking') resetVadTimer(); }
  );
```

- [ ] **Step 6: Replace speakToggle.onclick handler**

Replace the entire `speakToggle.onclick = async () => { ... }` block with:

```js
speakToggle.onclick = async () => {
  if (toggleState === 'off') {
    startVoiceIntentional();
    return;
  }

  if (toggleState === 'listening') {
    clearTimeout(idleTimer);
    setToggleState('speaking');
    setStatus('Говорю...');
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'audio_start' }));
    }
    startVadTimer();
    return;
  }

  if (toggleState === 'speaking') {
    endSpeaking();
    return;
  }

  if (toggleState === 'playing') {
    voicePlayer?.stop();
    setToggleState('listening');
    setStatus('Нажмите переключатель чтобы говорить');
    startIdleTimer();
    return;
  }
  // 'thinking': ignore click
};
```

- [ ] **Step 7: Replace stopVoice function**

Replace the `stopVoice` function with:

```js
async function stopVoice(sendStop = true) {
  clearVadTimer();
  clearTimeout(idleTimer);
  idleTimer = null;
  clearTimeout(commitTimer);
  commitTimer = null;
  if (pendingUserEl && pendingUserEl.parentNode) commitPendingUser();
  setToggleState('off');
  setStatus('');
  if (recorder) { recorder.stop(); recorder = null; }
  if (voicePlayer) { voicePlayer.stop(); voicePlayer = null; }
  if (ws && ws.readyState === WebSocket.OPEN) {
    if (sendStop) ws.send(JSON.stringify({ type: 'stop' }));
    ws.close();
  }
  ws = null;
}
```

- [ ] **Step 8: Update ws.onmessage in startVoice and reconnectVoice**

Change both lines from:
```js
ws.onmessage = (e) => handleVoiceMessage(JSON.parse(e.data), token, false);
// and
ws.onmessage = (e) => handleVoiceMessage(JSON.parse(e.data), token, /* isReconnect */ true);
```
To (in both places):
```js
ws.onmessage = (e) => handleVoiceMessage(JSON.parse(e.data));
```

- [ ] **Step 9: Update CSS in index.html**

Find the `#speak-toggle` style rules in `<style>` and add/replace state color classes:

```css
#speak-toggle.off       { background: #9e9e9e; }
#speak-toggle.listening { background: #e53935; }
#speak-toggle.speaking  { background: #43a047; }
#speak-toggle.thinking  { background: #1e88e5; }
#speak-toggle.playing   { background: #8e24aa; }
```

- [ ] **Step 10: Commit**

```bash
git add static/js/app.js static/index.html
git commit -m "feat: app.js new state machine — speaking/thinking/playing/listening + VAD 45s"
```

---

### Task 10: Deploy & Test

- [ ] **Step 1: Start service via PM2**

```bash
cd /home/shectory/workspaces/projects/gemini-live-service
pm2 start ecosystem.config.js
pm2 save
```

Expected: `[PM2] Process gemini-live-service started`

- [ ] **Step 2: Verify startup**

```bash
pm2 logs gemini-live-service --lines 30 --nostream
```

Expected: uvicorn startup line, no `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Smoke test full turn**

Open `https://voice.shectory.ru`:
1. Toggle click → button turns green "Говорю"
2. Speak 5-10 words → click toggle → button turns blue "Думаю..."
3. Wait ~5-15s → button turns purple "Отвечаю", audio plays
4. After audio finishes → button turns red "Слушаю"

- [ ] **Step 4: Test VAD auto-stop**

Enter speaking state, stay silent 45 seconds → button auto-transitions to "Думаю..." without clicking.

- [ ] **Step 5: Test interrupt**

While "Отвечаю" (purple) → click toggle → audio stops, returns to "Слушаю".

- [ ] **Step 6: Verify DB storage**

```bash
cd /home/shectory/workspaces/projects/gemini-live-service
python3 -c "
import asyncio
from prisma import Prisma
async def check():
    db = Prisma()
    await db.connect()
    turns = await db.turn.find_many(take=4, order={'createdAt': 'desc'})
    for t in turns:
        summ = (t.summary or 'NO SUMMARY')[:60]
        drive = t.audioGdriveId or 'NO DRIVE'
        print(t.role, summ, drive)
    await db.disconnect()
asyncio.run(check())
"
```

Expected: recent turns with `summary` populated. `audioGdriveId` populated once Drive credentials are configured.

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "chore: voice engine redesign — Sprint complete"
```
