# Федерация Shectory — Справочник агентов

> Читай когда не знаешь кто что умеет или к кому обратиться.
> Не загружай автоматически — только по необходимости.

---

## 📜 МАНИФЕСТ ФЕДЕРАЦИИ (обязателен для всех агентов)

**Правило 1. Прямое обращение = мгновенный ответ.**

Если агент А обращается к агенту Б напрямую (через `sessions_send`, API, Telegram,
вызов навыка), агент Б обязан:
- **немедленно получить уведомление** о входящем запросе
- **ответить без задержки** — даже если ответ "принял, работаю" или "нужно время"
- При невозможности ответить сразу — сообщить когда сможет

**Правило 2. Тяжёлые тексты и файлы — через Inbox.**

Если нужно передать другому агенту:
- длинный текст (>1000 слов)
- файл, архив, изображение
- любой бинарный или объёмный контент

→ **Не отправлять напрямую.**
→ Сохранить в директорию Inbox получателя.
→ Отправить **ссылку/уведомление через API**:

```
# smain: положить файл в инбокс агента на любом хосте
# (для агентов на smain: ~/workspaces/inbox/<agent_id>/)
cat task.md > ~/workspaces/inbox/tank/TASK_1744819200.md

# Уведомить через Keymaster API
curl "http://127.0.0.1:9093/inbox/notify?..."

# ИЛИ напрямую через sessions_send (короткое сообщение)
sessions_send(sessionKey, "Задача в инбоксе: TASK_1744819200.md")
```

**Правило 3. Каждый агент проверяет свой Inbox при старте и по heartbeat.**

Это обязанность, а не опция. Inbox — единственный гарантированный канал
для нетривиальных данных.

**Правило 4. Все ключи/токены/пароли — только через Ключник.**

Никогда не хардкодить, не публиковать, не передавать. Ключник знает где лежит
секрет, но никогда не выдаёт его значение.

**Нарушение любого правила = доклад Борису.**

---

## 🔴 ДОРОГИЕ LLM — СТРОГО ПО СОГЛАСОВАНИЮ С БОРИСОМ

**Следующие провайдеры очень дорогие. Использовать ТОЛЬКО при явном указании Бориса:**

| Провайдер | Модели | Примерная стоимость |
|-----------|--------|---------------------|
| **Anthropic** (`anthropic/*`) | claude-sonnet-4-6, claude-opus-4-7 | $3–75 за M токенов |
| **OpenAI** (`openai/*`) | gpt-4o, gpt-4.1, o3, o4-mini | $1–40 за M токенов |
| **OpenRouter** (`openrouter/*`) | любые платные | варьируется |

**Дешёвые / разрешённые без согласования:**
- `deepseek/deepseek-v4-flash` — основная рабочая модель
- `google/gemini-2.5-flash` — быстрая, дешёвая
- `anthropic/claude-haiku-4-5-20251001` — дешёвый Claude (~$0.8/M)
- `openai/gpt-4o-mini` — дешёвый GPT (~$0.15/M)

> Если Борис не сказал явно "используй GPT-4o" / "используй Opus" / "используй OpenAI" —
> **не используй дорогие провайдеры**. По умолчанию: deepseek или gemini-flash.

---

## 🟢 БЕСПЛАТНЫЕ ЛОКАЛЬНЫЕ МОДЕЛИ — LM Studio (hyperv)

**Приоритет выше платных.** Используй локальные модели по умолчанию для задач, которые не требуют точности уровня GPT-4o.

| Модель | Эндпоинт (через Lineman) | Эндпоинт (vibe прямой) | Задачи |
|--------|--------------------------|------------------------|--------|
| `gemma-4-e4b-it` | `/proxy/lm-studio/v1/chat/completions` | `http://192.168.1.70:1234/v1/...` | OCR, vision, быстрые вопросы |
| `gemma-4-26b-a4b-it-imatrix` | то же | то же | Суммаризация, HTML, длинный контекст |
| `deepseek-r1-distill-qwen-14b` | то же | то же | Рассуждения, сложный анализ |

**Адреса:**
- Все узлы (smain, sdev, hoster, pi): `http://10.66.0.1:9090/proxy/lm-studio/v1/...`
- **vibe (Windows)** — прямой LAN: `http://192.168.1.70:1234/v1/...` (CCR_LMSTUDIO_URL из keymaster, быстрее)

