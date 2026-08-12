# Shectory Federation — Disaster Recovery Restore Prompt

Ты агент восстановления. Задача: поднять федерацию Shectory на НОВОЙ инфраструктуре
из DR-бэкапа. Действуй по шагам, не импровизируй с секретами. Всё общение и коммиты —
кратко, по-русски, MSK-время (канон §10.1).

## Предусловие: пароль от архива

`BACKUP_ZIP_PASS` хранится **у Бориса вне федерации** (менеджер паролей) — это единственный
источник, доступный когда smain погиб. Копии внутри инфраструктуры (Keymaster на smain,
`~/.drill/backup_pass` на dr-drill) в аварии недоступны и на них рассчитывать нельзя.
Без этого пароля архивы нечитаемы и восстановление невозможно — начинай с него.

Важно при смене пароля: старые архивы остаются на старом. Полная ротация занимает
5 ночных прогонов (по числу копий на Google Drive), до этого храни оба.

## Что у тебя на входе
1. Расшифрованный архив бэкапа: `federation-<date>.tar.gz.gpg` расшифрован в `RESTORE/`.
   Пароль архива — см. предусловие выше. Команда:
   `gpg --batch --passphrase "$BACKUP_ZIP_PASS" -d federation-<date>.tar.gz.gpg | tar -xz -C RESTORE/`
   Источник архива — Google Drive по `BACKUP_URL`.
2. Структура `RESTORE/<date>/`:
   - `smain/ sdev/ hoster/ pi2/` — репозитории каждого узла (`~/workspaces` без vendor/секретов)
   - `_meta/db/` — дампы БД (sqlite `.backup`, `redis-dump.rdb`)
   - `_meta/config/` — `ssh_config`, `docker-compose.yml` сервисов
   - `_meta/manifest/` — `systemd-*-units.txt`, `docker.txt`, **`keymaster-manifest.json`** (инвентарь секретов БЕЗ значений)
   - `media-full/` — медиа/temp (разовая полная копия)
3. Доступ к свежему хосту класса smain (Ubuntu 22+), root/sudo.

## Чего в бэкапе НЕТ (сознательно, канон §7)
Сырых LLM-ключей, паролей БД/почты/GitHub, приватных ssh-ключей, `.env`, `openclaw.json`,
`.keymaster/`. Всё это **пере-провижинится через Keymaster** (шаг 6). Список того, что
нужно восстановить, — в `_meta/manifest/keymaster-manifest.json`.

## Шаги

### 1. База и зависимости
```bash
sudo apt update && sudo apt install -y rsync sqlite3 gpg docker.io docker-compose-plugin \
  nodejs npm python3 python3-venv wireguard-tools
# rclone для offsite (если нужен обратный доступ к Google Drive):
curl https://rclone.org/install.sh | sudo bash
```

### 2. Пользователь и репозитории
```bash
sudo useradd -m -s /bin/bash shectory   # если новый хост
sudo -u shectory mkdir -p /home/shectory/workspaces
# восстановить репо каждого узла на его будущий хост (здесь smain как пример):
rsync -a RESTORE/<date>/smain/ /home/shectory/workspaces/
# node_modules/venv отсутствуют намеренно — восстановить сборкой:
#   npm ci  (в JS-репо),  python3 -m venv .venv && pip install -r requirements.txt
```

### 3. Базы данных
```bash
# sqlite: положить файлы обратно по их путям (имена в _meta/db/ = путь с '/'→'_')
#   пример: workspaces_infra_lineman_lineman.db -> ~/workspaces/infra/lineman/lineman.db
# redis:
docker cp _meta/db/redis-dump.rdb <redis_container>:/data/dump.rdb   # до старта контейнера
# poste-mail: восстановить ~/mail-poste/data (users.db, dav.db, roundcube/), поднять compose.
```

### 4. Сеть (WireGuard) и SSH
- Поднять WG-интерфейс `10.66.0.0/24` (адреса узлов — в `_meta/config/ssh_config`:
  smain .1, pi .2, sdev .4, pi2 .5, vibe .6). Ключи WG — новые, распространить по узлам.
- `ssh_config` восстановить в `~/.ssh/config`; приватные ssh-ключи сгенерировать заново
  (`ssh-keygen -t ed25519`), публичные добавить в `authorized_keys` узлов и в GitHub deploy keys.

### 5. Сервисы
```bash
# systemd-юниты перечислены в _meta/manifest/systemd-system-units.txt и systemd-user-units.txt.
# Ключевые (smain): lineman/klod-dispatch, keymaster-sync, keymaster-tg-bot, klod-tg-bot,
#   builder, openclaw-gateway, shectory-portal, career-bot, lmstudio-tunnel.
#   (ollama-tunnel убран 2026-08-12: узел ollama-hoster ликвидирован.)
# docker-сервисы из _meta/config/*compose.yml: gemini-live-service (app+redis), mail-poste.
docker compose -f _meta/config/gemini-live-service-... up -d
# systemd: пересоздать юниты (тела — в репо infra/, пути в manifest), затем enable --now.
```

### 6. Секреты через Keymaster (обязательный ручной шаг)
Federation не хранит ключи. Поднять Keymaster (в `infra/`), затем **для каждого имени** из
`_meta/manifest/keymaster-manifest.json` задать значение заново (у Бориса/в бэкап-хранилище паролей):
```bash
# после старта Keymaster на 127.0.0.1:9093 — заполнить credentials store,
# затем сервисы получат значения штатно (openclaw.json, .env генерятся из Keymaster).
```
Критичные секреты: LLM-провайдеры (GEMINI/DEEPSEEK/ANTHROPIC OAuth), GitHub-токен, poste
mail-пароли, `BACKUP_ZIP_PASS`, `BACKUP_URL`, `BORIS_CHAT_ID`, публичный IP smain.

### 7. Проверка (verify)
```bash
curl -sS http://10.66.0.1:9090/api/klod/models >/dev/null && echo lineman-ok
curl -sS http://127.0.0.1:9093/keymaster/manifest >/dev/null && echo keymaster-ok
sqlite3 ~/workspaces/infra/lineman/lineman.db 'select count(*) from sqlite_master;'
docker ps   # gemini-live-service + mail-poste healthy
systemctl --user status klod-dispatch keymaster-tg-bot
```
Готово, когда: агенты в реестре отвечают через `/api/klod/ask`, Keymaster отдаёт значения,
почта и портал поднялись. Сообщи Борису статус через `Lineman /api/tg/send`.
