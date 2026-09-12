---
name: onboarding
description: Use when the user types `/onboarding` (or asks to "onboard this agent / актуализируй онбординг / обнови онбординг") inside an agent's project folder. Pulls the federation canon, writes a project-local onboarding snapshot, registers the agent with Klod, and ensures a portal card exists.
---

# /onboarding — bring an agent up to the current federation contract

When Boris (or any user) runs `/onboarding` inside a federation agent's project folder, you actualize the agent's context against the **single source of truth**: `/home/shectory/docs/FEDERATION_AGENT_ONBOARDING.md` (lives on `smain`).

Goal: after one `/onboarding` run the agent has, locally in its project folder, an up-to-date copy of the canon, a project-specific `AGENT.md` card (agent_id, node, purpose, repo path, doc pointers), a portal card on dashboard (created if missing), and a registered "onboarded" event in the federation news log so other agents see this agent exists.

## When to invoke

Trigger on any of:
- The user types `/onboarding`.
- The user says "сделай онбординг", "актуализируй онбординг", "обнови онбординг", "onboard this agent", "register this agent".
- You just landed in a federation agent project folder (`~/workspaces/*` on smain/sdev, or any folder with `.openclaw/` / `agent_id` markers) and there is NO `.onboarding/` directory.

**Do NOT** invoke /onboarding for the Lineman/Klod repo itself (`/home/shectory/workspaces/infra/lineman/`) — Klod IS the owner of the canon, it doesn't onboard itself.

## What you do — step by step

### 0. Short-circuit: бросить пайплайн если папка свежая

Перед чем-либо ещё запусти:

```bash
bash ~/.claude/skills/onboarding/bin/check_freshness.sh
```

- `status=fresh` → ОДНА строка пользователю: `/onboarding: up-to-date (age N h, ttl M h, sha …)`. На этом всё, шаги 1–9 НЕ выполнять. Никаких чтений канона, никаких подвызовов `/go-harness`.
- `status=stale` → продолжай с шага 1 (актуализация нужна).
- `status=absent` → продолжай с шага 1 (первый онбординг).

`ONBOARDING_FORCE=1` обходит short-circuit, если пользователь явно требует полного перепрогона.

### 1. Determine `agent_id` and `node`

In order:
1. Read `./.onboarding/AGENT.md` if it exists → use the recorded `agent_id` / `node`.
2. Else read `./CLAUDE.md` or `./AGENTS.md` and grep for `agent_id:` / `agent =`.
3. Else use the folder name as `agent_id` (e.g. `~/workspaces/eshkola` → `eshkola`).
4. `node` = `$(hostname -s)` (`smain` / `sdev` / `hoster` / `pi` / `vibe`).

If you cannot infer `agent_id` confidently, ask the user with one short question — don't guess.

### 2. Проверь доступ к индексу канона (копию НЕ сохраняем)

Канон больше **не копируется** в папку агента. Копия на 40 KB устаревала молча и
занимала контекст ради знаний, которые нужны пару раз за сессию. Канон живёт на smain
(`/home/shectory/docs/FEDERATION_AGENT_ONBOARDING.md`), индексируется на sdev и
спрашивается через Lineman.

Проверь, что канал живой, и заодно получи §0 контракта:

```bash
curl -sS -m 60 -X POST http://10.66.0.1:9090/api/fedrag/search \
  -H "X-Agent-Name: <agent_id>" -H 'Content-Type: application/json' \
  -d '{"query":"контракт агента федерации: что обязан выполнять новый агент"}' \
  | jq -r '.source, .text' | head -40
```

- `source: ragkit` — индекс жив, ничего сохранять не нужно.
- `source: fallback` — индекс недоступен. Онбординг **не прерывай**: карточка из шага 3
  самодостаточна. Допиши в отчёт строку «fedrag недоступен, канон не сверен» и сообщи
  Клоду через klod-access.

Если в папке остался старый `./.onboarding/CANONICAL.md` — удали его: два источника
правды хуже одного, а расходящаяся копия опаснее отсутствующей.

### 3. Write the project-local AGENT card