**Доступность:** LM Studio работает пока hyperv включён. Если `502` — hyperv выключен. Lazy Queue автоматически фолбэкнет на Ollama@hoster или DeepSeek-flash.

### Lazy Queue — batch и неспешные задачи через local LLM

```bash
# HTTP из любого агента:
curl -s -X POST http://10.66.0.1:9090/api/queue/lazy \
  -H "Content-Type: application/json" \
  -d '{"kind":"ocr","from_agent":"агент@нода","from_node":"нода",
       "user_prompt":"[{\"type\":\"image_url\",...},{\"type\":\"text\",\"text\":\"Extract text\"}]",
       "max_tokens":2000,"priority":2}'

# Забрать результат:
curl http://10.66.0.1:9090/api/queue/lazy/<job_id>
```

```python
# Python (на smain — path /home/shectory/workspaces/infra/lineman):
import sys; sys.path.insert(0, "/home/shectory/workspaces/infra/lineman")
from lazy_client import submit_and_wait, submit, wait
import json, base64

# Vision/OCR — user_prompt ОБЯЗАТЕЛЬНО JSON-массив:
img_b64 = base64.b64encode(open("page.png","rb").read()).decode()
vision_parts = [
    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
    {"type": "text", "text": "Extract all text from this page."},
]
text = submit_and_wait(kind="ocr", prompt=json.dumps(vision_parts),
                       from_agent="агент@нода", max_tokens=2000, timeout=300)
```

**Доступные kinds:** `ocr | vision | caption | describe | summarise | critique | tune | eval | lint | html | css | reason | task-split`
Суффикс `:terse` → сжатый ответ (-65% output).
**Параллельность:** 4 воркера одновременно, LM Studio загружается на полную.

### Batch-OCR PDF/изображений (ЭШкола и другие)

```bash
ssh smain "cd /home/shectory/workspaces/infra/lineman && \
  .venv/bin/python3 scripts/ocr_batch.py \
  --pdf /путь/к/book.pdf \
  --agent <агент>@<нода> \
  --out /tmp/result.json \
  --workers 4"
```

---

## 🔴 MUST: СЕТЕВОЕ ПРАВИЛО — ЕДИНСТВЕННЫЙ СТАНДАРТ ФЕДЕРАЦИИ

**ЕДИНСТВЕННЫЙ прокси для всех агентов и сервисов — smain Lineman.**
**Любой другой прокси (Proxy6, iProyal напрямую, SSH-туннели) — ЗАПРЕЩЁН.**

| Хост | Адрес прокси | Способ |
|------|-------------|--------|
| smain (shectory-work) | `http://127.0.0.1:9090` | локально |
| sdev, hoster, cloud, pi | `http://10.66.0.1:9090` | WireGuard → smain |
| **vibe (VBoris2)** | **`http://127.0.0.1:19090`** | SSH reverse tunnel → smain |

Это касается: кода агентов, VS Code (`http.proxy` + `remote.env`), `.bashrc`, системных сервисов, docker-compose, `.env` файлов.

**ЗАПРЕЩЕНО** напрямую обращаться к:
- `api.telegram.org`
- `generativelanguage.googleapis.com`
- `api.deepseek.com`
- `api.anthropic.com`
- любым внешним API без прокси

### Как использовать прокси в коде

**Python (urllib.request):**
```python
import urllib.request

LINEMAN = "http://127.0.0.1:9090"  # на smain; на других хостах: http://10.66.0.1:9090
proxy = urllib.request.ProxyHandler({"http": LINEMAN, "https": LINEMAN})
opener = urllib.request.build_opener(proxy)
with opener.open(request, timeout=15) as r:
    data = r.read()
```

**bash/curl:**
```bash
curl --proxy http://127.0.0.1:9090 https://api.telegram.org/bot.../sendMessage
```

**Python (requests):**
```python
proxies = {"http": "http://127.0.0.1:9090", "https": "http://127.0.0.1:9090"}
response = requests.get(url, proxies=proxies)
```

**OpenClaw (openclaw.json) для удалённых хостов:**
```json
"models": {
  "providers": {
    "google":   { "baseUrl": "http://10.66.0.1:9090/proxy/google" },
    "deepseek": { "baseUrl": "http://10.66.0.1:9090/proxy/deepseek" }
  }
}
```

### Куда класть export (важно — non-interactive шеллы)

