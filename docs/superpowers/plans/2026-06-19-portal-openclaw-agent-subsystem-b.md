# Subsystem B — Агент-исполнитель на OpenClaw (per-project, pro-модели через Lineman) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Сделать backend `openclaw` (уже выбираемый в GUI настроек портала) рабочим: чат проекта исполняется OpenClaw-агентом, привязанным к каталогу проекта, на pro-моделях (gemini-3.1-pro primary, deepseek-v4-pro fallback) через Lineman. cursor_cli остаётся запаркованным.

**Architecture:** Портал регистрирует per-project OpenClaw-агента (`portal-<slug>`) в `~/.openclaw/openclaw.json` (workspace = каталог проекта, model.primary/fallbacks из ролей), как он уже управляет per-project ТГ-ботами. Backend `openclaw` в `scripts/lib/agent-cli.mjs` вызывает `openclaw agent --agent portal-<slug> --json` (workspace и модель — из конфига агента) и возвращает ответ. OpenClaw даёт родные tools/skills/MCP, трафик в модели идёт через Lineman (providers.*.baseUrl у openclaw уже на Lineman).

**Tech Stack:** Next.js 14 + TS (portal), openclaw CLI 2026.6.x, node:test через tsx, live mint-session integration.

**Scope note:** Subsystem B из спека `docs/superpowers/specs/2026-06-19-portal-models-and-openclaw-agent-design.md`. Зависит от Subsystem A (развёрнут: роли chat/think, backend enum `openclaw` с guard-заглушкой, model-catalog). Работа в репо `CursorRPA` (портал), ветка `feat/portal-openclaw-agent`.

**Grounded facts (проверено 2026-06-19):**
- `openclaw agent` флаги: `--agent <id>`, `--model <provider/model>` (per-run override), `--message`, `--json`, `--session-key`, `--timeout <sec>`. **Нет `--workspace`** → workspace берётся из openclaw.json агента по id.
- Федеративный Agent API Lineman (`proxy_server.py:955`) шеллит `openclaw agent --agent <id> --message <msg> --json` синхронно и возвращает JSON.
- openclaw.json agents.list элемент: `{id, name, workspace, model:{primary,fallbacks,timeoutMs}}` (см. memory reference_openclaw). Gateway hot-reload подхватывает изменения.
- Subsystem A оставил в `agent-cli.mjs` ветку `if (backend === "openclaw") return {ok:false,...,"backend openclaw ещё не реализован (Subsystem B)"}` — её заменяем.
- openclaw CLI бинарь не на голом PATH портала: `/usr/lib/node_modules/openclaw/openclaw.mjs` (запуск `node <path> ...`) либо глобальный `openclaw`. Раннер вызывает через резолвимый путь (см. Task 3).

---

## File Structure

| Файл | Действие | Ответственность |
|------|----------|-----------------|
| `src/lib/openclaw-agent.ts` | Create | read/modify/write openclaw.json: ensureProjectAgent(slug, workspace, primary, fallbacks) — идемпотентно, с backup и валидацией |
| `src/lib/openclaw-agent.test.ts` | Create | unit: добавление/обновление записи в склонированном json-объекте (чистая функция upsertAgentEntry) |
| `scripts/lib/openclaw-cli.mjs` | Create | resolveOpenclawCmd() + runOpenclawAgent(agentId, message, modelId, timeoutMs) → {ok,stdout,stderr} |
| `scripts/lib/openclaw-cli.test.mjs` | Create | unit: парсинг JSON-ответа openclaw, построение argv |
| `scripts/lib/agent-cli.mjs` | Modify | заменить openclaw-guard на вызов runOpenclawAgent; обеспечить регистрацию агента |
| `src/app/api/agent/chat/route.ts` или ensure-точка | Modify | при backend=openclaw гарантировать ensureProjectAgent перед стартом раннера |

---

## Task 1: Чистая функция upsert записи агента в openclaw.json

**Files:** Create `src/lib/openclaw-agent.ts`, Create `src/lib/openclaw-agent.test.ts`.

