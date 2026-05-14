# Федерация Shectory — Карта связности
Версия: 2026-05-13 (обновлено: Lineman dashboard + reverse proxy)

## ⚖️ Иерархия

```
Tank 🛠️ (CTO, smain)
├── Shectory Dev (софт-разработка)
│   ├── Selfcoder ⚡ — пишет код
│   ├── Qaper 🔍 — тестирует
│   └── TankDev 🛠️ — CTO-дублёр (sdev)
├── Job Search (поиск работы)
│   ├── JobScanner 🔎 — сканирует вакансии
│   ├── ResumePro 📄 — адаптирует резюме
│   └── InterviewCoach 🎯 — готовит к собеседованиям
├── Personal (личные ассистенты)
│   ├── VirtualBoris 🧠 — мамина связь (smain)
│   ├── VBoris2 🧠 — цифровой дублёр (vibe)
│   ├── Nurse 🩺 — психподдержка (smain)
│   ├── GUIlya 🎨 — дизайн (smain)
│   ├── Titan 🏋️ — фитнес (smain)
│   ├── Shopin 🛒 — шопинг-разведчик (hoster)
│   └── Inbox 📥 — секретарь (везде)
├── Infrastructure (инфраструктура)
│   ├── Hoster 🏠 — git-репозитории (hoster)
│   ├── Lineman 🔌 — Cloudflare-коммуникации (hoster)
│   └── Медсестра 🩺 — voice.shectory.ru (smain)
└── Executive Advisory
    └── Клод 🤖 — арбитр (недоступен, 403)
```

---

## 0. Мониторинг федерации