| Файл | Когда читается | Класть `HTTPS_PROXY`? |
|------|----------------|----------------------|
| `~/.profile` | login shell (ssh, cron с `-l`, VS Code Server при старте) | **ДА — основной** |
| `~/.bashrc` | interactive non-login (терминал внутри tmux) | Опционально, но `.profile` уже сорсит `.bashrc` |
| `~/.bash_profile` | если существует — перекрывает `.profile` | Лучше не плодить |

**Стандартный Ubuntu `.bashrc`** имеет в начале guard `case $- in *i*) ;; *) return;; esac` — non-interactive шеллы (`bash -c`, cron, VS Code Server) выходят до экспортов. Поэтому **HTTPS_PROXY ставится в `~/.profile`**, иначе claude CLI, cron-джобы и VS Code будут ходить без прокси и натыкаться на гео-блок / на iProyal с динамическим egress IP.

```bash
# ~/.profile хвост — на всех узлах federation
export HTTPS_PROXY=http://10.66.0.1:9090   # на smain: http://127.0.0.1:9090
export HTTP_PROXY=http://10.66.0.1:9090
export NO_PROXY=localhost,127.0.0.1,10.66.0.0/24
```

### VS Code Server на удалённых узлах

`~/.vscode-server/data/Machine/settings.json`:
```jsonc
{
  "http.proxy": "http://10.66.0.1:9090",
  "http.proxyStrictSSL": false,
  "claudeCode.environmentVariables": [
    {"name": "HTTPS_PROXY", "value": "http://10.66.0.1:9090"},
    {"name": "HTTP_PROXY",  "value": "http://10.66.0.1:9090"},
    {"name": "NO_PROXY",    "value": "localhost,127.0.0.1,10.66.0.0/24"}
  ]
}
```

Скрипт `~/scripts/vscode-proxy-sync.py` (на sdev и др.) поддерживает этот файл. **Запрещено** подставлять туда прямой `$LINEMAN_IPROYAL_URL` — egress IP сдева нестабильный, iProyal даст 403 на половине запросов.

### Журнал инфра-фиксов

| Дата | Узел | Что исправлено |
|------|------|----------------|
| 2026-05-29 | sdev | `vscode-proxy-sync.py` переписан: пишет `http://10.66.0.1:9090` (Lineman через WG), а не `$LINEMAN_IPROYAL_URL`. Добавлен HTTPS_PROXY-блок в `~/.profile`. Причина: egress IP sdev динамический (CGNAT: `134.255.210.31` / `2.63.176.183` чередуются), whitelist одного IP в iProyal даёт `403 CONNECT` на части запросов. Lineman принимает CONNECT и форвардит через iProyal от фиксированного smain IP. |

---

## 🔑 ПРОТОКОЛ БЕЗОПАСНОСТИ — ОБЯЗАТЕЛЕН ДЛЯ ВСЕХ АГЕНТОВ

### Правило секретов (нарушение = красная линия)

1. **Никогда не выводить значения ключей/токенов/паролей** в чат, лог, файл, память
2. **Никогда не передавать секреты другим агентам** в сообщениях или задачах
3. **Для получения метаданных** (имя переменной, путь к файлу) — обращаться к Ключнику

### Как обратиться к Ключнику

```bash
# Узнать где лежит ключ
python3 ~/keymaster/keymaster.py --requester <твой_agent_id> query GEMINI_API_KEY

# Список всех секретов (только имена)
python3 ~/keymaster/keymaster.py --requester <твой_agent_id> list
```

Ключник вернёт: имя env-переменной, путь к файлу, назначение — и **уведомит Бориса**.

### Как использовать ключи в коде

```python
# ПРАВИЛЬНО: читать из окружения
import os
api_key = os.environ.get("GEMINI_API_KEY")

# ПРАВИЛЬНО: читать из файла по пути из Ключника
with open(os.path.expanduser("~/.openclaw/credentials/some-token")) as f:
    token = f.read().strip()

# ЗАПРЕЩЕНО: хардкодить значение
api_key = "AIzaSy..."  # ← НИКОГДА
```

### Доступ к ~/.keymaster/

Директория `~/.keymaster/` доступна только Ключнику и Борису.
Другие агенты **не должны** читать эту директорию напрямую.

### Keymaster API (HTTP) — для всех агентов на всех хостах

Все агенты федерации (включая VBoris2 на vibe, Hoster, Shopin,
TankDev и др.) могут запрашивать метаданные секретов через HTTP.

**Базовый URL:**

| Откуда | Адрес |
|--------|-------|
| smain (локально) | `http://127.0.0.1:9093` |
| sdev, hoster, cloud, vibe/pi (WireGuard) | `http://10.66.0.1:9093` |

