# Shectory Portal — стандарты карточки проекта, БД на Hoster и фронтенд

> **Статус:** действующий (задокументировано по факту кода, 2026-05-28)
> **Источники:**
> - Portal: `smain:~/workspaces/projects/shectory-portal/`
> - Komissionka: `hoster:~/komissionka/`
> - OurDiary: `hoster:~/ourdiary/`

---

## 1. Карточка проекта на Shectory Portal

### 1.1 Что такое «проект» в портале

Портал (`shectory.ru`) — **витрина и оркестратор** всех прикладных приложений Shectory. Каждый проект — запись в таблице `projects` (PostgreSQL на smain). Список проектов — главная страница портала.

### 1.2 Поля карточки проекта

| Поле | Тип | Описание |
|------|-----|---------|
| `id` | CUID | Первичный ключ |
| `slug` | TEXT UNIQUE | URL-идентификатор (`/projects/komissionka`) |
| `name` | TEXT | Отображаемое название |
| `description` | TEXT | Описание проекта — показывается на карточке |
| `workspacePath` | TEXT | Путь к рабочей директории на сервере |
| `architectureMermaid` | TEXT | Диаграмма архитектуры в нотации Mermaid (mindmap/flowchart) |
| `repoUrl` | TEXT NULL | Ссылка на репозиторий |
| `docsUrl` | TEXT NULL | Ссылка на документацию |
| `version` | TEXT | Версия приложения (`"0.1.0"`) |
| `moduleVersionsJson` | JSON NULL | Версии отдельных модулей: `{"next":"14","prisma":"5"}` |
| `lastDeployedAt` | TIMESTAMP NULL | Дата последнего prod-деплоя |
| `aiContext` | TEXT | Контекст для ИИ-агентов: ключевые архитектурные принципы |

### 1.3 Связанные подтаблицы карточки

| Таблица | Поля | Назначение |
|---------|------|-----------|
| `tech_stack_items` | name, vendorUrl, sortOrder | Стек технологий (отображается как теги-ссылки) |
| `chat_sessions` | title, messages[] | Чат-сессии с ИИ-агентом проекта |
| `backlog_items` | title, description, status, priority | Бэклог задач |
| `test_modules` | id, name, description | Модули тест-кейсов |
| `test_cases` | title, description, kind, scope, status | Тест-кейсы (kind: `manual-guided/semi-automatic/automatic`) |
| `deploy_environments` | name, branch, status, targetHost, directory, isProd | Среды деплоя |

### 1.4 Отображение карточки (UI)

**Список проектов** (`/`) — grid-карточки с:
- Название, описание (3 строки, обрезается)
- Версия, дата prod-деплоя
- Hover: синий бордер

**Страница проекта** (`/projects/{slug}`) — три зоны:

```
┌─────────────────────────────────┬──────────────────────────┐
│ Описание, версия, стек,         │ Mermaid-диаграмма        │
│ repoUrl, docsUrl, workspacePath │ архитектуры              │
│ AI-контекст (pre-блок)          │                          │
└─────────────────────────────────┴──────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│ Рабочая область (вкладки):                                   │
│ Чаты │ Файлы │ Бэклог │ Тест-кейсы │ Деплой/среды │ ТГ-бот │ Терминал
└──────────────────────────────────────────────────────────────┘
```

### 1.5 Рабочая область — вкладки

| Вкладка | API | Что делает |
|---------|-----|-----------|
| Чаты | `POST /api/agent/chat` | Чат с ИИ-агентом; агент запускается через `agent` CLI в `workspacePath` |
| Файлы | `GET /api/workspace/tree` | Дерево файлов (exec на сервере) |
| Бэклог | `GET/POST /api/project/backlog` | CRUD задач |
| Тест-кейсы | `GET/POST /api/project/tests` | CRUD тест-кейсов + upsert модулей |
| Деплой/среды | `GET/POST /api/project/deploy` | Среды деплоя (CRUD) |
| ТГ-бот | `GET/POST /api/project/bot` | Статус и конфигурация Telegram-бота проекта |
| Терминал | — | Только SSH-ссылка (веб-терминал не встроен из соображений безопасности) |

