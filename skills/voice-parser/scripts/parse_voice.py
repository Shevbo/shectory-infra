#!/usr/bin/env python3
"""
Voice/Video Parser — транскрипция и анализ аудио и видео через Gemini.
Usage:
  python3 parse_voice.py <file_path> [prompt|mode_name]
  python3 parse_voice.py batch <dir_or_glob> [prompt|mode_name]

Named modes (вместо текста промпта):
  transcribe   — только транскрипция (default)
  interview    — анализ записи собеседования: вопрос/ответ + оценка + рекомендации
  workout      — анализ тренировочного видео: техника, нагрузка, рекомендации
  monologue    — структурированная транскрипция монолога с выжимкой

Поддерживаемые форматы:
  Аудио: .ogg .mp3 .wav .m4a .webm .opus
  Видео: .mp4 .mov .mkv .avi .3gp

All calls go through Lineman (LINEMAN_URL env var or http://127.0.0.1:9090).
Files < 19MB: inline_data. Files >= 19MB or video: Gemini File API.
"""

import sys, os, base64, json, requests, glob, time, uuid
from datetime import datetime

CONFIG_PATH = os.path.expanduser("~/.openclaw/openclaw.json")
FILE_SIZE_THRESHOLD = 15 * 1024 * 1024  # 15MB — go through File API earlier to avoid connection resets on borderline inline payloads
LINEMAN = os.environ.get("LINEMAN_URL", "http://127.0.0.1:9090")

# Video formats always go through File API (Gemini video understanding)
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".3gp"}

NAMED_PROMPTS = {
    "transcribe": (
        "Ты — транскрибатор. Прослушай аудио/видео и ВЕРНИ ТОЛЬКО ТРАНСКРИПЦИЮ: "
        "распознай речь слово в слово на том языке, на котором говорят. "
        "Если язык смешанный — транскрибируй как есть. "
        "Если слышна не речь — опиши звуки. "
        "Не добавляй комментариев, не исправляй грамматику, не перефразируй."
    ),
    "interview": (
        "Это запись собеседования или тренировочного интервью. "
        "Проведи детальный анализ по следующей структуре:\n\n"
        "**ТРАНСКРИПЦИЯ**\nВопрос: [вопрос интервьюера]\nОтвет: [ответ кандидата]\n"
        "(повтори для каждого вопроса-ответа)\n\n"
        "**ОЦЕНКА ПО КАЖДОМУ ОТВЕТУ**\n"
        "Для каждого ответа:\n"
        "✅ Сильно: что сказано хорошо, конкретно, убедительно\n"
        "⚠️ Слабо: чего не хватает, что лишнее, где потеряна структура\n"
        "💡 Образец: краткая усиленная версия ответа\n\n"
        "**ОБЩАЯ ОЦЕНКА**\n"
        "• Структура ответов (STAR): [оценка]\n"
        "• Конкретика и цифры: [оценка]\n"
        "• Использование 'я' vs 'мы': [оценка]\n"
        "• Хронометраж ответов: [оценка]\n"
        "• Уверенность / темп / паузы: [оценка]\n\n"
        "**СЛЕДУЮЩИЕ ШАГИ**\n"
        "1. [конкретное действие]\n"
        "2. [конкретное действие]\n"
        "3. [конкретное действие]"
    ),
    "workout": (
        "Это видеозапись тренировки. Проведи детальный анализ:\n\n"
        "**ТРАНСКРИПЦИЯ** (если есть речь тренера/спортсмена)\n\n"
        "**ТЕХНИКА ВЫПОЛНЕНИЯ**\n"
        "Для каждого упражнения/движения:\n"
        "✅ Правильно: [что выполнено технически верно]\n"
        "⚠️ Ошибки: [нарушения техники, риски травм]\n"
        "💡 Исправление: [конкретная рекомендация]\n\n"
        "**НАГРУЗКА И ИНТЕНСИВНОСТЬ**\n"
        "• Общий объём: [оценка]\n"
        "• Темп и ритм: [оценка]\n"
        "• Восстановление между подходами: [оценка]\n\n"
        "**РЕКОМЕНДАЦИИ**\n"
        "1. [приоритет 1]\n"
        "2. [приоритет 2]\n"
        "3. [приоритет 3]"
    ),
    "monologue": (
        "Это запись монолога или разговора. Сделай структурированный разбор:\n\n"
        "**ТРАНСКРИПЦИЯ** (полная, слово в слово)\n\n"
        "**КРАТКАЯ ВЫЖИМКА** (3-5 предложений: суть, ключевые тезисы)\n\n"
        "**СТРУКТУРА** (как организована речь: начало → развитие → выводы)\n\n"
        "**ЭМОЦИОНАЛЬНЫЙ ТОН** (уверенность, тревога, энергия, паузы)"
    ),
}