**Эндпоинты:**

```
GET /health                              → проверка связи
GET /keymaster/list?requester=<agent_id>  → список имён секретов
GET /keymaster/query?name=<SECRET>&requester=<agent_id>  → метаданные
```

**Параметр `requester` — обязателен.** Используй свой Agent ID:

| Агент | ID |
|-------|-----|
| VBoris2 (vibe) | `virtual-boris` |
| Tank (smain) | `tank` |
| Selfcoder (smain) | `selfcoder` |
| QAper (smain) | `qaper` |
| Hoster | `hoster` |
| Shopin | `shopin` |
| ResumeWriter | `resumewriter` |
| TankDev (sdev) | `tank-dev` |
| Tank 3 (cloud) | `tank-3` |

**Формат ответа:**

```json
{
  "secret": "GEMINI_API_KEY",
  "env_var": "GEMINI_API_KEY",
  "file_path": "~/.openclaw/credentials/gemini-api-key",
  "purpose": "Gemini API для голосовых и текстовых моделей",
  "requester": "virtual-boris"
}
```

**Важно:**
- Ответ содержит **только метаданные** — имя env-переменной и/или путь к файлу
- Значения секретов **никогда** не передаются
- Каждый запрос аудитируется в `~/.keymaster/audit.log`
- Борис получает уведомление о каждом запросе в Telegram

**Пример для VBoris2 (через curl с vibe/Windows):**
```bash
curl http://10.66.0.1:9093/keymaster/list?requester=virtual-boris
curl "http://10.66.0.1:9093/keymaster/query?name=GEMINI_API_KEY&requester=virtual-boris"
```

**Пример для скрипта/кода (любой язык):**
```bash
# Bash
curl -s "http://127.0.0.1:9093/keymaster/query?name=OPENAI_API_KEY&requester=selfcoder" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ENV:', d.get('env_var'))"
```

```python
# Python
import json, urllib.request
url = "http://127.0.0.1:9093/keymaster/list?requester=selfcoder"
with urllib.request.urlopen(url, timeout=10) as r:
    data = json.loads(r.read())
    print(data["secrets"])
```

---

## Агенты федерации

### smain — shectory-work (10.66.0.1, alias: smain)

Главный сервер. Lineman здесь на :9090.

| Агент | ID | Навыки | Когда обращаться |
|-------|-----|--------|-----------------|
| Tank 🛠️ | main | Оркестрация, subagents, Google Drive, изображения, встречи | Главный. Все задачи от Бориса сначала сюда. Распределяет между агентами. |
| Selfcoder ⚡ | selfcoder | Написание кода, рефакторинг | Написать/исправить код. Перед кодом читает `~/workspaces/qaper/qa-knowledge-base.json`. |
| QAper 🔍 | qaper | Тестирование, поиск багов, qa-knowledge-base | Написать тесты, проверить код. Ведёт базу повторяющихся ошибок. |
| Virtual Boris 🧠 | virtual-boris | Браузерная автоматизация, интернет-поиск | Исследовать сайты, автоматизировать браузер. |
| Titan 🏋️ | titan | Фитнес, нутрициология, Polar V800, ЧСС-зоны | Тренировки Бориса, питание, данные Polar. Борис 92→87 кг, колено — бег запрещён. |
| Медсестра 🩺 | nurse | Психологическая поддержка, здоровье | Поддержка Бориса и семьи. Говорит от женского лица. Не ставит диагнозов. |
| GUIlya 🎨 | guilya | UI/UX дизайн, Google Slides | Дизайн интерфейсов. Всегда 3 варианта, новый слайддек на каждый уровень. |
| JobScanner 🔎 | jobsearch-scanner | Поиск вакансий, web scraping | Мониторинг вакансий, парсинг. |
| ResumePro 📄 | resume-editor | Адаптация резюме, карьерные материалы | Резюме Бориса под конкретную вакансию языком работодателя. |
| InterviewCoach 🎯 | interview-coach | Подготовка к собеседованиям | Тренировка интервью, разбор вопросов. |
| Inbox 📥 | inbox | Входящие сообщения | Входящие для Tank. |
| **Ключник 🔑** | **keymaster** | **Реестр секретов — метаданные** | **Нужно узнать имя env-переменной или путь к ключу. Значения не выдаёт.** |

### sdev — cursorrpa (10.66.0.4, user: shevbo)

