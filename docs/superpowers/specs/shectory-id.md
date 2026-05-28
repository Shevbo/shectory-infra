# Shectory ID — процесс учёта пользователей для всех приложений Shectory

> **Статус:** действующий (задокументировано по факту кода, 2026-05-28)
> **Источник правды:** `~/workspaces/projects/shectory-portal/`
> **База:** PostgreSQL (shectory.ru), ORM Prisma

---

## 1. Концепция

**Shectory ID** — единый аккаунт пользователя, который работает во всех приложениях экосистемы Shectory. Хранится в одной БД (PostgreSQL на smain). Портал (`shectory.ru`) является **точкой входа и авторитетным хранилищем**. Остальные приложения проверяют учётные данные через HTTP-мост (bridge API).

Цитата из UI: *"Единый аккаунт работает во всех приложениях Shectory. Пароли хранятся только как bcrypt-хэши."*

---

## 2. Модель данных

### `portal_users` — основная таблица

| Поле | Тип | Описание |
|------|-----|---------|
| `id` | CUID | Первичный ключ |
| `email` | TEXT UNIQUE | Нормализован (`trim().toLowerCase()`), идентификатор |
| `password_hash` | TEXT | bcrypt, cost=12 |
| `role` | TEXT | `user` (default) или `admin` |
| `full_name` | TEXT NULL | Отображаемое имя |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

### `password_reset_tokens` — токены сброса пароля

| Поле | Тип | Описание |
|------|-----|---------|
| `id` | CUID | |
| `email` | TEXT | Email пользователя |
| `token` | TEXT UNIQUE | 64-символьный hex (32 random bytes) |
| `expires_at` | TIMESTAMP | +1 час от создания |
| `created_at` | TIMESTAMP | |

---

## 3. Аутентификация — полный поток

### 3.1 Вход

```
POST /api/auth/login
Body: { email, password }
```

1. Нормализовать email: `trim().toLowerCase()`
2. Найти `PortalUser` по email в БД
3. `bcrypt.compare(password, user.passwordHash)` — если false → 401
4. Сформировать session token:
   - `payload = "{email}:{expires_unix}"` (TTL = 30 дней)
   - `sig = HMAC-SHA256(payload, AUTH_SESSION_SECRET)`
   - `token = "{email}:{expires_unix}:{sig}"`
5. Вернуть `{ ok: true, email, role }` + Set-Cookie

**Cookie:** `shectory_portal_session`; HttpOnly; SameSite=Lax; Max-Age=2592000 (30д); Path=/; Secure (только prod)

### 3.2 Структура session token

```
{email}:{expires_unix_timestamp}:{hmac_sha256_hex}
```

- Подписан HMAC-SHA256, ключ = `AUTH_SESSION_SECRET`
- Проверка через `timingSafeEqual` (защита от timing attacks)
- Не хранится в БД — нельзя инвалидировать до истечения

### 3.3 Middleware — защита маршрутов

`src/middleware.ts` — защищает все маршруты Next.js:
- Читает cookie `shectory_portal_session`
- Верифицирует HMAC и срок действия
- При провале → redirect на `/login`

**Публичные маршруты** (без авторизации):
- `/login`, `/forgot-password`, `/reset-password`
- `/api/auth/*`, `/api/internal/*`
- `/_next/*`, `/brand/*`, `/favicon.ico`

### 3.4 Выход

```
POST /api/auth/logout
```
Устанавливает `Max-Age=0` для `shectory_portal_session` и `shectory_admin`.

### 3.5 Проверка текущей сессии

```
GET /api/auth/me
→ { ok: true, email } | { ok: false }
```

---

## 4. Сброс пароля

### Шаг 1 — запрос ссылки

```
POST /api/auth/forgot-password   Body: { email }
→ { ok: true }  (всегда, не раскрывает наличие пользователя)
```

Внутри, если пользователь найден:
- Удаляет старые токены для этого email
- Создаёт `crypto.randomBytes(32).toString('hex')`, TTL +1ч
- Отправляет письмо со ссылкой `https://shectory.ru/reset-password?token=<token>`

### Шаг 2 — применение нового пароля

```
POST /api/auth/reset-password   Body: { token, password }
```