> Все вкладки рабочей области требуют `adminAuthOk()` (роль `admin`).

### 1.6 Как создать проект в портале

```bash
# На smain, в каталоге shectory-portal
cd ~/workspaces/projects/shectory-portal

# Через скрипт seed (при первом запуске):
npm run db:seed

# Вручную через Prisma:
npx tsx -e "
  const { PrismaClient } = require('@prisma/client');
  const p = new PrismaClient();
  p.project.create({ data: {
    slug: 'my-app',
    name: 'My App',
    workspacePath: '/home/shectory/workspaces/my-app',
    description: '...',
    architectureMermaid: 'mindmap\n  root((My App))',
    aiContext: '...',
  }}).then(console.log).finally(() => p.\$disconnect());
"
```

---

## 2. Стандарт базы данных на Hoster с Prisma

### 2.1 Принцип

**На Hoster (83.69.248.175) — PostgreSQL сервер для prod-окружений всех приложений Shectory.** Каждое приложение имеет:
- Отдельную базу данных
- Отдельного пользователя PostgreSQL
- Отдельную схему Prisma (`prisma/schema.prisma`)

### 2.2 Базы данных на Hoster (актуально на 2026-05-28)

| База данных | Владелец (PG user) | Приложение |
|------------|-------------------|-----------|
| `komissionka_db` | `komissionka` | Komissionka (prod + test1) |
| `ourdiary` | `ourdiary_app` | OurDiary |
| `garden_manager` | `garden_manager_app` | Garden Manager |
| `project_cursorrpa` | `project_cursorrpa_app` | Проект CursorRPA (портальный трекер) |
| `project_komissionka` | `project_komissionka_app` | Проект Komissionka (портальный трекер) |
| `project_shectory_portal` | `project_shectory_portal_app` | Проект Shectory Portal (портальный трекер) |
| `shectory` | `shectory_app` | Shectory Portal (основная БД портала) |

> **Примечание:** `project_*` — базы, созданные порталом для хранения бэклога/тестов/деплоев по каждому проекту. Они управляются отдельно от основных приложений.

### 2.3 Создание новой базы для приложения

```bash
ssh ubuntu@83.69.248.175

# Создать пользователя и базу
sudo -u postgres createuser -P myapp_user
sudo -u postgres createdb -O myapp_user myapp_db

# Строка подключения:
# DATABASE_URL="postgresql://myapp_user:PASSWORD@localhost:5432/myapp_db"
```

### 2.4 Стандарт Prisma в Shectory-приложениях

#### Файл `prisma/schema.prisma` — минимальный шаблон

```prisma
datasource db {
  provider = "postgresql"
}

generator client {
  provider = "prisma-client-js"
}
```

#### Prodвинутый вариант (Komissionka-стандарт — Prisma 7 + pg adapter)

```prisma
datasource db {
  provider = "postgresql"
}

generator client {
  provider        = "prisma-client-js"
  previewFeatures = ["fullTextSearch"]
}
```

В `.env` обязательно добавить:
```env
PRISMA_CLIENT_ENGINE_TYPE=library
```

В `prisma.config.ts` / `src/lib/prisma.ts` использовать `@prisma/adapter-pg`:

```typescript
import { Pool } from "pg";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@prisma/client";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const adapter = new PrismaPg(pool);
export const prisma = new PrismaClient({ adapter });
```

> Shectory Portal (smain) использует стандартный Prisma (без adapter-pg). Komissionka/OurDiary на Hoster — Prisma 7 + adapter-pg.

### 2.5 Workflow работы с Prisma