Dev-ветка. Тест новых фич OpenClaw и агентов.
⚠️ **Личный ПК Бориса — может быть выключен.** Не полагаться как на стабильный хост.

| Агент | ID | Роль |
|-------|-----|------|
| TankDev 🛠️ | tank-dev | Клон Tank для тестирования. Бот: @ShectoryTankTestBot |
| Selfcoder ⚡ | selfcoder-sdev | Dev-ветка кодера |
| QAper 🔍 | qaper-sdev | Dev-ветка QA |

### hoster — 83.69.248.175 (10.66.0.7, user: ubuntu)

Хостинг git-репозиториев и сервисов.

| Агент | ID | Роль |
|-------|-----|------|
| Hoster 🏠 | main | Управление репозиториями, деплой |
| Inbox 📥 | inbox | Входящие hoster |
| Shopin 🛒 | shopin | Шопинг-ассистент |
| ResumeWriter ✍️ | resumewriter | Редактор резюме |

### vibe — Windows PC (192.168.1.64 / 10.66.0.6, user: boris)

Windows 10/11. OpenClaw node.

| Агент | Federation ID | Local OpenClaw ID | Роль |
|-------|--------------|-------------------|------|
| VBoris2 🧠 | virtual-boris-vibe | vboris2 | Виртуальный ассистент Бориса на Windows |
| Inbox 📥 | inbox | inbox | Входящие vibe |

**VBoris2 — доступ к Lineman API:**
- Lineman на smain доступен через SSH reverse tunnel: **`http://127.0.0.1:19090`**
- Туннель автоматически поддерживается PM2 процессом `vibe-tunnel` на smain
- Пример: `curl --noproxy "*" "http://127.0.0.1:19090/api/agent/keymaster/message?from=virtual-boris-vibe&message=ping"`
- **Важно:** использовать `--noproxy "*"` чтобы обойти прокси-конфиг openclaw

**LM Studio — прямой LAN-доступ с vibe (быстрее, чем через Lineman):**
- URL: `http://192.168.1.70:1234` (секрет `CCR_LMSTUDIO_URL` в keymaster)
- Модель OCR/vision: `gemma-4-e4b-it`
- Пример: `POST http://192.168.1.70:1234/v1/chat/completions` с `Authorization: Bearer local`
- Если hyperv выключен — фолбэк через `http://127.0.0.1:19090/proxy/lm-studio/...`

**Секреты для VBoris2:**
- Keymaster API: `http://127.0.0.1:19090/api/agent/keymaster/message?from=virtual-boris-vibe&message=...`
- После получения env-переменной — читать из локального окружения vibe

### cloud — shevbo-cloud (10.66.0.3, user: shevbo) — стабильный VPS

OpenClaw node. Обычно доступен (не зависит от Бориса).

| Агент | Federation ID | Local OpenClaw ID | Роль |
|-------|--------------|-------------------|------|
| Tank 3 ⚡ | tank-3 | main | Основной агент cloud (Gemini-2.5-flash) |

**Клод 3 (Executive Advisor на cloud):**
```bash
# Из smain или любого хоста — спросить Клода 3
ssh cloud '~/scripts/ask-claude.sh "Вопрос"'

# Задача через inbox
ssh cloud 'cat > ~/workspaces/claude-inbox/TASK_$(date +%s)_SMAIN.md' << 'EOF'
Тело задачи...
EOF
```

**Доступ к Lineman с cloud:**
- Lineman на smain: `http://10.66.0.1:9090`
- Keymaster API: `http://10.66.0.1:9093`

**Связь cloud → smain агенты:**
```bash
curl "http://10.66.0.1:9090/api/agent/main/message?from=tank-3&message=ping"
```

### sdev — cursorrpa (10.66.0.4, user: shevbo)

⚠️ **Личный ПК Бориса — может быть выключен.** Не полагаться как на стабильный хост.

### smarthome — Windows VM (WireGuard: TBD, user: Boris)

Windows VM. Codex + OpenSSH. Проект **Boris Home 2.0** — умный дом Бориса.

| Агент | Federation ID | Роль |
|-------|--------------|------|
| Claude-SmartHome 🏠 | smarthome | Умный дом: сценарии, устройства, автоматизации, Home Assistant |

**Скилы SmartHome:**
- Управление умным домом (Home Assistant / Z-Wave / Zigbee)
- Сценарии освещения, климата, охраны
- Интеграция с голосовыми ассистентами (Алиса)
- Бытовая техника, уведомления по событиям дома

