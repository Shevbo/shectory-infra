---
name: github-repo
description: Manage GitHub repositories — create, push, set remote, add collaborators. Use when the user says создай репо, запушь на github, создай репозиторий, push to github, new repo.
---

# GitHub Repo Skill

Создание и управление GitHub-репозиториями через GitHub API.

## Токен

Хранится в `~/.shectory_github_token` (одна строка — Personal Access Token).
Права токена: `repo` (полный доступ к репозиториям).

Создать токен: https://github.com/settings/tokens/new
Записать: `echo "ghp_ВАШ_ТОКЕН" > ~/.shectory_github_token && chmod 600 ~/.shectory_github_token`

## ⚠️ Ограничение: GitHub API заблокирован по IP

GitHub REST API недоступен с IP сервера (83.69.248.77) из-за US trade controls.
Это касается создания/удаления репо, управления через API.

**SSH git-доступ работает нормально** — `git push`, `git clone` через SSH не затронуты.

**Обходной путь для создания репо:**
1. Создать репо вручную на github.com (через браузер с локального ПК)
2. Затем использовать команду `push` для подключения remote и отправки кода

Или: передать задачу агенту с доступом к GitHub API (например, локальный Claude Code).

## Скрипт

**Путь:** `~/skills/github-repo/scripts/github_repo.py`

## Команды

```bash
# Создать репозиторий
python3 ~/skills/github-repo/scripts/github_repo.py create \
  --name "repo-name" \
  --description "Описание проекта" \
  --private \
  --org Shevbo

# Создать репо и сразу подключить как remote к текущей папке
python3 ~/skills/github-repo/scripts/github_repo.py create \
  --name "repo-name" \
  --description "Описание" \
  --private \
  --org Shevbo \
  --local-path /home/shectory/workspaces/my-project \
  --push

# Только подключить существующее репо как remote и запушить
python3 ~/skills/github-repo/scripts/github_repo.py push \
  --url "git@github.com:Shevbo/repo-name.git" \
  --local-path /home/shectory/workspaces/my-project

# Список репозиториев организации
python3 ~/skills/github-repo/scripts/github_repo.py list --org Shevbo

# Удалить репозиторий (осторожно!)
python3 ~/skills/github-repo/scripts/github_repo.py delete \
  --org Shevbo --name "repo-name"
```

## Типовой флоу (создать + запушить)

1. Убедиться что в папке есть `git init` и первый коммит
2. Запустить `create --push`
3. Скрипт создаст репо → добавит remote origin → сделает `git push -u origin main`
4. Вернёт URL репозитория

## Хранение SSH-ключа

SSH-ключ для GitHub: `~/.ssh/id_ed25519_github`
Прописан в `~/.ssh/config` или используется напрямую через `GIT_SSH_COMMAND`.

## Конфиг по умолчанию

- **Org/User:** `Shevbo`
- **Visibility:** private
- **Default branch:** main
- **SSH key:** `~/.ssh/id_ed25519_github`