```bash
# Первый деплой / после клонирования
npm install
npx prisma generate
npx prisma migrate deploy   # применить существующие миграции

# Разработка: изменить schema.prisma, затем:
npx prisma generate
npx prisma migrate dev --name описание_изменения

# Просмотр БД
npx prisma studio --port 5555

# Проверка подключения (Komissionka)
npx tsx scripts/db-check.ts
```

### 2.6 Стандарт миграций при деплое

```bash
# В deploy-from-git.sh на Hoster:
git fetch && git reset --hard origin/main
npm ci                              # или npm install при fallback
npx prisma generate
npx prisma migrate deploy           # ВСЕГДА deploy (не dev!) в prod
pm2 restart komissionka
```

---

## 3. Стандарт фронтенда на Hoster

### 3.1 Стек

| Компонент | Технология |
|----------|-----------|
| Фреймворк | Next.js (App Router) |
| Язык | TypeScript |
| UI | shadcn/UI + Tailwind CSS |
| Компоненты | Radix UI (dialog, label, slot, tabs) |
| ORM | Prisma 7 |
| Auth | NextAuth.js + Shectory ID bridge |
| Rich text | TipTap (Komissionka), @uiw/react-md-editor |
| Charts/diagram | Mermaid |
| Terminal | xterm.js |

### 3.2 Портовая схема Hoster

| Порт | Приложение | Домен |
|------|-----------|-------|
| 3000 | komissionka (prod) | komissionka92.ru |
| 3001 | komissionka-test1 | — (внутренний) |
| 3002 | ourdiary | ourdiary.shectory.ru |
| 3003 | garden-manager | garden.shectory.ru |
| 3141 | komissionka agent API | — (внутренний) |
| 18789 | OpenClaw gateway | — (федерация) |

### 3.3 Nginx — стандарт конфигурации

```nginx
upstream myapp_next {
    server 127.0.0.1:PORT;
    keepalive 8;
}

server {
    server_name myapp.shectory.ru;
    client_max_body_size 40m;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_pass http://myapp_next;
    }

    listen 443 ssl;  # настраивает Certbot
    ssl_certificate /etc/letsencrypt/live/myapp.shectory.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myapp.shectory.ru/privkey.pem;
}
```

SSL — Let's Encrypt через Certbot: `sudo certbot --nginx -d myapp.shectory.ru`

> **Важно:** `location /` должен ловить весь трафик включая `/_next/static/` — без отдельного `alias` на статику. Иначе Next.js отдаёт 400 для CSS.

### 3.4 PM2 — стандарт процессов

```javascript
// ecosystem.config.cjs
module.exports = {
  apps: [
    {
      name: "myapp",
      script: "npm",
      args: "run start",
      cwd: __dirname,
      instances: 1,
      exec_mode: "fork",
      max_memory_restart: "700M",
      env: { NODE_OPTIONS: "--max-old-space-size=512", TZ: "Europe/Moscow" },
    },
    // Опционально: отдельные процессы для agent (400M) и bot (200M)
  ],
};
```

Запуск: `pm2 start ecosystem.config.cjs`

### 3.5 Стандарт env-переменных для приложения на Hoster

```env
# БД
DATABASE_URL="postgresql://user:pass@localhost:5432/dbname"
PRISMA_CLIENT_ENGINE_TYPE=library   # для Prisma 7 + adapter-pg

# NextAuth
NEXTAUTH_SECRET="..."
NEXTAUTH_URL="https://myapp.shectory.ru"
AUTH_TRUST_HOST=true

# Shectory ID (SSO с порталом)
SHECTORY_PORTAL_URL="https://shectory.ru"
SHECTORY_AUTH_BRIDGE_SECRET="тот-же-секрет-что-на-портале"

# Прочее
APP_BASE_URL="https://myapp.shectory.ru"
NODE_ENV=production
TZ=Europe/Moscow
```

### 3.6 Интеграция с Shectory ID (SSO)

Приложения на Hoster могут подключиться к единому каталогу пользователей через bridge API портала.

**Паттерн (OurDiary — эталонная реализация):**