**SmartHome → остальная федерация (через smain):**
```bash
# Из Windows PowerShell/SSH — обращение к любому агенту
ssh smain "curl -s 'http://127.0.0.1:9090/api/agent/main/message?from=smarthome&message=текст'"

# Задача для Claude Code (smain)
ssh smain "cat > /home/shectory/workspaces/claude-inbox/TASK_\$(date +%s)_SH.md" << 'EOF'
# Задача от SmartHome
<текст>

## Callback
session_key: agent:main:telegram:direct:36910539
EOF
```

**Федерация → SmartHome (входящие):**

SmartHome читает inbox-папку на smain:
```
/home/shectory/workspaces/smarthome-inbox/
```

Любой агент пишет туда файл:
```bash
cat > /home/shectory/workspaces/smarthome-inbox/MSG_$(date +%s)_from_main.md << 'EOF'
<сообщение>
EOF
```

SmartHome забирает через SSH:
```powershell
# PowerShell — проверить inbox
ssh smain "ls /home/shectory/workspaces/smarthome-inbox/"

# Забрать и удалить файл
ssh smain "cat /home/shectory/workspaces/smarthome-inbox/MSG_*.md && rm /home/shectory/workspaces/smarthome-inbox/MSG_*.md"
```

**Подключение к WireGuard:**
После настройки WG на Windows VM — добавить IP в эту таблицу и в `REMOTE_SSH_CONFIG` в `proxy_server.py`.



### windows-vm — Claude-SiteCloner (192.168.1.50, user: boris)

Добавлен: 2026-05-25

| Агент | Federation ID | Роль |
|-------|--------------|------|
| Claude-SiteCloner | site-cloner | Клонирование сайтов — анализ, воспроизведение UI/UX, парсинг структуры |

**Навыки:** HTML/CSS/JS парсинг, Playwright, скриншоты, воспроизведение дизайна, Next.js/React клоны

**Входящие (из smain):**
```bash
cat > /home/shectory/workspaces/site-cloner-inbox/MSG_$(date +%s)_from_SENDER.md << 'EOF'
<сообщение>
EOF
```

**Claude-SiteCloner → федерация:**
```bash
ssh smain "curl -s 'http://127.0.0.1:9090/api/agent/main/message?from=site-cloner&message=TEXT'"
```

### sdev — Claude-ShectoryFix (10.66.0.4, user: shevbo)

Добавлен: 2026-05-26

| Агент | Federation ID | Роль |
|-------|--------------|------|
| Claude-ShectoryFix | shectoryfix | Реализация Censor Autopilot — автономная система обнаружения аномалий, Opus root-cause анализ, авто-патчинг конфигов |

**Навыки:** Python, cron, Lineman API, OpenClaw конфиги, git, pytest, Claude CLI

**Входящие (из smain):**
```bash
cat > /home/shectory/workspaces/shectoryfix-inbox/MSG_$(date +%s)_from_SENDER.md << 'EOF'
<сообщение>
EOF
```

**Claude-ShectoryFix → федерация:**
```bash
ssh smain "curl -s 'http://127.0.0.1:9090/api/agent/main/message?from=shectoryfix&message=TEXT'"
```
### pi, pi2 — резервные хосты

Пустые / минимальная конфигурация. Агентов нет.

---

## 🖥️ Keymaster API service

Keymaster API — HTTP-сервер на smain, порт 9093.
Обслуживает запросы от всех агентов федерации.
Управление:

```bash
# Запуск
pm2 start ~/keymaster/api_server.py --name keymaster-api --interpreter python3 -- --port 9093 --bind 0.0.0.0

# Статус
pm2 status keymaster-api

# Логи
pm2 logs keymaster-api --lines 20

# Рестарт
pm2 restart keymaster-api
```

---

## Как связаться с другим агентом

### 📡 Быстрые запросы — через Lineman Agent API (рекомендовано)

**Единый API для всей федерации.** Отправляет сообщение любому агенту — локальному или удалённому — через Lineman на :9090.

```
GET http://127.0.0.1:9090/api/agent/{federation_agent_id}/message?from={my_id}&message={text}
```

| Параметр | Описание |
|----------|----------|
| `{federation_agent_id}` | Federation ID агента-получателя (см. таблицы ниже) |
| `from` | Твой Federation ID |
| `message` | Текст сообщения (URL-encoded) |

**Примеры:**

