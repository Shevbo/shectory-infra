# shectory-infra

Infrastructure monorepo for the **Shectory Federation** — all code, configs, and docs needed to deploy new hosts, agents, and skills, or restore after failure.

**Primary host:** `smain` (VDS, Leaseweb LA, Ubuntu)  
**Federation node:** OpenClaw `smain` with agents: main (Tank), titan, virtual-boris, nurse, guilya, jobsearch, resume-editor, interview-coach, inbox

---

## Structure

```
shectory-infra/
├── lineman/          # Lineman v2 — smart API gateway + health monitor
│   ├── *.py          # Core service code
│   ├── checks/       # Per-service health check modules
│   ├── config.example.json  # Template — copy to config.json and fill secrets
│   ├── lineman.service      # systemd unit
│   └── run-lineman.sh       # Launcher (reads secrets from ~/.openclaw/)
├── skills/           # Claude Code skills (voice, youtube, summarize, etc.)
├── scripts/          # Utility scripts (voice, lineman client, etc.)
├── nginx/            # Nginx vhost configs
├── systemd/          # systemd user units for all services
├── claude/           # Claude Code global config (settings.json, CLAUDE.md, RTK.md)
├── docs/             # Federation docs, agent identities, architecture
└── deploy/
    ├── bootstrap.sh  # Full new-host setup from scratch
    └── restore.sh    # Quick recovery after failure
```

---

## Deploy new host

```bash
# 1. Клонируй репо
git clone git@github.com:Shevbo/shectory-infra.git ~/workspaces/shectory-infra

# 2. Запусти bootstrap
bash ~/workspaces/shectory-infra/deploy/bootstrap.sh

# 3. Заполни секреты
cp ~/workspaces/lineman/config.example.json ~/workspaces/lineman/config.json
# → отредактируй config.json: proxy_url, api keys
# → создай ~/.openclaw/openclaw.json с Gemini/Telegram токенами

# 4. Запусти Lineman
systemctl --user start lineman
```

## Restore after failure

```bash
cd ~/workspaces/shectory-infra && git pull
bash deploy/restore.sh
```

## Add new agent

1. Создай воркспейс: `~/workspaces/{agent-name}/`
2. Добавь systemd unit в `systemd/` и зарегистрируй в `lineman/config.example.json → agents.node_map`
3. Задокументируй в `docs/AGENTS.md`
4. Закоммить: `cd ~/workspaces/shectory-infra && git add . && git commit -m "feat: add {agent-name} agent"`

## Add new skill (Claude Code)

1. Создай директорию `skills/{skill-name}/`
2. Добавь точку входа и опиши в `skills/{skill-name}/README.md`
3. Зарегистрируй в `.claude/settings.json` если нужен hook

---

## Secrets (NOT in this repo)

| Секрет | Где хранится |
|--------|-------------|
| Gemini API key | `~/.openclaw/openclaw.json` |
| DeepSeek API key | `~/.openclaw/agents/main/agent/auth-profiles.json` |
| Telegram bot token | `~/.openclaw/openclaw.json` |
| Proxy credentials | `~/workspaces/lineman/config.json` (из `config.example.json`) |
| DB password | `~/.shectory_db_password` |
| GitHub token | `~/.shectory_github_token` |

---

## Key services

| Сервис | Port | Unit | Описание |
|--------|------|------|----------|
| Lineman | 9090 | `lineman.service` | API gateway, health monitor, reverse proxy |
| OpenClaw gateway | — | `openclaw-gateway.service` | Агентский оркестратор |
| Shectory portal | — | `shectory-portal.service` | Web dashboard |
| Nginx | 80/443 | system | Reverse proxy, SSL termination |

---

*Maintained by [Shevbo](https://github.com/Shevbo) + Claude Code (Executive Advisor)*
