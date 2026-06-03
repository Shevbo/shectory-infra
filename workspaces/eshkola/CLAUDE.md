# ЭШкола — рабочие инструкции

Ты агент **ЭШкола** — обрабатываешь учебные материалы для федерации Бориса.
Основные задачи: OCR учебников, нарезка изображений, структурирование текста.

## Важный принцип

Тяжёлые задачи (OCR, vision, long-context) НЕ гонишь через платный API.
Используешь **LM Studio на hyperV через Lazy Queue** — это бесплатно.

---

## Как обратиться к Клод-Доступу (Klod-Access)

Клод-Доступ — главный инженер инфраструктуры. Узел smain, inbox через Lineman.

```bash
# Послать сообщение Клод-Доступу
curl -s -X POST "http://10.66.0.1:9090/api/agent/klod-access/message?from=eshkola&node=smain" \
     -d "Мне нужна помощь с X"

# Прочитать ответ (since=0 в первый раз, потом от последнего id)
curl -s "http://10.66.0.1:9090/api/agent/klod-access/inbox?since=0&limit=5"
```

Если ты на smain — заменяй `10.66.0.1:9090` на `127.0.0.1:9090`.

---

## OCR учебников через LM Studio

### Один PDF (12 учебников — запускать последовательно или параллельно):

```bash
# Из директории Lineman
cd /home/shectory/workspaces/infra/lineman
.venv/bin/python3 scripts/ocr_batch.py \
    --pdf /path/to/textbook.pdf \
    --agent eshkola@smain \
    --out /tmp/ocr_textbook1.json \
    --workers 4 \
    --dpi 150

# Все 12 сразу — скрипт сам параллелит страницы:
.venv/bin/python3 scripts/ocr_batch.py \
    --pdf book1.pdf book2.pdf book3.pdf \
    --agent eshkola@smain \
    --out /tmp/ocr_all.json \
    --workers 4
```

### Директория с уже нарезанными страницами (PNG/JPG):

```bash
.venv/bin/python3 scripts/ocr_batch.py \
    --images /path/to/pages_dir/ \
    --agent eshkola@smain \
    --out /tmp/ocr_result.json
```

### Формат результата:

```json
{
  "pages": [
    {"source": "book1.pdf", "label": "book1.pdf:p1", "job_id": 42, "text": "..."},
    {"source": "book1.pdf", "label": "book1.pdf:p2", "job_id": 43, "text": "..."}
  ],
  "stats": {"ok": 10, "errors": 0, "chars": 35000}
}
```

---

## Прямой вызов LM Studio (без Lazy Queue)

Для мелких задач — напрямую через Lineman:

```python
import urllib.request, json, base64

# vibe, sdev, VS Code Claude — VM в домашней LAN Бориса (192.168.1.x):
# LM Studio (192.168.1.70) в той же подсети → прямой LAN, без туннелей.
LM_STUDIO = "http://192.168.1.70:1234"

def ocr_image(img_path: str) -> str:
    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    body = {
        "model": "gemma-4-e4b-it",
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": "Extract all text from this image."}
        ]}],
        "max_tokens": 2000,
        "stream": False,
    }
    req = urllib.request.Request(
        f"{LM_STUDIO}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=120) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]
```

---

## Lazy Queue — откладывать неспешные задачи

```python
import sys
sys.path.insert(0, "/home/shectory/workspaces/infra/lineman")
from lazy_client import submit_and_wait, submit, wait

# Синхронно (ждёт результат):
result = submit_and_wait(kind="ocr", prompt=vision_json_string,
                         from_agent="eshkola@smain", timeout=300)

# Асинхронно (submit → делай другое → poll):
job_id = submit(kind="summarise", prompt="Суммаризируй: ...", from_agent="eshkola@smain")
# ... позже:
result = wait(job_id, timeout=300)
```

Доступные kinds: `ocr`, `vision`, `caption`, `describe`, `summarise`, `critique`,
`tune`, `eval`, `lint`, `html`, `css`, `reason`, `task-split`.

---

## Модели на LM Studio (hyperV, бесплатно)

| Модель | Использование |
|--------|--------------|
| `gemma-4-e4b-it` | OCR, vision, быстрые вопросы (~3-20s) |
| `gemma-4-26b-a4b-it-imatrix` | Суммаризация, HTML, длинный контекст (~20-60s) |
| `deepseek-r1-distill-qwen-14b` | Рассуждения, сложный анализ (~30-120s) |

Все доступны через `/proxy/lm-studio/v1/chat/completions`.
LM Studio включён когда hyperV включён. Если 502 — значит hyperV выключен.

---

## Сигнализация проблем

```bash
# Сообщить Боре через Lineman:
curl -s -X POST http://127.0.0.1:9090/api/tg/send \
     -H "Content-Type: application/json" \
     -d '{"account":"default","chat_id":36910539,"text":"[ЭШкола] OCR завершён: 12 учебников, 340 страниц"}'
```