```bash
# Написать VBoris2 на vibe (из smain)
curl "http://127.0.0.1:9090/api/agent/virtual-boris-vibe/message?from=tank&message=Привет+от+Танка"

# Написать Tank 3 на cloud
curl "http://127.0.0.1:9090/api/agent/tank-3/message?from=tank&message=Привет+от+Tank"

# Написать Keymaster
curl "http://127.0.0.1:9090/api/agent/keymaster/message?from=selfcoder&message=list_secrets"

# С других хостов (cloud, sdev, vibe, hoster) — тот же URL с WireGuard IP
curl "http://10.66.0.1:9090/api/agent/main/message?from=tank-3&message=ping"
```

**Формат ответа (успех):**

```json
{
  "runId": "...",
  "status": "ok",
  "result": { "payloads": [{ "text": "ответ агента" }] }
}
```

**Формат ответа (ошибка):**

```json
{
  "status": "error",
  "message": "Agent 'X' not found in federation.",
  "stdout": "...",
  "stderr": "..."
}
```

**Как работает маршрутизация:**
- Агенты на **smain** → вызов через `openclaw agent --agent <id> --json` локально
- Агенты на **vibe/sdev/hoster** → вызов через SSH + `openclaw agent --agent <id> --json`
- Federation ID → Local OpenClaw ID маппинг задан в `REMOTE_SSH_CONFIG` в `proxy_server.py`

**Варианты прямого обращения (дополнительные):**

| Способ | Когда использовать |
|--------|-------------------|
| Lineman API (выше) | **Основной способ** — любой агент, любой хост |
| `sessions_send` | Другой агент на том же хосте OpenClaw (legacy) |
| Telegram-бот агента | Другой агент на любом хосте (если есть бот) |
| `~/scripts/ask-claude.sh` | Вопрос к Executive Advisor (Клод) |

### 📦 Тяжёлые данные — через Inbox + ссылка

Если нужно передать:
- длинный текст (>1000 слов)
- файл, архив, изображение
- любой объёмный/бинарный контент

**Порядок действий:**
1. Сохранить файл в директорию Inbox получателя
2. Отправить короткое уведомление через прямой канал (sessions_send / Telegram / API)

**Пути Inbox для каждого хоста:**

| Хост | Путь Inbox |
|------|-----------|
| smain | `~/workspaces/inbox/<agent_id>/` |
| hoster | `~/workspaces/inbox/<agent_id>/` |
| vibe | `~/workspaces/inbox/<agent_id>/` |
| sdev | `~/workspaces/inbox/<agent_id>/` |

**Формат файла задачи:**

```bash
cat > ~/workspaces/inbox/tank/TASK_$(date +%s).md << 'EOF'
От: [имя агента / agent_id]
Тема: [кратко]
Приоритет: высокий/средний/низкий
Тип: вопрос/задача/файл/отчёт

Тело задачи...
EOF
```

### ⚠️ Важно: ответ обязателен

При получении любого обращения (прямого или через Inbox) агент обязан:
1. **Подтвердить получение** (в течение 1 минуты)
2. **Оценить срок выполнения**
3. **Выполнить или передать дальше**

Игнорирование входящих запросов = нарушение манифеста федерации.

---

---

## 📧 Почтовый сервер shectory.ru

**Сервер:** Poste.io (Postfix + Dovecot + Rspamd) в Docker на smain.
**Домен:** `shectory.ru`
**Управление:** `~/mail-poste/` на smain, данные в `~/mail-poste/data/`

### Существующие ящики

| Адрес | Назначение |
|-------|-----------|
| admin@shectory.ru | Суперадмин |
| openclaw@shectory.ru | OpenClaw gateway |
| portal@shectory.ru | Shectory Portal |
| qaper@shectory.ru | QAper агент |
| bshevelev@shectory.ru | Борис |
| claude-test@shectory.ru | Claude Garden (тест) |

### Как создать новый ящик (программно)

Вставить запись напрямую в SQLite — самый надёжный способ для агентов:

```python
import sqlite3, datetime, crypt

DB = '/home/shectory/mail-poste/data/users.db'  # на smain
# Если ты не на smain — скопируй через SSH или выполни через ssh smain

def create_mailbox(address: str, password: str, display_name: str = ''):
    pw_hash = '{SHA512-CRYPT}' + crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute('SELECT address FROM users WHERE address=?', (address,))
    if cur.fetchone():
        print(f'Already exists: {address}')
        conn.close()
        return
    username = address.split('@')[0]
    domain = address.split('@')[1]
    cur.execute('''
        INSERT INTO users
        (address, username, password, home, uid, gid, name,
         disabled, domainAdmin, superAdmin, strictFromDisabled,
         created, discard, internalOnly, domainName)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        address, username, pw_hash,
        f'/data/domains/{domain}/{username}',
        5000, 5000, display_name or username,
        False, False, False, False,
        datetime.datetime.now().isoformat(),
        False, False, domain
    ))
    conn.commit()
    conn.close()
    print(f'Created: {address}')

create_mailbox('myagent@shectory.ru', 'SecurePassword123', 'My Agent')
```

Из другого хоста (не smain) — через SSH:
```bash
ssh smain python3 - << 'PYEOF'
import sqlite3, datetime, crypt
# ... тот же код ...
PYEOF
```

### Как отправить письмо (SMTP)

Порт **587** (STARTTLS) — аутентифицированная отправка:

```python
import smtplib
from email.mime.text import MIMEText

def send_email(from_addr, password, to_addr, subject, body):
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = subject

    s = smtplib.SMTP('mail.shectory.ru', 587, timeout=15)
    # Если с smain — можно использовать 127.0.0.1:587
    s.starttls()
    s.login(from_addr, password)
    s.sendmail(from_addr, [to_addr], msg.as_string())
    s.quit()

send_email(
    'myagent@shectory.ru', 'SecurePassword123',
    'user@gmail.com',
    'Тема письма',
    'Текст письма'
)
```

Bash (через curl/swaks — если установлен):
```bash
swaks --to user@gmail.com \
      --from myagent@shectory.ru \
      --server mail.shectory.ru:587 \
      --tls \
      --auth LOGIN \
      --auth-user myagent@shectory.ru \
      --auth-password SecurePassword123 \
      --header "Subject: Тема" \
      --body "Текст"
```

### Как читать входящие (IMAP)

Порт **993** (SSL/TLS):

```python
import imaplib, email

def read_inbox(mailbox_addr, password, count=10):
    m = imaplib.IMAP4_SSL('mail.shectory.ru', 993)
    m.login(mailbox_addr, password)
    m.select('INBOX')
    _, ids = m.search(None, 'ALL')
    for uid in ids[0].split()[-count:]:
        _, data = m.fetch(uid, '(RFC822)')
        msg = email.message_from_bytes(data[0][1])
        print(f"From: {msg['From']}")
        print(f"Subject: {msg['Subject']}")
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    print(part.get_payload(decode=True).decode())
        else:
            print(msg.get_payload(decode=True).decode())
    m.logout()

read_inbox('myagent@shectory.ru', 'SecurePassword123')
```

### Параметры подключения

| Протокол | Хост | Порт | Шифрование |
|----------|------|------|-----------|
| SMTP (отправка) | mail.shectory.ru | 587 | STARTTLS |
| SMTP (отправка) | mail.shectory.ru | 465 | SSL/TLS |
| IMAP (чтение) | mail.shectory.ru | 993 | SSL/TLS |
| Веб-админка | mail.shectory.ru/admin | 443 | HTTPS |

С smain можно использовать `127.0.0.1` вместо `mail.shectory.ru`.

---

### Claude в Telegram (cc-bot — smain)

Прямой диалог с Claude через Telegram. Персональный бот Бориса.
Знает всю инфраструктуру, проекты, федерацию. История диалога не теряется.

**Команды:** `/remember <факт>` `/forget` `/notes` `/clear`
**Модель:** claude-sonnet-4-6
**Файл конфига:** `/home/shectory/workspaces/infra/cc-bot/context.md`

---

### Executive Advisors (Клод 2 и Клод 3)

Два инстанса Claude Code. Оба — арбитры над всей федерацией.

**Клод 2 (smain — всегда доступен):**
```bash
~/scripts/ask-claude.sh "Вопрос"
```

**Клод 3 (shevbo-cloud — обычно доступен, стабильный VPS):**
```bash
ssh cloud '~/scripts/ask-claude.sh "Вопрос"'
```

**Задача с файлом:**
```bash
# Для Клода 2
cat > ~/workspaces/claude-inbox/TASK_$(date +%s)_AGENT.md << 'EOF'
Тело...
EOF

# Для Клода 3
ssh cloud 'cat > ~/workspaces/claude-inbox/TASK_$(date +%s)_AGENT.md' << 'EOF'
Тело...
EOF
```