def _api_key() -> str:
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    return cfg.get("models", {}).get("providers", {}).get("google", {}).get("apiKey", "")


def get_mime(path):
    ext = os.path.splitext(path)[1].lower()
    mime_map = {
        # audio
        ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav",
        ".m4a": "audio/mp4", ".webm": "audio/webm", ".opus": "audio/ogg",
        # video
        ".mp4": "video/mp4", ".mov": "video/mp4", ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo", ".3gp": "video/3gpp",
    }
    return mime_map.get(ext, "audio/ogg")


def is_video(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def file_info(path):
    size = os.path.getsize(path)
    name = os.path.basename(path)
    return f"{name} ({size/1024:.0f}KB)"


def call_gemini_inline(api_key, b64_data, mime, prompt, model="gemini-2.5-flash"):
    """Inline base64 audio — small files via Lineman."""
    models_to_try = [model, "gemini-2.0-flash", "gemini-2.0-flash-001"]
    seen = set()
    models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]
    last_error = None

    for m in models_to_try:
        try:
            url = f"{LINEMAN}/proxy/google/v1beta/models/{m}:generateContent?key={api_key}"
            body = {
                "contents": [{"parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime, "data": b64_data}}
                ]}],
                "generationConfig": {"maxOutputTokens": 8192, "temperature": 0.1}
            }
            r = requests.post(url, json=body, timeout=120)
            data = r.json()
            if "error" in data:
                last_error = f"❌ {m}: {data['error'].get('message', str(data['error']))}"
                continue
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text:
                last_error = f"❌ {m}: No text. Finish: {data.get('candidates',[{}])[0].get('finishReason','?')}"
                continue
            return text, m
        except requests.exceptions.Timeout:
            last_error = f"❌ {m}: Timeout (120s)"
        except Exception as e:
            last_error = f"❌ {m}: {e}"

    return f"Все модели не ответили. Последняя ошибка: {last_error}", models_to_try[-1]


def upload_to_file_api(api_key, audio_path, mime):
    """Upload audio or video via Lineman → /proxy/google/upload/v1beta/files."""
    filename = os.path.basename(audio_path)
    url = f"{LINEMAN}/proxy/google/upload/v1beta/files?uploadType=multipart&key={api_key}"

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    boundary = uuid.uuid4().hex
    metadata = json.dumps({"file": {"displayName": filename}})
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{metadata}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + audio_data + f"\r\n--{boundary}--".encode()

    r = requests.post(
        url,
        data=body,
        headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        timeout=300,
    )
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"File API upload error: {data['error'].get('message', data['error'])}")

    file_uri = data.get("file", {}).get("uri", "")
    file_name = data.get("file", {}).get("name", "")
    if not file_uri:
        raise RuntimeError(f"No file URI in upload response: {data}")

    _wait_for_file_active(api_key, file_name)
    return file_uri


def _wait_for_file_active(api_key, file_name, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        url = f"{LINEMAN}/proxy/google/v1beta/{file_name}?key={api_key}"
        try:
            r = requests.get(url, timeout=10)
            state = r.json().get("file", {}).get("state", "")
            if state == "ACTIVE":
                return
            if state == "FAILED":
                raise RuntimeError("File API processing FAILED")
        except RuntimeError:
            raise
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"File API: file not ACTIVE after {timeout}s")