1. Пользователь вводит email/логин + пароль
2. Сначала проверяем в общем каталоге:
   ```
   POST https://shectory.ru/api/internal/verify-portal-credentials
   Authorization: Bearer {SHECTORY_AUTH_BRIDGE_SECRET}
   Body: { email: "full@email.com", password: "..." }
   → { ok: true, email, role, fullName }
   ```
3. При успехе делаем **upsert** локального пользователя:
   - роль из каталога (superadmin→SUPERADMIN, admin→ADMIN, иначе MEMBER)
4. При провале проверяем локальный `passwordHash` (для семейных учёток без записи в каталоге)

**Важные детали OurDiary:**
- Поддерживает вход без `@` → дополняет доменом из `SHECTORY_LOGIN_EMAIL_DOMAIN`
- Если нет `SHECTORY_AUTH_BRIDGE_SECRET` — работает только с локальными учётками (режим dev)
- Источник истины для «портальных» пользователей — shectory.ru

### 3.7 Среды деплоя (Komissionka-стандарт)

Komissionka поддерживает несколько сред деплоя из одного кода:

| Среда | Порт | База данных | Назначение |
|-------|------|------------|-----------|
| prod | 3000 | komissionka_db | Основная рабочая версия |
| test1 | 3001 | komissionka_db (тест) | Тестирование фич перед prod |

Среды хранятся в таблице `deploy_environments`. Deploy Worker (PM2 `deploy-worker`) обрабатывает очередь `deploy_queue` → пишет лог в `deploy_log`.

### 3.8 Next.js build + start скрипты

```json
{
  "scripts": {
    "dev":   "next dev --turbo",
    "build": "prisma generate && next build",
    "start": "next start",
    "db:push": "prisma db push",
    "prisma:studio": "prisma studio --port 5555"
  }
}
```

---

## 4. Связь компонентов — итоговая схема

```
┌──────────────────────────────────────────────────────────────┐
│                      SMAIN (83.69.248.77)                     │
│  ┌────────────────────────────────────┐                       │
│  │  Shectory Portal (shectory.ru)     │                       │
│  │  Next.js :3000 → nginx → HTTPS    │                       │
│  │  PostgreSQL: shectory_app@smain   │                       │
│  │  AUTH: portal_users, session-hmac │                       │
│  │  BRIDGE: /api/internal/verify-*   │◄─── другие приложения │
│  └────────────────────────────────────┘                       │
└──────────────────────────────────────────────────────────────┘
                          │ SHECTORY_AUTH_BRIDGE_SECRET
                          ▼
┌──────────────────────────────────────────────────────────────┐
│                     HOSTER (83.69.248.175)                    │
│                                                               │
│  komissionka92.ru    :3000  DB: komissionka_db               │
│  komissionka-test1   :3001  DB: komissionka_db (test)        │
│  ourdiary.shectory.ru :3002  DB: ourdiary                    │
│  garden.shectory.ru  :3003  DB: garden_manager               │
│                                                               │
│  PostgreSQL (local) — все app-базы                           │
│  PM2 — управление процессами                                  │
│  Nginx — SSL termination + reverse proxy                      │
│  Certbot — Let's Encrypt сертификаты                         │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. Добавление нового приложения на Hoster — чеклист

```
□ PostgreSQL: createuser + createdb
□ Код: git clone / rsync в ~/appname/
□ .env: DATABASE_URL, NEXTAUTH_SECRET, NEXTAUTH_URL, SHECTORY_PORTAL_URL, SHECTORY_AUTH_BRIDGE_SECRET
□ npm install && npx prisma generate && npx prisma migrate deploy
□ ecosystem.config.cjs: имя, порт (следующий свободный), memory limit
□ pm2 start ecosystem.config.cjs && pm2 save
□ Nginx: /etc/nginx/sites-available/appname.shectory.ru → sites-enabled
□ Certbot: sudo certbot --nginx -d appname.shectory.ru
□ Добавить проект в Shectory Portal (slug, name, workspacePath)
```