- [ ] **Step 1: Failing test** `src/lib/openclaw-agent.test.ts`:
```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { upsertAgentEntry, projectAgentId } from "./openclaw-agent";

test("projectAgentId санитизирует slug", () => {
  assert.equal(projectAgentId("My Proj!"), "portal-my-proj-");
});

test("upsertAgentEntry добавляет нового агента, не трогая остальных", () => {
  const cfg = { agents: { list: [{ id: "keymaster", workspace: "/x" }] } };
  const out = upsertAgentEntry(cfg, {
    id: "portal-demo", workspace: "/ws/demo",
    primary: "google/gemini-3.1-pro-preview", fallbacks: ["deepseek/deepseek-reasoner"],
  });
  assert.equal(out.agents.list.length, 2);
  assert.ok(out.agents.list.find((a) => a.id === "keymaster"));
  const a = out.agents.list.find((a) => a.id === "portal-demo");
  assert.equal(a.workspace, "/ws/demo");
  assert.equal(a.model.primary, "google/gemini-3.1-pro-preview");
  assert.deepEqual(a.model.fallbacks, ["deepseek/deepseek-reasoner"]);
});

test("upsertAgentEntry обновляет существующего по id, без дублей", () => {
  const cfg = { agents: { list: [{ id: "portal-demo", workspace: "/old", model: { primary: "x" } }] } };
  const out = upsertAgentEntry(cfg, {
    id: "portal-demo", workspace: "/new", primary: "deepseek/deepseek-chat", fallbacks: [],
  });
  assert.equal(out.agents.list.length, 1);
  assert.equal(out.agents.list[0].workspace, "/new");
  assert.equal(out.agents.list[0].model.primary, "deepseek/deepseek-chat");
});
```

- [ ] **Step 2:** `npx tsx --test src/lib/openclaw-agent.test.ts` → FAIL.

- [ ] **Step 3: Implement** `src/lib/openclaw-agent.ts` (чистая логика + I/O-обёртка):
```ts
import * as fs from "node:fs";

const OPENCLAW_JSON = process.env.OPENCLAW_CONFIG ?? `${process.env.HOME ?? "/home/shectory"}/.openclaw/openclaw.json`;

export function projectAgentId(slug: string): string {
  return "portal-" + String(slug).toLowerCase().replace(/[^a-z0-9-]/g, "-");
}

export type AgentSpec = { id: string; workspace: string; primary: string; fallbacks: string[] };

/** Чистая: вернуть НОВЫЙ объект конфига с upsert-записью агента. Не мутирует вход. */
export function upsertAgentEntry(cfg: any, spec: AgentSpec): any {
  const next = JSON.parse(JSON.stringify(cfg ?? {}));
  next.agents = next.agents ?? {};
  next.agents.list = Array.isArray(next.agents.list) ? next.agents.list : [];
  const entry = {
    id: spec.id,
    name: spec.id,
    workspace: spec.workspace,
    model: { primary: spec.primary, fallbacks: spec.fallbacks, timeoutMs: 120000 },
  };
  const i = next.agents.list.findIndex((a: any) => a && a.id === spec.id);
  if (i >= 0) {
    next.agents.list[i] = { ...next.agents.list[i], ...entry, model: entry.model };
  } else {
    next.agents.list.push(entry);
  }
  return next;
}

/** I/O: прочитать openclaw.json, upsert, записать с backup. Идемпотентно. */
export function ensureProjectAgent(opts: { slug: string; workspace: string; primary: string; fallbacks: string[] }): { id: string } {
  const id = projectAgentId(opts.slug);
  const raw = fs.readFileSync(OPENCLAW_JSON, "utf8");
  const cfg = JSON.parse(raw);
  const next = upsertAgentEntry(cfg, { id, workspace: opts.workspace, primary: opts.primary, fallbacks: opts.fallbacks });
  // backup + atomic write
  fs.writeFileSync(OPENCLAW_JSON + ".bak", raw, { mode: 0o600 });
  const tmp = OPENCLAW_JSON + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(next, null, 2), { mode: 0o600 });
  fs.renameSync(tmp, OPENCLAW_JSON);
  return { id };
}
```

- [ ] **Step 4:** `npx tsx --test src/lib/openclaw-agent.test.ts` → 3 PASS.

- [ ] **Step 5: Commit** `git add src/lib/openclaw-agent.ts src/lib/openclaw-agent.test.ts && git commit -m "feat(portal): openclaw-agent — upsert per-project агента в openclaw.json"`

---

## Task 2: openclaw CLI обёртка (раннер)

**Files:** Create `scripts/lib/openclaw-cli.mjs`, Create `scripts/lib/openclaw-cli.test.mjs`.