def delete_from_file_api(api_key, file_uri):
    try:
        path = file_uri.split("googleapis.com/")[-1]
        url = f"{LINEMAN}/proxy/google/{path}?key={api_key}"
        requests.delete(url, timeout=15)
    except Exception:
        pass


def call_gemini_file_uri(api_key, file_uri, mime, prompt, model="gemini-2.5-flash"):
    """generateContent with File API URI — small JSON body via Lineman."""
    models_to_try = [model, "gemini-2.0-flash"]
    seen = set()
    models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]
    last_error = None

    for m in models_to_try:
        try:
            url = f"{LINEMAN}/proxy/google/v1beta/models/{m}:generateContent?key={api_key}"
            body = {
                "contents": [{"parts": [
                    {"text": prompt},
                    {"file_data": {"mime_type": mime, "file_uri": file_uri}}
                ]}],
                "generationConfig": {"maxOutputTokens": 8192, "temperature": 0.1}
            }
            r = requests.post(url, json=body, timeout=120)
            data = r.json()
            if "error" in data:
                last_error = f"❌ {m}: {data['error'].get('message', str(data['error']))}"
                continue
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text:
                last_error = f"❌ {m}: No text. Finish: {data.get('candidates',[{}])[0].get('finishReason','?')}"
                continue
            return text, m
        except requests.exceptions.Timeout:
            last_error = f"❌ {m}: Timeout (120s)"
        except Exception as e:
            last_error = f"❌ {m}: {e}"

    return f"Все модели не ответили. Последняя ошибка: {last_error}", models_to_try[-1]


def parse_audio(audio_path, prompt=None):
    if not os.path.exists(audio_path):
        return f"❌ File not found: {audio_path}"

    api_key = _api_key()
    if not api_key:
        return "❌ Gemini API key not found in config"

    # Resolve named prompts
    prompt = NAMED_PROMPTS.get(prompt, prompt) if prompt else NAMED_PROMPTS["transcribe"]
    mime = get_mime(audio_path)
    file_size = os.path.getsize(audio_path)
    # Video always uses File API; audio uses it only when large
    use_file_api = is_video(audio_path) or file_size >= FILE_SIZE_THRESHOLD

    if use_file_api:
        file_uri = None
        try:
            file_uri = upload_to_file_api(api_key, audio_path, mime)
            result, model_used = call_gemini_file_uri(api_key, file_uri, mime, prompt)
        except Exception as e:
            result = f"❌ File API error: {e}"
            model_used = "gemini-2.5-flash"
        finally:
            if file_uri:
                delete_from_file_api(api_key, file_uri)
    else:
        with open(audio_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        result, model_used = call_gemini_inline(api_key, b64, mime, prompt)

    via = "FileAPI" if use_file_api else "inline"
    icon = "🎬" if is_video(audio_path) else "🎙"
    header = (
        f"{icon} Медиа: {file_info(audio_path)}\n"
        f"🤖 Модель: {model_used} [{via}]\n"
        f"⏱ {datetime.now().strftime('%H:%M:%S')}\n"
        f"{'─'*50}\n"
    )
    return header + result


def parse_batch(pattern, prompt=None):
    files = sorted(glob.glob(os.path.expanduser(pattern)))
    if os.path.isdir(pattern):
        exts = ('.ogg', '.mp3', '.wav', '.m4a', '.webm', '.opus',
                '.mp4', '.mov', '.mkv', '.avi', '.3gp')
        files = sorted([
            os.path.join(pattern, f) for f in os.listdir(pattern)
            if f.lower().endswith(exts)
        ])
    if not files:
        return f"❌ No audio files found matching: {pattern}"
    return "\n".join(parse_audio(f, prompt) + "\n" for f in files)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    mode = sys.argv[1]
    if mode == "batch":
        pattern = sys.argv[2] if len(sys.argv) > 2 else "~/.openclaw/media/inbound/"
        prompt = sys.argv[3] if len(sys.argv) > 3 else None
        print(parse_batch(pattern, prompt))
    else:
        print(parse_audio(mode, sys.argv[2] if len(sys.argv) > 2 else None))