- Минимальная длина пароля: 8 символов
- Проверяет токен + `expiresAt`
- `bcrypt.hash(password, 12)`, сохраняет
- Удаляет использованный токен (одноразовый)

---

## 5. SMTP

| Параметр | Значение |
|---------|---------|
| Host | mail.shectory.ru:587 |
| From | portal@shectory.ru |
| TLS | STARTTLS, `rejectUnauthorized: false` |
| Тема письма | "Сброс пароля — Shectory" |
| Ссылка | `https://shectory.ru/reset-password?token=...` (1ч) |

---

## 6. Bridge API — интеграция других приложений

Другие приложения экосистемы Shectory используют:

```
POST /api/internal/verify-portal-credentials
Authorization: Bearer <SHECTORY_AUTH_BRIDGE_SECRET>
Body: { email, password }
→ { ok: true, email, role, fullName } | { error: "Invalid credentials", status: 401 }
```

**Назначение:** позволяет любому сервису Shectory проверить логин/пароль пользователя без дублирования auth-логики.

**Защита:** единый Bearer-токен, хранится в `SHECTORY_AUTH_BRIDGE_SECRET` (env портала).

---

## 7. Управление пользователями

**Самостоятельная регистрация отсутствует.** Пользователей создаёт только администратор через CLI:

```bash
cd ~/workspaces/projects/shectory-portal
node scripts/create-portal-user.mjs <email> <password> [role] [fullName]

# Примеры:
node scripts/create-portal-user.mjs user@example.com pass123 user "Иван Иванов"
node scripts/create-portal-user.mjs admin@shectory.ru pass123 admin "Boris"
```

Скрипт использует `upsert` — обновляет существующего пользователя или создаёт нового.

---

## 8. Роли

| Роль | Описание |
|------|---------|
| `user` | Стандартный доступ к порталу |
| `admin` | Полный доступ: управление проектами, деплоем, ботами (`adminAuthOk()` check) |

---

## 9. Env-переменные портала

| Переменная | Описание |
|-----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `AUTH_SESSION_SECRET` | HMAC-ключ для session tokens |
| `SHECTORY_AUTH_BRIDGE_SECRET` | Bearer-токен для Bridge API |
| `SMTP_HOST` | mail.shectory.ru |
| `SMTP_PORT` | 587 |
| `SMTP_USER` | portal@shectory.ru |
| `SMTP_PASSWORD` | пароль SMTP (в .env) |
| `SMTP_FROM` | portal@shectory.ru |
| `NEXT_PUBLIC_BASE_URL` | https://shectory.ru |

---

## 10. Безопасность — что реализовано

| Аспект | Реализация |
|--------|-----------|
| Хранение пароля | bcrypt, cost=12 |
| Session token | HMAC-SHA256, `timingSafeEqual` |
| Cookie | HttpOnly, SameSite=Lax, Secure (prod) |
| Reset token | 32 random bytes, одноразовый, TTL 1h |
| Blind response | forgot-password не раскрывает email |
| Bridge | отдельный Bearer-токен |

---

## 11. Известные ограничения

| Ограничение | Последствие |
|------------|------------|
| Session token не хранится в БД | Нельзя отозвать раньше срока (logout только на клиенте) |
| Нет OAuth/SSO | Нет входа через Google, GitHub и т.д. |
| Нет MFA | Только пароль |
| Нет self-registration | Только admin создаёт пользователей |
| Bridge secret — один на все приложения | При утечке — все интеграции скомпрометированы |
| Только 2 роли | Нет fine-grained permissions |

---

## 12. Инфраструктура

| Компонент | Где |
|----------|-----|
| Next.js приложение | smain: `~/workspaces/projects/shectory-portal/` |
| PostgreSQL | smain (DATABASE_URL в .env) |
| Systemd сервис | `shectory-portal.service` (user unit) |
| Публичный URL | https://shectory.ru |
| SMTP-сервер | mail.shectory.ru (Poste.io на smain) |
| Исходный код auth | `src/lib/portal-auth.ts`, `src/lib/admin-auth.ts` |
| Middleware | `src/middleware.ts` |
| CLI создания юзеров | `scripts/create-portal-user.mjs` |