- [ ] **Step 1: Failing test** `scripts/lib/openclaw-cli.test.mjs`:
```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildOpenclawArgs, parseOpenclawJson } from "./openclaw-cli.mjs";

test("buildOpenclawArgs формирует agent-вызов с моделью и json", () => {
  const a = buildOpenclawArgs({ agentId: "portal-demo", message: "hi", modelId: "google/gemini-3.1-pro-preview", timeoutSec: 120 });
  assert.deepEqual(a, ["agent", "--agent", "portal-demo", "--message", "hi", "--model", "google/gemini-3.1-pro-preview", "--json", "--timeout", "120"]);
});

test("buildOpenclawArgs без modelId опускает --model", () => {
  const a = buildOpenclawArgs({ agentId: "portal-demo", message: "hi", timeoutSec: 60 });
  assert.ok(!a.includes("--model"));
});

test("parseOpenclawJson извлекает текст ответа", () => {
  assert.equal(parseOpenclawJson(JSON.stringify({ reply: "готово" })), "готово");
  assert.equal(parseOpenclawJson(JSON.stringify({ text: "ok" })), "ok");
  assert.equal(parseOpenclawJson("не json"), "");
});
```
NOTE: точные поля JSON-ответа `openclaw agent --json` (reply/text/message/content) сверить ЖИВЬЁМ на этапе реализации: `node /usr/lib/node_modules/openclaw/openclaw.mjs agent --agent <тест> --message ping --json` и подогнать `parseOpenclawJson` + тест под реальный формат. НЕ угадывать — если поле иное, поправить и тест, и реализацию.

- [ ] **Step 2:** `node --test scripts/lib/openclaw-cli.test.mjs` → FAIL.

- [ ] **Step 3: Implement** `scripts/lib/openclaw-cli.mjs`:
```js
import { spawn } from "node:child_process";
import * as fs from "node:fs";

/** Найти исполняемый openclaw: глобальный бинарь или node + .mjs. */
export function resolveOpenclawCmd() {
  const mjs = "/usr/lib/node_modules/openclaw/openclaw.mjs";
  if (fs.existsSync(mjs)) return { cmd: process.execPath, prefix: [mjs] };
  return { cmd: "openclaw", prefix: [] };
}

export function buildOpenclawArgs({ agentId, message, modelId, timeoutSec }) {
  const a = ["agent", "--agent", agentId, "--message", String(message ?? "")];
  if (modelId) a.push("--model", modelId);
  a.push("--json");
  if (timeoutSec) a.push("--timeout", String(timeoutSec));
  return a;
}

/** Извлечь текст из JSON-ответа openclaw. Поля сверены живьём (см. Task 2 note). */
export function parseOpenclawJson(stdout) {
  try {
    const j = JSON.parse(stdout);
    return String(j.reply ?? j.text ?? j.message ?? j.content ?? "").trim();
  } catch {
    return "";
  }
}

export async function runOpenclawAgent({ agentId, message, modelId, timeoutMs }) {
  const { cmd, prefix } = resolveOpenclawCmd();
  const timeoutSec = Math.max(30, Math.floor((timeoutMs ?? 120000) / 1000));
  const args = [...prefix, ...buildOpenclawArgs({ agentId, message, modelId, timeoutSec })];
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { shell: false });
    let stdout = "", stderr = "";
    const t = setTimeout(() => { try { child.kill("SIGTERM"); } catch {} resolve({ ok: false, stdout, stderr: stderr + "\n[timeout]" }); }, (timeoutMs ?? 120000) + 5000);
    child.stdout?.on("data", (d) => (stdout += d.toString()));
    child.stderr?.on("data", (d) => (stderr += d.toString()));
    child.on("close", (code) => { clearTimeout(t); const text = parseOpenclawJson(stdout); resolve({ ok: code === 0 && !!text, stdout: text || stdout, stderr }); });
    child.on("error", (e) => { clearTimeout(t); resolve({ ok: false, stdout: "", stderr: String(e) }); });
  });
}
```

- [ ] **Step 4:** `node --test scripts/lib/openclaw-cli.test.mjs` → PASS (после сверки формата JSON).

- [ ] **Step 5: Commit** `git add scripts/lib/openclaw-cli.mjs scripts/lib/openclaw-cli.test.mjs && git commit -m "feat(portal): обёртка openclaw agent CLI"`

---

## Task 3: Подключить backend openclaw в agent-cli.mjs

**Files:** Modify `scripts/lib/agent-cli.mjs`.

- [ ] **Step 1:** Прочитать текущую openclaw-ветку (заглушка из Subsystem A) и `resolveRole`-эквивалент. Раннер — mjs, не импортирует ts. Модель роли chat берём из env: `process.env.ROLE_CHAT_MODEL` (формат `provider/modelId`), маппинг gemini→google через уже существующий `modelIdToLinemanTarget`. Для openclaw `--model` нужен формат `provider/model` где provider — как понимает openclaw (google/deepseek/...). Использовать `modelIdToLinemanTarget(ROLE_CHAT_MODEL)` → `${provider}/${model}`.

