# Security incident — 2026-05-29 — секреты в git history

## Что произошло

GitGuardian обнаружил Telegram Bot Token и OpenClaw Auth Token в публично-видимой истории `Shevbo/shectory-infra` (push 2026-05-29 15:01:31 UTC). Файл `.openclaw/openclaw.json` был закоммичен в коммитах `dc8d8f4`, `01019e5`, `9c4ab42`, `68ed8a4`, а удалён в `e9c5159`. Удаление через `git rm` НЕ убирает файл из истории — он по-прежнему доступен через `git log --all -p`. GitHub сканирует все коммиты — поэтому алёрты валятся.

Файл `.openclaw/openclaw.json` уже в `.gitignore` — новых утечек этим путём не будет.

## Что утекло (paths only, значения замаскированы)

| Тип | Поле | Кол-во |
|---|---|---|
| Google API key | `models.providers.google.apiKey` + 7 повторов в personas | 1 уникальный ключ |
| Telegram bot tokens | `channels.telegram.accounts.{default,guilya,main-sdev,resume-editor,interview-coach,keymaster,titan,virtual-boris,nurse}.botToken` | 9 ботов |
| OpenClaw gateway token | `gateway.auth.token` (48 chars) | 1 |
| Ollama dummy | `models.providers.ollama.apiKey` (placeholder, 14 chars) | можно проигнорировать |

Все Telegram-токены 46 символов формата `<id>:<35char>`. Google ключ префикс `AIza…Tg` (длина 39).

## Что я уже сделал (Lineman инженер)

1. Подтвердил что `.openclaw/openclaw.json` уже в `.gitignore` (не повторится).
2. Подготовил `scripts/scrub_history.sh` (этот файл выполнит filter-repo + force-push).
3. Подготовил `scripts/install_secret_guard.sh` (pre-commit + pre-push hook на gitleaks/regex).
4. В Lineman runtime: модуль `secret_mask.py`, маскирование на двух канала (reverse_proxy.py:812 и `/api/log` endpoint в proxy_server.py:490), 11 unit-тестов, ретроактивная маска 4457 строк в `lineman.db`. Это закрывает второй канал утечки — `request_log.request_body`.

## Что должен сделать Борис ВРУЧНУЮ (ротация скомпрометированных секретов)

GitHub-история уже была публичной — все эти токены считай скомпрометированы, даже если репо приватный.

### A. BotFather → ротировать все 9 ботов

Сценарий в Telegram чате с `@BotFather`:
```
/mybots
→ выбрать бота
→ API Token → Revoke current token → подтвердить
→ скопировать новый
```
Делать для каждого из 9: `default`, `guilya`, `main-sdev`, `resume-editor`, `interview-coach`, `keymaster`, `titan`, `virtual-boris`, `nurse`.

### B. Google Cloud Console → regenerate Google API key

Адрес: `https://console.cloud.google.com/apis/credentials`. Найти ключ с префиксом `AIza…Tg`. Кнопка → Regenerate key. Старый сразу мёртв.

### C. OpenClaw gateway token

Заменить `gateway.auth.token` (48 chars) на новое значение. Куда смотреть: `~/.openclaw/openclaw.json` поле `gateway.auth.token`. Сгенерировать новое `openssl rand -hex 24`.

### D. После A/B/C — обновить keymaster

Залить новые значения через TG-бот Ключника командой `прими секрет: NAME=VALUE` для каждого. Затем редиректить агентов на новые ключи (обычно через redeploy openclaw config).

### E. Дать мне команду «scrub»

После того как ротация прошла — сказать мне «зачищай историю». Я запущу `bash scripts/scrub_history.sh` который:
- Прогонит `git filter-repo --invert-paths --path .openclaw/openclaw.json --force`
- Сделает `git push --force-with-lease origin main`
- (опционально) trigger GitHub support ticket на инвалидацию cached blobs

До ротации scrub бесполезен — токены уже у атакующих.

## Почему не сделал scrub автоматом

`git push --force-with-lease` — destructive операция, переписывает удалённую историю, может сломать другие клонированные репозитории. По правилу из `CLAUDE.md` (`Любой git push --force…` требует аппрува). Дополнительно: scrub без предварительной ротации не имеет смысла безопасности и только усложняет debugging для коллег.

## Контроль

- В Lineman pipeline: ежедневный аудит `scripts/lineman_daily_audit.py` уже проверяет наличие `api_key/sk-/Bearer` в `request_log.request_body` и шлёт P0 алёрт в TG.
- В shectory-infra после `install_secret_guard.sh`: pre-commit hook завернёт коммит с подобными паттернами; pre-push — последняя сетка.