**Дашборд:** [https://dashboard.shectory.ru](https://dashboard.shectory.ru) — Basic Auth: `boris` / *htpasswd*

Показывает SVG-карту топологии в реальном времени: агенты smain → Lineman → внешние сервисы.
Анимированные пакеты отображают каждый LLM-запрос. Клик по агенту → история сигналов + описание.

**Lineman** — умный прокси-шлюз, работает на smain `127.0.0.1:9090`.
- Все LLM-запросы OpenClaw идут через него (`baseUrl = http://127.0.0.1:9090/proxy/{provider}`)
- Считает токены из тел запросов/ответов в реальном времени
- Хранит все запросы в SQLite (`lineman.db`: таблицы `request_log` + `signals`)
- API: `/health`, `/api/nodes`, `/api/signals`, `/api/log/stats`

Полная документация: `workspaces/lineman/WIKI.md`

---

## 1. Хосты и доступ к ним

### smain (83.69.248.77) — главный сервер
```
WG IP:   10.66.0.1
SSH:     ssh shectory@83.69.248.77 (ключ ~/.ssh/id_ed25519)
OpenClaw: bind=lan, порт 18789
Статус:  ✅ Gateway UP
```

### sdev — сервер разработки (CursorRPA)
```
WG IP:   10.66.0.4
SSH:     ssh sdev (через ~/.ssh/config)
OpenClaw: bind=lan, порт 18789
Статус:  ✅ Gateway UP (systemd inactive, но процесс работает)
```

### vibe (192.168.1.64) — Windows-узел
```
WG IP:   10.66.0.6
SSH:     ssh vibe (ключ ~/.ssh/id_ed25519)
OpenClaw: node, gateway на smain
```

### hoster (83.69.248.175) — git-хостинг
```
WG IP:   10.66.0.7
SSH:     ssh hoster (ключ ~/.ssh/id_ed25519)
OpenClaw: bind=lan, порт 18789
Статус:  ✅ Gateway UP (systemd inactive)
```

### shevbo-cloud (192.144.14.187) — облачный OpenClaw
```
WG IP:   10.66.0.3
SSH:     ssh cloud (через ~/.ssh/config, ключ ~/.ssh/shevbo_cloud_ed25519)
         ssh cloud-fb (через ProxyJump smain, запасной путь)
OpenClaw: bind=lan, порт 18789
Статус:  ✅ Gateway UP (только что поднят)
Публичный IP: только 22 порт открыт
```

### pi (10.66.0.2) — Raspberry Pi (основной)
```
WG IP:   10.66.0.2
SSH:     ssh -J shectory-work shevbo@10.66.0.2
         (ключ ~/.ssh/pi_deploy_ed25519)
OpenClaw: node, gateway = 10.66.0.3 (cloud)
Статус:  ✅ Node UP (подключён к cloud gateway)
Сервисы: PingMaster (порт 4555), syslog-srv
```

### pi2 (10.66.0.5) — Raspberry Pi (чистый)
```
WG IP:   10.66.0.5
SSH:     ssh ubuntu@10.66.0.5 (ключ ~/.ssh/id_ed25519)
OpenClaw: ❌ не установлен
Статус:  ⚠️ Только SSH, чистый Ubuntu 24.04
```

---

## 2. Агенты — где живут, как вызвать

### На smain (через openclaw, bind=lan:18789)

| Имя | Функция | Вызов |
|-----|---------|-------|
| Tank 🛠️ | CTO, модератор | Через Telegram канал smain |
| Selfcoder ⚡ | Разработчик | `openclaw agent --agent selfcoder --message "..."` |
| Qaper 🔍 | QA-инженер | `openclaw agent --agent qaper --message "..."` |
| VirtualBoris 🧠 | Мамина связь | Telegram: @virtual-boris |
| JobScanner 🔎 | Сканирование HH/Trud | `openclaw agent --agent jobsearch-scanner --message "..."` |
| ResumePro 📄 | Адаптация резюме | Telegram: @resume-editor |
| InterviewCoach 🎯 | Подготовка к интервью | `openclaw agent --agent interview-coach --message "..."` |
| Nurse 🩺 | Психподдержка | `openclaw agent --agent nurse --message "..."` |
| GUIlya 🎨 | UI/UX дизайн | Telegram: @guilya |
| Titan 🏋️ | Фитнес-тренер | Telegram: @titan |
| Inbox 📥 | Секретарь | `openclaw agent --agent inbox --message "..."` |

### На sdev

| Имя | Функция | Вызов |
|-----|---------|-------|
| TankDev 🛠️ | CTO-дублёр (Tank Main на sdev) | `ssh sdev 'openclaw agent --message "..."'` |
| Selfcoder ⚡ | Разработчик | `ssh sdev 'openclaw agent --agent selfcoder --message "..."'` |
| Qaper 🔍 | QA | `ssh sdev 'openclaw agent --agent qaper --message "..."'` |

**Прямое сообщение из скрипта:** `~/scripts/msg-sdev.sh "текст"`

### На vibe (Windows)

| Имя | Функция | Вызов |
|-----|---------|-------|
| VBoris2 🧠 | Виртуальный Борис | Telegram: @vboris2 (через default канал vibe) |
| Inbox 📥 | Секретарь | `ssh vibe 'openclaw agent --agent inbox --message "..."'` |

**Прямое сообщение из скрипта:** `~/scripts/msg-vibe.sh "текст"`

### На hoster

| Имя | Функция | Вызов |
|-----|---------|-------|
| Hoster 🏠 | Git-сервер | `ssh hoster 'openclaw agent --agent main --message "..."'` |
| Shopin 🛒 | Шопинг-разведчик | `ssh hoster 'openclaw agent --agent shopin --message "..."'` |
| Lineman 🔌 | Cloudflare-коммуникации | `ssh hoster 'openclaw agent --agent lineman --message "..."'` |
| Inbox 📥 | Секретарь | `ssh hoster 'openclaw agent --agent inbox --message "..."'` |

### Сервисы (без OpenClaw)

| Имя | Функция | Адрес |
|-----|---------|-------|
| Lineman 🚦 | API-шлюз + мониторинг + дашборд | http://127.0.0.1:9090 / https://dashboard.shectory.ru |
| Медсестра 🩺 | Web-интерфейс (voice.shectory.ru) | http://localhost:8080 / https://voice.shectory.ru |
| PingMaster | Мониторинг пиров | http://10.66.0.2:4555 (на pi) |

---

## 3. Маршруты сообщений между агентами

### Скрипты быстрой связи (из ~/scripts/)

```bash
# На sdev (TankDev, Selfcoder, Qaper)
~/scripts/msg-sdev.sh "Текст сообщения"

# На vibe (VBoris2, Inbox, Shopin)
~/scripts/msg-vibe.sh "Текст сообщения"
```

### Через SSH + openclaw agent

```bash
# На smain (любому агенту)
openclaw agent --agent <id> --message "текст"

# На sdev
ssh sdev 'openclaw agent --agent <id> --message "текст"'

# На hoster
ssh hoster 'openclaw agent --agent <id> --message "текст"'

# На vibe (Windows)
ssh vibe 'openclaw agent --agent <id> --message "текст"'

# На cloud
ssh cloud 'openclaw agent --agent <id> --message "текст"'

# На pi (только node, без gateway)
ssh -J shectory-work shevbo@10.66.0.2 '...'

# На pi2 (без OpenClaw)
ssh ubuntu@10.66.0.5 '...'
```

### Сквозной пример: Tank → Shopin на hoster
```bash
ssh hoster 'openclaw agent --agent shopin --message "Какие находки за сегодня?"'
```

### Сквозной пример: Tank → VBoris2 на vibe (через Telegram-канал)
```bash
# Через скрипт отправляет в inbox на vibe
~/scripts/msg-vibe.sh "VBoris2, проверь новые находки от Shopin"
```

---

## 4. Состояние gateway на каждом хосте

| Хост | Gateway | Порт | Bind | Статус |
|------|---------|------|------|--------|
| smain | ✅ UP | 18789 | lan (0.0.0.0) | Работает |
| sdev | ✅ UP | 18789 | lan (0.0.0.0) | Процесс есть, systemd inactive |
| hoster | ✅ UP | 18789 | lan (0.0.0.0) | Процесс есть, systemd inactive |
| cloud | ✅ UP (только что) | 18789 | lan (0.0.0.0) | systemd user service enabled |
| vibe | node mode | — | — | Подключён к smain gateway |
| pi | node mode | — | loopback | Подключён к cloud gateway (10.66.0.3) |
| pi2 | ❌ нет OpenClaw | — | — | Чистый хост |

---

## 5. Проверка связности (quick reference)

```bash
# Ping всех WG хостов
for ip in 10.66.0.1 10.66.0.2 10.66.0.3 10.66.0.4 10.66.0.5 10.66.0.6 10.66.0.7; do
  ping -c1 -W2 $ip >/dev/null 2>&1 && echo "✅ $ip" || echo "❌ $ip"
done

# WG handshake
sudo wg show | grep -E "endpoint|latest handshake|allowed ips"
```

---

<!-- EOF -->