- [ ] **Step 2:** Заменить заглушку:
```js
  if (backend === "openclaw") {
    const { runOpenclawAgent } = await import("./openclaw-cli.mjs");
    const roleVal = String(process.env.ROLE_CHAT_MODEL || "gemini/gemini-3.1-pro-preview");
    const tgt = modelIdToLinemanTarget(roleVal);
    const modelArg = tgt ? `${tgt.provider}/${tgt.model}` : undefined;
    const agentId = "portal-" + String(process.env.SHECTORY_PROJECT_SLUG || "").toLowerCase().replace(/[^a-z0-9-]/g, "-");
    if (!agentId || agentId === "portal-") {
      return { ok: false, stdout: "", stderr: "openclaw backend: SHECTORY_PROJECT_SLUG не задан" };
    }
    return runOpenclawAgent({ agentId, message: prompt, modelId: modelArg, timeoutMs });
  }
```
NOTE: `SHECTORY_PROJECT_SLUG` должен прокидываться в окружение раннера тем, кто его спавнит. Проверить, как `agent-chat-runner.mjs` получает проект, и пробросить slug (Task 4). Если раннер уже знает workspacePath/slug — использовать его напрямую вместо env. Сверить при реализации; НЕ угадывать имя переменной — согласовать с Task 4.

- [ ] **Step 3:** `node --test scripts/lib/agent-cli.test.mjs` → существующие тесты (включая openclaw-guard, который теперь НЕ применим) обновить: заменить тест guard на тест что backend=openclaw без slug возвращает ошибку про slug.

- [ ] **Step 4: Commit** `git add scripts/lib/agent-cli.mjs scripts/lib/agent-cli.test.mjs && git commit -m "feat(portal): backend openclaw — вызов per-project агента"`

---

## Task 4: Регистрация агента + проброс slug при старте чата

**Files:** Modify `scripts/agent-chat-runner.mjs` и/или `src/app/api/agent/chat/route.ts`.

- [ ] **Step 1:** Прочитать `agent-chat-runner.mjs` и `src/app/api/agent/chat/route.ts` — найти, где известен project (slug, workspacePath) и где спавнится раннер / зовётся runAgentPrompt.

- [ ] **Step 2:** Перед запуском исполнения при backend=openclaw: вызвать `ensureProjectAgent({slug, workspace: project.workspacePath, primary: <ROLE_CHAT_MODEL в openclaw-формате>, fallbacks: ["deepseek/deepseek-reasoner"]})`. Удобнее в route.ts (TS, есть prisma project) — импортировать `ensureProjectAgent` из `@/lib/openclaw-agent`, вызвать когда `SHECTORY_EXECUTOR_BACKEND==="openclaw"` (читать через portal-settings). Пробросить `SHECTORY_PROJECT_SLUG=project.slug` в env спавна раннера (или в payload, если раннер берёт проект из БД — тогда раннер сам знает slug и Task 3 берёт его оттуда, env не нужен).

- [ ] **Step 3: Live integration test:** выставить `SHECTORY_EXECUTOR_BACKEND=openclaw` в настройках, минт-сессия суперадмина (как в журнале 2026-06-19), отправить сообщение в чат проекта, дождаться assistant-ответа от OpenClaw-агента. Проверить: запись `portal-<slug>` появилась в openclaw.json (workspace верный), ответ пришёл, чат не завис, очередь освободилась.

- [ ] **Step 4: Commit** изменения раннера/route.

---

## Self-Review checklist (выполнить после написания кода)
- Покрыт ли каждый пункт спека B? upsert агента (T1), CLI-обёртка (T2), backend-ветка (T3), регистрация+slug+интеграция (T4).
- Нет ли захардкоженных секретов? openclaw.json НЕ содержит ключей (модели идут через Lineman baseUrl); запись только id/workspace/model.
- Идемпотентность ensureProjectAgent (повторный вызов не плодит дублей) — тест T1.
- cursor_cli/gemini_api/lineman ветки не сломаны.
- Backup openclaw.json перед записью; atomic rename.

## Открытые пункты (сверить живьём, не угадывать)
1. Точный формат JSON `openclaw agent --json` (поле текста) — Task 2 note.
2. Как `agent-chat-runner.mjs` получает project/slug — Task 4 Step 1 (определяет, нужен ли env SHECTORY_PROJECT_SLUG).
3. Подхватывает ли gateway новый агент сразу после записи openclaw.json (hot-reload) или нужен сигнал — проверить на live-тесте T4.
4. Формат провайдера для openclaw `--model`: gemini→`google` или `gemini`? Сверить (memory reference_openclaw показывает `google/gemini-2.5-flash`). Подогнать modelIdToLinemanTarget-вывод при необходимости.

## Деплой
Только портал-репо (CursorRPA): merge feat/portal-openclaw-agent → main, rebuild, restart shectory-portal.service. openclaw.json правится в рантайме (не репо). НЕ требует рестарта Lineman.
