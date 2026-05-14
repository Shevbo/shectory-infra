---
name: image-gen
description: Генерация изображений через Google Imagen 4 API. Для создания UI-концептов, мокапов, визуальных референсов.
metadata: {"clawdbot":{"emoji":"🖼️","requires":{"bins":["python3","curl"]}}}
---

# image-gen — Генерация изображений (Imagen 4)

## Быстрый старт

```bash
python3 /home/shectory/skills/image-gen/gen.py "описание изображения"
# Вернёт путь к файлу: /tmp/imagen_<timestamp>.jpg
```

## Модели

| Модель | Скорость | Качество | Когда использовать |
|--------|----------|----------|--------------------|
| `imagen-4.0-fast-generate-001` | быстро | хорошо | черновики, итерации |
| `imagen-4.0-generate-001` | медленнее | отлично | финальные концепты |
| `imagen-4.0-ultra-generate-001` | медленно | максимум | презентационные |

## Python API напрямую

```python
import requests, base64, time, os

GEMINI_KEY = "YOUR_GEMINI_API_KEY"
PROXY = "http://USER:PASS@PROXY_HOST:PORT"

def generate_image(prompt: str, model: str = "imagen-4.0-fast-generate-001", count: int = 1) -> list[str]:
    """Генерирует изображения, возвращает список путей к файлам."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict?key={GEMINI_KEY}"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": count}
    }
    r = requests.post(url, json=payload, proxies={"https": PROXY, "http": PROXY}, timeout=60)
    r.raise_for_status()

    paths = []
    for i, pred in enumerate(r.json()["predictions"]):
        img_bytes = base64.b64decode(pred["bytesBase64Encoded"])
        path = f"/tmp/imagen_{int(time.time())}_{i}.jpg"
        with open(path, "wb") as f:
            f.write(img_bytes)
        paths.append(path)
    return paths
```

## Загрузка в Google Drive (для отправки Борису)

```bash
# После генерации загрузить в Drive папку shectory и получить ссылку:
FILE=/tmp/imagen_*.jpg
GOG_KEYRING_PASSWORD=openclaw GOG_ACCOUNT=bshevelev75@gmail.com \
  gog drive upload "$FILE" \
  --parent 1_4Yk7kpSs8FTNxbP4w0V1o301Vqa6mRa \
  -j | python3 -c "import json,sys; r=json.load(sys.stdin); print(r['webViewLink'])"
```

## Рабочий процесс GUIlya

1. Сформировать детальный prompt на английском (Imagen лучше работает с EN)
2. Сгенерировать `count=3` вариантов через `imagen-4.0-fast-generate-001`
3. Загрузить в Drive → получить 3 ссылки
4. Отправить Борису на выбор

## Советы по промптам для UI/UX

```
# Хорошие паттерны:
"mobile app UI, [экран/функция], [стиль: minimalist/material/glassmorphism], 
 clean design, [цветовая схема], [разрешение: high resolution mockup]"

# Примеры:
"mobile chat app UI with dark theme, bot conversation bubbles, minimalist design"
"dashboard UI wireframe, analytics charts, sidebar navigation, light theme"
"telegram mini app interface, group chat room, participant list, modern flat design"
```