Create `./.onboarding/AGENT.md` using `~/.claude/skills/onboarding/templates/AGENT.md` as the shape. Fill:
- `agent_id`, `node`, `repo_path`
- `purpose` (one-line; if unknown, leave a `TODO:` marker for the user)
- `entry_points` (binaries / scripts / endpoints this agent exposes)
- `docs` (pointers to in-repo docs the agent owns)
- `dependencies_on_federation` (Klod for LLM, Keymaster for secrets, etc.)
- `last_onboarded_at` = current UTC+3 (MSK) timestamp

### 4. Cross-link into AGENTS.md / CLAUDE.md

If the project has `AGENTS.md` or `CLAUDE.md`, ensure a one-line marker exists pointing at
the agent card and the index. Add only if missing:

```
> Federation onboarding: карточка агента — [.onboarding/AGENT.md](.onboarding/AGENT.md). Канон федерации локально НЕ хранится: спрашивай индекс `POST http://10.66.0.1:9090/api/fedrag/search` с телом `{"query":"..."}`. Обновить карточку — `/onboarding`.
```

### 5. Ensure a portal card

Check whether this agent has a card on the dashboard:

```bash
~/.claude/skills/onboarding/bin/check_portal_card.sh "<agent_id>" "<node>"
```

Behavior:
- If the portal returns 200 → card exists, nothing to do.
- If 404 → POST to create with `agent_id`, `node`, `purpose` (from AGENT.md).
- If portal is unreachable from this node → fall back to posting a klod message: "portal-card-missing: <agent_id>@<node>" so Klod can create it manually.

### 6. Register the "onboarded" event in federation news

This is **mandatory** — it's how other agents discover that this agent exists and what it does.

```bash
~/.claude/skills/onboarding/bin/post_news.sh "<agent_id>" "<node>" onboarded \
  "purpose=<one-line>; repo=<abs-path>; docs=<comma-separated>"
