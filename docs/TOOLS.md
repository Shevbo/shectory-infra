# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## SSH Hosts (агентская ферма Shectory)

```
shectory-work → 83.69.248.77, user: shectory, key: ~/.ssh/id_ed25519
  Главный сервер разработки. Репозитории, Docker, почта.
  Пути: ~/workspaces/* (проекты)

shevbo-cloud → 192.144.14.187, user: shevbo, key: ~/.ssh/shevbo_cloud_ed25519
  OpenClaw-сервер (черновик). Claude/Gemini, Telegram.
  Пути: ~/.openclaw/, ~/wireguard-deploy/

shevbo-pi → 10.66.0.2, user: shevbo, key: ~/.ssh/pi_deploy_ed25519
  Через ProxyJump: shectory-work → shevbo-pi
  Raspberry Pi. OpenClaw-minimal, PingMaster, syslog.
  Пути: ~/workspaces/*, ~/PingMaster/

shevbo-pi2 → 192.168.1.90, user: ubuntu, key: ~/.ssh/id_ed25519
  Raspberry Pi (чистая). Свежая Ubuntu 24.04. Базовый хост для сервисов.
  Пока пустой.

hoster → 83.69.248.175, user: ubuntu, key: ~/.ssh/id_ed25519
  Хостинг приватных Git-репозиториев.
  Пути: /home/ubuntu/repos/

github.com → git@github.com, key: ~/.ssh/id_ed25519_github
  GitHub (Shevbo org): ShectoryAssist, OpenClaw-Dev, ourdiary, komissionka-app
```

## Репозитории Shectory

| Проект | Репозиторий | Хост |
|---|---|---|
| Shectory Assist | git@github.com:Shevbo/ShectoryAssist.git | GitHub |
| OpenClaw-Dev | git@github.com:Shevbo/OpenClaw-Dev.git | GitHub |
| ourdiary | git@github.com:Shevbo/ourdiary.git | GitHub |
| komissionka-app | git@github.com:Shevbo/komissionka-app.git | GitHub |
| PingMaster | ssh://hoster/home/ubuntu/repos/pingmaster.git | hoster |
| PiranhaAI | ssh://hoster/home/ubuntu/repos/piranha-ai.git | hoster |

## Рабочие директории на shectory-work
```
~/workspaces/Shectory Assist/
~/workspaces/Shectory Trade & Lab/
~/workspaces/CursorRPA/
~/workspaces/PingMaster/
~/workspaces/PiranhaAI/
~/workspaces/syslog-srv/
~/workspaces/openclaw/
~/workspaces/ourdiary/
~/workspaces/komissionka/
```

## Рабочие директории на shevbo-pi
```
~/workspaces/CursorRPA/
~/workspaces/syslog-srv/
~/PingMaster/
```

## Прочее

- **Голосовые сообщения:** только по явной просьбе Бориса
- **tts.auto = never** — голос не генерится автоматом
- **Почта:** mail.shectory.ru (Poste.io в Docker на shectory-work)
- **Домен:** shectory.ru
- **Tailscale:** 10.66.0.0/24, 100.0.0.0/8
- **Telegram:** один бот-токен на shevbo-cloud и cursorrpa, прокси через Proxy6

## vibe (home-pc) — Windows узел

vibe — 192.168.1.64 / WireGuard: 10.66.0.6, user: boris
Windows 10/11. OpenClaw node (schtasks, автозапуск).
SSH: ssh vibe (ключ id_ed25519), AmneziaWG VPN: 10.66.0.6

### Команды через OpenClaw

```bash
openclaw nodes status
openclaw nodes invoke --node vibe --command system.which --params '{"bins":["node","python","git"]}'
ssh vibe 'powershell -Command "Get-Date"'
```

### Инструменты на vibe
- node.exe v24.13.1, npm, openclaw v2026.5.7
- python C:/Python314/, git, VS Code, Cursor
- AmneziaWG, OpenSSH

### openclaw node сервис
- schtasks "OpenClaw Node" — автозапуск при логине бориса
- Скрипт: C:/Users/Boris/.openclaw/node.cmd
- Gateway: ws://10.66.0.1:18789 (WireGuard VPN)
- Node ID: bc80cbd7b52b2b19136a66b990a397a323cec9c093ec405cbc87304a37aa26b8
- Управление (на vibe): openclaw node start/stop/restart/status
