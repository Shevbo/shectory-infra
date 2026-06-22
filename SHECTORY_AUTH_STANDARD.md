# 🔐 Стандарт аутентификации Shectory (единая учётка) — АВТОРИТЕТНЫЙ

> **Владелец стандарта: Claude / Executive Advisor (`main`).** Этот файл — единственный источник
> истины по auth для всех агентов федерации. Заменяет `infra/lineman/docs/PORTAL_AUTH_STANDARD.md`
> (тот устарел: декларирует bcrypt, тогда как код реально на scrypt — см. инцидент 2026-06-21).
> Обновляется только Claude. Дата актуализации: 2026-06-22.

## 🚫 Правило для всех агентов (Lineman, Qaper, nurse, titan, и т.д.)

**НИКТО, кроме Claude/Executive Advisor, не правит систему аутентификации.** Запрещено без явного
проведения через Claude:
- менять код auth портала (`shectory-portal/src/lib/portal-auth.ts`, любые `src/app/api/auth/*`,
  `src/app/api/internal/verify-portal-credentials/route.ts`);
- писать/менять `portal_users` (хэши паролей, роли) напрямую в БД `project_shectory_portal`;
- ротировать `SHECTORY_AUTH_BRIDGE_SECRET`;
- заводить собственную таблицу паролей в прикладном проекте.

Нужна правка auth или новый потребитель? → обратись к `main` (Claude):
`curl "http://127.0.0.1:9090/api/agent/main/message?from=<id>&message=auth:%20..."`.
Любое несанкционированное изменение детектирует сторож (ниже) и алертит Борю в Telegram.

## Принцип (одна фраза)

**Источник истины по пользователям — портал Shectory (таблица `portal_users`). Прикладные
приложения НЕ хранят пароли — проверяют их у портала через bridge и на успехе выдают свой
сессионный токен.** Логин пользователя — всегда полный email (`bshevelev@mail.ru` = superadmin везде).

## Фактический механизм (по коду, проверено 2026-06-22)

- **Хэш паролей: scrypt** формата `scrypt$<salt-hex>$<hash-hex>` (НЕ bcrypt). Реализация
  `portal-auth.ts`: `hashPassword`/`verifyPassword` (`scryptSync(pw, salt, 64)`), self-contained
  (соль в строке, внешний секрет не нужен).
- **Сессия портала:** HttpOnly cookie, токен `v1.<base64url(JSON{email,role,exp})>.<hmac-sha256>`,
  секрет `AUTH_SESSION_SECRET||NEXTAUTH_SECRET||ADMIN_TOKEN` иначе детерминированный фолбэк.
  Смена этого секрета инвалидирует существующие сессии (не пароли).
- **Bridge (сервер-сервер):** `POST {SHECTORY_PORTAL_URL}/api/internal/verify-portal-credentials`,
  `Authorization: Bearer {SHECTORY_AUTH_BRIDGE_SECRET}`, body `{email,password}`. Внутри тот же
  `passwordMatches` (scrypt). Ответы: 503 секрет не задан / 403 рассинхрон секрета / 401 неверно /
  200 `{ok,email,role,fullName}`.
- **Потребители** (гарден/GardenManager, STL, Lineman-дашборд, ourdiary): verify у портала →
  выпускают свою сессию. Локальный пароль допустим ТОЛЬКО для учёток, которых нет в `portal_users`.

## Регистрация новых пользователей (контракт)

- `POST /api/auth/register/request-code` {email} → код на почту (SMTP). Новый юзер = роль `user`.
- `POST /api/auth/register/confirm` {email,code,password} → `setPortalUserPassword(verifyEmail=true)`
  + сессия. Email `@unique`. Новые внешние юзеры всегда `user` (не admin).
- Код подтверждения НЕ возвращается в ответе в проде (`debugCode` только при `NODE_ENV!=production`).
- Готовность к потоку регистраций и открытые риски — см. `~/docs/auth-registration-readiness.md`.

## Сторож (tripwire) — детекция правок в обход стандарта

`~/workspaces/infra/auth-guard/auth-guard.sh` (cron каждые 10 мин). Алертит Борю в Telegram при:
изменении привилегированных аккаунтов (superadmin/admin), изменении auth-кода, ротации bridge-секрета,
деградации `/api/auth/login`, пустом хэше superadmin. Поток обычных регистраций (role=user) —
только логируется, тревогу НЕ поднимает. Baseline'ы: `~/keymaster/auth-baseline/*.baseline` (perms 600).
Снимок учёток (с хэшами, 600): `~/keymaster/auth-baseline/portal_users-snapshot-*.tsv`.

## Конфиг (env, ВЕРХНИЙ_РЕГИСТР, значения — только через Keymaster)

| Переменная | Назначение |
|---|---|
| `SHECTORY_PORTAL_URL` | база портала (прод `https://shectory.ru`, локально `http://127.0.0.1:3000`) |
| `SHECTORY_AUTH_BRIDGE_SECRET` | общий секрет портал↔потребитель (одно значение в обоих `.env`) |
| `AUTH_SESSION_SECRET` | подпись сессионных cookie портала |
| `SMTP_*`, `AUTH_EMAIL_FROM` | доставка кодов регистрации/сброса |

## Частые грабли

- «Пароль не подходит везде сразу» → хэш `portal_users` подменён, ИЛИ (для потребителей) 403 на
  bridge = рассинхрон `SHECTORY_AUTH_BRIDGE_SECRET`. Web-логин портала секрет НЕ использует —
  если падает и он, дело в хэше.
- Старый scrypt-хэш необратим: бэкап БД обязателен, иначе восстановление пароля = задать заново в портале.