```

`post_news.sh` POSTs to Lineman's klod-access inbox with `topic=news` so the daily refresh job picks it up and folds it into the canon.

### 7. Run `/go-harness` in the same folder

`/onboarding` устанавливает контекст «кто я в федерации»; `/go-harness`
устанавливает контекст «как меня запускать и проверять». Без второго
автономный оркестратор всё равно споткнётся на первом же задании.

Сразу после шагов 1-6 **вызови skill `/go-harness`** через Skill-инструмент в этой же
папке (см. `~/.claude/skills/go-harness/SKILL.md`). Он сам:
- зафиксирует absolute workspace path и git state,
- найдёт verify-loop (test/lint/typecheck),
- запишет baseline,
- создаст/расширит `AGENTS.md` с операционным cheatsheet.

Это обязательная часть `/onboarding`, не «опционально».

### 8. Убедись что `/spec-pilot` доступен (для будущих задач)

`/spec-pilot` запускается **позже** — когда пользователь приходит с
нетривиальной задачей («собери X», «сделай Y»). Сейчас твоя задача —
лишь убедиться что он установлен в этом узле:

```bash
test -r ~/.claude/skills/spec-pilot/SKILL.md && echo "spec-pilot=installed" || echo "spec-pilot=MISSING"
```

Если `MISSING` — добавь в финальный отчёт строку с инструкцией: на smain skill
лежит в `~/.claude/skills/spec-pilot/`, его нужно rsync'нуть на этот узел
(`rsync -az smain:.claude/skills/spec-pilot/ ~/.claude/skills/spec-pilot/`)
или попросить Бориса. На Windows-агентах копирует Боря руками.

Также добавь в `.onboarding/AGENT.md` строку:
```
next_action_on_new_task: при следующей нетривиальной задаче от пользователя — активировать /spec-pilot (он сам соберёт спеку и согласует перед кодом)
```

### 9. Report to the user

ОДИН компактный блок (русский, без воды, без эмодзи). **Жёсткий лимит — 8 строк**, никаких многостраничных отчётов:

```
/onboarding — <agent_id>@<node>
canon:       <fresh|refreshed N bytes>
agent card:  <wrote|updated>
portal card: <ok|created|reported-missing>
news:        registered (event=onboarded)
go-harness:  <L<N>→L4-ready | needs: ...>
spec-pilot:  <installed | MISSING (rsync ...)>
next:        <TODO-маркеры из AGENT.md | "ready for tasks">
```

Если short-circuit (шаг 0 вернул `fresh`) — лимит **одна** строка.

## Hard rules (do not violate)

- **Never write LLM API keys** into `.onboarding/AGENT.md` or anywhere else local. The whole point of the canon §2 is that agents don't hold keys.
- **Never** open public internet to Lineman/Keymaster from this skill. All HTTP calls go to `10.66.0.1:9090` (WG) or `127.0.0.1:9090` (loopback on smain) only.
- **Never** modify the canon `/home/shectory/docs/FEDERATION_AGENT_ONBOARDING.md` from this skill. The canon is updated by:
  - Klod manually (for policy changes), or
  - the daily refresh job (`scripts/onboarding_refresh.py` on smain) that folds in news from agents.
  If you spot a gap in the canon, post it as news (event=canon-gap) — don't edit the file.
- **Don't** invent agent_ids. If you can't infer one, ask the user.
- This skill is **idempotent** — running it twice in a row must be a no-op except for refreshing `last_onboarded_at`.
- **Канонический канал общения с Клодом — ТОЛЬКО эти два endpoint'а** (см. канон §3, регрессия 2026-08-11 «ответы терялись между inbox'ами»):
  - Отправить: `POST /api/agent/klod-access/message?from=<self>` (текст в теле, любой из `text/plain` / `application/json` / `application/x-www-form-urlencoded`).
  - Забрать ответы: `GET /api/agent/klod-access/outbox?to=<self>&since=<cursor>` — курсор сохраняй у себя, поллить раз в 5 мин или по push (§3.1 канона).
  - **НЕ полагаться на** `~/.federation-inbox/<self>/inbox.jsonl` для ответов Клода — это catch-all для сообщений от **других** агентов, не от Клода. Ответы Клода **всегда** в его outbox.
  - Проверка что твой поллер работает: `curl "http://10.66.0.1:9090/api/agent/klod-access/outbox?to=<self>&since=0" | jq '.messages | length'` — если ≥1, канал живой. Если 0 при известной активности Клода — поллер сломан, чинь у себя.
- **Onboarding-пайплайн должен проверить**, что агент читает outbox правильно: `bin/bootstrap.sh` дёргает `GET /api/agent/klod-access/outbox?to=<self>&since=0` и логирует последний id — если агент видит меньше, чем есть на самом деле, это ошибка его поллера, а не Клода.

## Files this skill provides

```
~/.claude/skills/onboarding/
  SKILL.md                  ← this file
  bin/
    fetch_canon.sh          ← pull canon with fallback chain
    detect_agent.sh         ← derive agent_id + node
    check_portal_card.sh    ← GET/POST portal card with fallback
    post_news.sh            ← POST news event to Klod inbox
    bootstrap.sh            ← top-level orchestrator (runs all of the above)
  templates/
    AGENT.md                ← project-local AGENT card shape
    marker.md               ← one-line marker for AGENTS.md/CLAUDE.md
```

You can run the bash-only part of the pipeline at once:

```bash
~/.claude/skills/onboarding/bin/bootstrap.sh
```

`bootstrap.sh` покрывает шаги 1–6 (canon, AGENT card, marker, portal-card, news) +
проверку наличия `/spec-pilot`. Шаг 7 (`/go-harness`) — это уже отдельный skill,
который ты вызываешь следующим (через Skill-инструмент), потому что он сам
читает файлы проекта и принимает решения о baseline'е.

## See also

- Canon: `/home/shectory/docs/FEDERATION_AGENT_ONBOARDING.md`
- Daily refresh: `/home/shectory/workspaces/infra/lineman/scripts/onboarding_refresh.py`
- Distribution: this skill lives on `smain` and `sdev` under `~/.claude/skills/onboarding/`. Windows (`vibe`) — Boris copies manually.
