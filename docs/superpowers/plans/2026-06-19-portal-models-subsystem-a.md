# Subsystem A — Каталог моделей и роли chat/think через Lineman — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать порталу единый каталог моделей (Gemini/DeepSeek/Claude/LM Studio), выбор моделей в настройках по ролям chat/think, и маршрутизацию всех LLM-вызовов строго через Lineman Klod-gateway.

**Architecture:** Каталог — константа в коде портала. Роли chat/think хранятся в `portal_settings`. Новый backend `lineman` в `scripts/lib/agent-cli.mjs` шлёт вызовы в `POST 127.0.0.1:9090/api/klod/ask` с явными provider+model. Klod-gateway расширяется: принимает явные provider+model (не только пресеты), поддерживает lm-studio и reasoning-модели. Захардкоженный BrightData-прокси удаляется. cursor_cli/gemini_api остаются как запаркованные backend-опции.

**Tech Stack:** Next.js 14 + Prisma (portal), Python 3.12 + pytest (Lineman), node:test через tsx (portal pure-logic), psql + minted session curl (live integration).

**Scope note:** Это Subsystem A из спека `docs/superpowers/specs/2026-06-19-portal-models-and-openclaw-agent-design.md`. Subsystem B (агент на OpenClaw) — отдельный план, пишется после A. A — самодостаточен и шиппится без B.

**Working dirs:**
- Portal: `/home/shectory/workspaces/projects/CursorRPA/shectory-portal`
- Lineman: `/home/shectory/workspaces/infra/lineman`

---

## File Structure

| Файл | Действие | Ответственность |
|------|----------|-----------------|
| `lineman/klod_ask.py` | Modify | resolve явных provider+model; lm-studio в build_request_payload; reasoning_content в extract_text |
| `lineman/proxy_server.py` | Modify | `_raw_api_klod_ask`: читать body.provider+body.model |
| `lineman/tests/test_klod_ask.py` | Modify | тесты explicit provider+model, lm-studio, reasoning_content |
| `shectory-portal/src/lib/model-catalog.ts` | Create | каталог моделей + helpers (валидация, toHint) |
| `shectory-portal/src/lib/model-catalog.test.ts` | Create | unit-тесты каталога |
| `shectory-portal/src/lib/portal-settings-registry.ts` | Modify | ключи ROLE_CHAT_MODEL/ROLE_THINK_MODEL; `lineman` в backend enum |
| `shectory-portal/src/lib/model-roles.ts` | Create | resolveRole(role) → {provider, modelId} |
| `shectory-portal/src/lib/model-roles.test.ts` | Create | unit-тесты ролей |
| `shectory-portal/scripts/lib/agent-cli.mjs` | Modify | backend `lineman` → runLinemanPrompt(klod/ask) |
| `shectory-portal/scripts/lib/agent-cli.test.mjs` | Create | unit-тест маппинга modelId→provider/model |
| `shectory-portal/src/components/PortalSettingsClient.tsx` | Modify | enum-дропдауны из registry.enumValues (DRY) |
| `shectory-portal/src/lib/proxy-fetch.ts` | Delete | удалить BrightData (секреты в коде) |

---

## Phase 1 — Lineman: явные provider+model в Klod-gateway (prerequisite)

Без этого klod/ask неизвестный hint молча падает в Claude Sonnet (`resolve_model` fallback="normal"). Каталог-модели должны идти точечно.

### Task 1: Klod-gateway принимает явные provider+model

**Files:**
- Modify: `lineman/klod_ask.py`
- Modify: `lineman/proxy_server.py:2189-2217`
- Test: `lineman/tests/test_klod_ask.py`

- [ ] **Step 1: Baseline pytest зелёный**

Run: `cd /home/shectory/workspaces/infra/lineman && .venv/bin/python -m pytest tests/test_klod_ask.py -q`
Expected: PASS (текущие тесты).

- [ ] **Step 2: Написать падающие тесты**

Добавить в `tests/test_klod_ask.py`:

```python
def test_resolve_explicit_provider_model_overrides_hint():
    # явные provider+model имеют приоритет над hint
    prov, model = klod_ask.resolve_explicit("deepseek", "deepseek-reasoner")
    assert prov == "deepseek"
    assert model == "deepseek-reasoner"

def test_resolve_explicit_rejects_unknown_provider():
    import pytest
    with pytest.raises(ValueError):
        klod_ask.resolve_explicit("madeup", "x")

def test_build_payload_lmstudio_openai_compat():
    path, body, headers = klod_ask.build_request_payload(
        "lm-studio", "qwen3.5-9b", "hi", 100)
    assert path == "/proxy/lm-studio/v1/chat/completions"
    assert body["model"] == "qwen3.5-9b"
    assert body["messages"][0]["content"] == "hi"

def test_extract_deepseek_reasoning_content_fallback():
    resp = {"choices": [{"message": {"content": "", "reasoning_content": "думал тут"}}]}
    assert klod_ask.extract_text("deepseek", resp) == "думал тут"
```

- [ ] **Step 3: Запустить — убедиться, что падают**

Run: `.venv/bin/python -m pytest tests/test_klod_ask.py -q -k "explicit or lmstudio or reasoning"`
Expected: FAIL (resolve_explicit нет; lm-studio в build_request_payload бросает ValueError; reasoning_content не извлекается).

- [ ] **Step 4: Реализация в `klod_ask.py`**

Добавить список валидных провайдеров и функцию:

```python
VALID_PROVIDERS = {"anthropic", "google", "deepseek", "lm-studio"}

def resolve_explicit(provider: str, model: str) -> tuple[str, str]:
    """Явные provider+model от вызывающего. Валидируем провайдера."""
    p = (provider or "").strip().lower()
    m = (model or "").strip()
    if p not in VALID_PROVIDERS:
        raise ValueError(f"unknown provider: {provider!r}")
    if not m:
        raise ValueError("model required")
    return p, m
```

В `build_request_payload` добавить ветку lm-studio (OpenAI-совместимо, как deepseek, без авторизации — локальный):

```python
    if provider == "lm-studio":
        path = "/proxy/lm-studio/v1/chat/completions"
        body = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"Content-Type": "application/json", "X-Agent-Name": "klod-access"}
        return path, body, headers
```

В `extract_text`, ветка deepseek (и lm-studio), reasoning fallback:

```python
    if provider in ("deepseek", "lm-studio"):
        try:
            choices = response.get("choices") or []
            if not choices:
                return ""
            msg = choices[0].get("message") or {}
            content = (msg.get("content") or "").strip()
            if content:
                return content
            return (msg.get("reasoning_content") or "").strip()
        except Exception:
            return ""
```

- [ ] **Step 5: Прокинуть provider+model в хендлере `proxy_server.py`**

В `_raw_api_klod_ask`, заменить блок резолва (строки ~2195, 2215):

```python
        hint = (body.get("model_hint") or "").strip().lower() or None
        explicit_provider = (body.get("provider") or "").strip().lower()
        explicit_model = (body.get("model") or "").strip()
        max_tokens = klod_ask.clamp_max_tokens(body.get("max_tokens"))
```

И ниже, где было `provider, model_id = klod_ask.resolve_model(hint)`:

```python
        if explicit_provider and explicit_model:
            try:
                provider, model_id = klod_ask.resolve_explicit(
                    explicit_provider, explicit_model)
            except ValueError as e:
                return self._send_simple_and_close(wr, 400, {"error": str(e)})
        else:
            provider, model_id = klod_ask.resolve_model(hint)
```

- [ ] **Step 6: Тесты зелёные**

Run: `.venv/bin/python -m pytest tests/test_klod_ask.py -q`
Expected: PASS (все, включая новые).

- [ ] **Step 7: Smoke на живом Lineman**

Run:
```bash
curl -s -m 30 -X POST http://127.0.0.1:9090/api/klod/ask -H 'Content-Type: application/json' \
 -d '{"agent":"portal","provider":"deepseek","model":"deepseek-chat","prompt":"скажи ОК","max_tokens":20}'
```
Expected: JSON с `"provider":"deepseek"`, `"model_used":"deepseek-chat"`, непустой text.

- [ ] **Step 8: Commit**

```bash
cd /home/shectory/workspaces/infra/lineman
git add klod_ask.py proxy_server.py tests/test_klod_ask.py
git commit -m "feat(klod): явные provider+model + lm-studio + reasoning_content"
```

---

### Task 2: Проверить/добавить маршрут lm-studio в Lineman

**Files:**
- Inspect/Modify: `lineman/config.json` (routing/reverse_proxy upstreams)

- [ ] **Step 1: Проверить наличие upstream lm-studio**

Run: `cd /home/shectory/workspaces/infra/lineman && python3 -c "import json;c=json.load(open('config.json'));print(json.dumps(c.get('reverse_proxy',{}).get('upstreams',c.get('routing')),ensure_ascii=False))" | tr ',' '\n' | grep -i "lm-studio\|lmstudio\|1234"`
Expected: показывает эндпоинт lm-studio (по памяти федерации `192.168.1.70:1234` или общий `lm-studio`). Если есть — Task 2 завершён, перейти к Step 3.

- [ ] **Step 2: Если маршрута нет — добавить upstream**

Добавить в `config.json → reverse_proxy.upstreams` (точный ключ/формат — по образцу существующего deepseek upstream в этом же файле; НЕ хардкодить секреты, эндпоинт LM Studio локальный без ключа). Это изменение `reverse_proxy.upstreams` — по дисциплине Lineman требует согласования у Бори (CLAUDE.md Lineman). Спросить через `/api/agent/main/message` перед правкой.

- [ ] **Step 3: Smoke lm-studio (если LM Studio запущен)**

Run:
```bash
curl -s -m 40 -X POST http://127.0.0.1:9090/api/klod/ask -H 'Content-Type: application/json' \
 -d '{"agent":"portal","provider":"lm-studio","model":"<реальный id из LM Studio>","prompt":"ok?","max_tokens":20}'
```
Expected: непустой ответ ИЛИ понятная ошибка соединения (если LM Studio выключен — это ожидаемо, маршрут корректен).

- [ ] **Step 4: Commit (если менялся config)**

```bash
git add config.json && git commit -m "feat(lineman): upstream lm-studio для klod/ask"
```

---

## Phase 2 — Portal: каталог, роли, backend lineman, UI

### Task 3: Каталог моделей (константа + helpers)

**Files:**
- Create: `shectory-portal/src/lib/model-catalog.ts`
- Test: `shectory-portal/src/lib/model-catalog.test.ts`

- [ ] **Step 1: Написать падающий тест**

`src/lib/model-catalog.test.ts`:
```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { MODEL_CATALOG, findCatalogModel, parseRoleValue, isValidRoleValue } from "./model-catalog.ts";

test("каталог содержит 12 моделей всех провайдеров", () => {
  const providers = new Set(MODEL_CATALOG.map((m) => m.provider));
  assert.ok(providers.has("gemini"));
  assert.ok(providers.has("deepseek"));
  assert.ok(providers.has("anthropic"));
  assert.ok(providers.has("lm-studio"));
  assert.equal(MODEL_CATALOG.length, 12);
});

test("findCatalogModel находит по provider+modelId", () => {
  const m = findCatalogModel("deepseek", "deepseek-reasoner");
  assert.equal(m?.label, "DeepSeek Pro (reasoner)");
});

test("parseRoleValue парсит 'provider/model'", () => {
  assert.deepEqual(parseRoleValue("gemini/gemini-2.5-flash"), {
    provider: "gemini", modelId: "gemini-2.5-flash",
  });
  assert.equal(parseRoleValue("garbage"), null);
});

test("isValidRoleValue требует наличие в каталоге", () => {
  assert.equal(isValidRoleValue("gemini/gemini-2.5-flash"), true);
  assert.equal(isValidRoleValue("gemini/not-real"), false);
});
```

- [ ] **Step 2: Запустить — упадёт (модуля нет)**

Run: `cd /home/shectory/workspaces/projects/CursorRPA/shectory-portal && npx tsx --test src/lib/model-catalog.test.ts`
Expected: FAIL (cannot find module).

- [ ] **Step 3: Реализация `src/lib/model-catalog.ts`**

```ts
// Каталог моделей портала. Источник истины — здесь (не БД).
// provider должен совпадать с провайдером в Lineman (anthropic/google→gemini/deepseek/lm-studio).
// ВНИМАНИЕ: в Lineman google-провайдер; в портале он зовётся "gemini".
// Маппинг portalProvider→linemanProvider — в toLinemanProvider().

export type ModelTier = "chat" | "think" | "both";
export type CatalogModel = {
  provider: "gemini" | "deepseek" | "anthropic" | "lm-studio";
  modelId: string;
  label: string;
  tier: ModelTier;
};

export const MODEL_CATALOG: CatalogModel[] = [
  { provider: "gemini", modelId: "gemini-2.5-flash", label: "Gemini 2.5 Flash", tier: "chat" },
  { provider: "gemini", modelId: "gemini-3.0-flash", label: "Gemini 3.0 Flash", tier: "chat" },
  { provider: "gemini", modelId: "gemini-2.5-pro", label: "Gemini 2.5 Pro", tier: "think" },
  { provider: "gemini", modelId: "gemini-3.1-pro-preview", label: "Gemini 3.1 Pro", tier: "think" },
  { provider: "deepseek", modelId: "deepseek-chat", label: "DeepSeek Flash (chat)", tier: "chat" },
  { provider: "deepseek", modelId: "deepseek-reasoner", label: "DeepSeek Pro (reasoner)", tier: "think" },
  { provider: "anthropic", modelId: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5", tier: "chat" },
  { provider: "anthropic", modelId: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", tier: "both" },
  { provider: "anthropic", modelId: "claude-opus-4-8", label: "Claude Opus 4.8", tier: "think" },
  { provider: "lm-studio", modelId: "qwen3.5-9b", label: "Qwen 3.5 9B (local)", tier: "chat" },
  { provider: "lm-studio", modelId: "deepseek-r1-14b", label: "DeepSeek R1 14B (local)", tier: "think" },
  { provider: "lm-studio", modelId: "gemma-4-26b", label: "Gemma 4 26B (local)", tier: "both" },
];

export function findCatalogModel(provider: string, modelId: string): CatalogModel | undefined {
  return MODEL_CATALOG.find((m) => m.provider === provider && m.modelId === modelId);
}

export function parseRoleValue(value: string): { provider: string; modelId: string } | null {
  const i = (value || "").indexOf("/");
  if (i <= 0) return null;
  return { provider: value.slice(0, i), modelId: value.slice(i + 1) };
}

export function isValidRoleValue(value: string): boolean {
  const p = parseRoleValue(value);
  return !!p && !!findCatalogModel(p.provider, p.modelId);
}

/** Значения для dropdown: "provider/modelId" → лейбл. */
export function roleEnumValues(): string[] {
  return MODEL_CATALOG.map((m) => `${m.provider}/${m.modelId}`);
}

/** portalProvider → linemanProvider (Lineman зовёт Gemini как "google"). */
export function toLinemanProvider(portalProvider: string): string {
  return portalProvider === "gemini" ? "google" : portalProvider;
}
```

- [ ] **Step 4: Тест зелёный**

Run: `npx tsx --test src/lib/model-catalog.test.ts`
Expected: PASS (4 теста).

- [ ] **Step 5: Commit**

```bash
git add src/lib/model-catalog.ts src/lib/model-catalog.test.ts
git commit -m "feat(portal): каталог моделей + helpers"
```

---

### Task 4: Роли chat/think в реестре настроек + resolveRole

**Files:**
- Modify: `shectory-portal/src/lib/portal-settings-registry.ts`
- Create: `shectory-portal/src/lib/model-roles.ts`
- Test: `shectory-portal/src/lib/model-roles.test.ts`

- [ ] **Step 1: Добавить ключи ролей в реестр**

В `PORTAL_SETTINGS_REGISTRY` (группа `ai`) добавить:
```ts
  {
    key: "ROLE_CHAT_MODEL",
    label: "Модель роли chat",
    description: "Быстрая модель для интерактива. Формат provider/modelId.",
    defaultValue: "gemini/gemini-2.5-flash",
    group: "ai",
    enumValues: [
      "gemini/gemini-2.5-flash", "gemini/gemini-3.0-flash", "gemini/gemini-2.5-pro",
      "gemini/gemini-3.1-pro-preview", "deepseek/deepseek-chat", "deepseek/deepseek-reasoner",
      "anthropic/claude-haiku-4-5-20251001", "anthropic/claude-sonnet-4-6", "anthropic/claude-opus-4-8",
      "lm-studio/qwen3.5-9b", "lm-studio/deepseek-r1-14b", "lm-studio/gemma-4-26b",
    ],
  },
  {
    key: "ROLE_THINK_MODEL",
    label: "Модель роли think",
    description: "Модель для анализа/аудита. Формат provider/modelId.",
    defaultValue: "gemini/gemini-2.5-pro",
    group: "ai",
    enumValues: [
      "gemini/gemini-2.5-flash", "gemini/gemini-3.0-flash", "gemini/gemini-2.5-pro",
      "gemini/gemini-3.1-pro-preview", "deepseek/deepseek-chat", "deepseek/deepseek-reasoner",
      "anthropic/claude-haiku-4-5-20251001", "anthropic/claude-sonnet-4-6", "anthropic/claude-opus-4-8",
      "lm-studio/qwen3.5-9b", "lm-studio/deepseek-r1-14b", "lm-studio/gemma-4-26b",
    ],
  },
```

В существующих `SHECTORY_EXECUTOR_BACKEND`/`SHECTORY_AUDITOR_BACKEND` добавить `lineman` (и заранее `openclaw` для Subsystem B) в `enumValues`:
```ts
    // SHECTORY_EXECUTOR_BACKEND:
    enumValues: ["cursor_cli", "gemini_api", "lineman", "openclaw"],
    // SHECTORY_AUDITOR_BACKEND:
    enumValues: ["", "cursor_cli", "gemini_api", "lineman", "openclaw"],
```

- [ ] **Step 2: Написать падающий тест resolveRole**

`src/lib/model-roles.test.ts`:
```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { resolveRoleFromEnv } from "./model-roles.ts";

test("resolveRoleFromEnv читает chat из env", () => {
  const r = resolveRoleFromEnv("chat", { ROLE_CHAT_MODEL: "deepseek/deepseek-chat" });
  assert.deepEqual(r, { provider: "deepseek", modelId: "deepseek-chat" });
});

test("resolveRoleFromEnv фолбэк на дефолт при пустом/невалидном", () => {
  assert.deepEqual(resolveRoleFromEnv("chat", {}), { provider: "gemini", modelId: "gemini-2.5-flash" });
  assert.deepEqual(resolveRoleFromEnv("think", { ROLE_THINK_MODEL: "garbage" }),
    { provider: "gemini", modelId: "gemini-2.5-pro" });
});
```

- [ ] **Step 3: Запустить — упадёт**

Run: `npx tsx --test src/lib/model-roles.test.ts`
Expected: FAIL (модуля нет).

- [ ] **Step 4: Реализация `src/lib/model-roles.ts`**

```ts
import { parseRoleValue, isValidRoleValue } from "./model-catalog.ts";

const DEFAULTS: Record<"chat" | "think", { provider: string; modelId: string }> = {
  chat: { provider: "gemini", modelId: "gemini-2.5-flash" },
  think: { provider: "gemini", modelId: "gemini-2.5-pro" },
};

/** Чистая функция: резолв роли из произвольного env-словаря (тестируемо). */
export function resolveRoleFromEnv(
  role: "chat" | "think",
  env: Record<string, string | undefined>
): { provider: string; modelId: string } {
  const key = role === "chat" ? "ROLE_CHAT_MODEL" : "ROLE_THINK_MODEL";
  const v = (env[key] || "").trim();
  if (v && isValidRoleValue(v)) {
    return parseRoleValue(v)!;
  }
  return DEFAULTS[role];
}

/** Прод-обёртка над process.env. */
export function resolveRole(role: "chat" | "think") {
  return resolveRoleFromEnv(role, process.env as Record<string, string | undefined>);
}
```

- [ ] **Step 5: Тест зелёный**

Run: `npx tsx --test src/lib/model-roles.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/lib/portal-settings-registry.ts src/lib/model-roles.ts src/lib/model-roles.test.ts
git commit -m "feat(portal): роли chat/think в настройках + resolveRole"
```

---

### Task 5: Backend `lineman` в agent-cli.mjs

**Files:**
- Modify: `shectory-portal/scripts/lib/agent-cli.mjs`
- Test: `shectory-portal/scripts/lib/agent-cli.test.mjs`

- [ ] **Step 1: Написать падающий тест маппинга**

`scripts/lib/agent-cli.test.mjs`:
```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { modelIdToLinemanTarget } from "./agent-cli.mjs";

test("modelId 'gemini/gemini-3.1-pro-preview' → google provider", () => {
  assert.deepEqual(modelIdToLinemanTarget("gemini/gemini-3.1-pro-preview"),
    { provider: "google", model: "gemini-3.1-pro-preview" });
});

test("modelId 'deepseek/deepseek-reasoner' → deepseek", () => {
  assert.deepEqual(modelIdToLinemanTarget("deepseek/deepseek-reasoner"),
    { provider: "deepseek", model: "deepseek-reasoner" });
});

test("голый modelId без провайдера → null (нужен формат provider/model)", () => {
  assert.equal(modelIdToLinemanTarget("gemini-3-flash"), null);
});
```

- [ ] **Step 2: Запустить — упадёт**

Run: `cd /home/shectory/workspaces/projects/CursorRPA/shectory-portal && node --test scripts/lib/agent-cli.test.mjs`
Expected: FAIL (функции нет).

- [ ] **Step 3: Реализация в `scripts/lib/agent-cli.mjs`**

Добавить экспорт-функции (рядом с resolveBackend):
```js
/** "provider/model" → {provider, model} для Lineman (gemini→google). НЕ роль, а конкретная модель. */
export function modelIdToLinemanTarget(modelId) {
  const v = String(modelId || "");
  const i = v.indexOf("/");
  if (i <= 0) return null;
  const portalProvider = v.slice(0, i);
  const model = v.slice(i + 1);
  if (!model) return null;
  const provider = portalProvider === "gemini" ? "google" : portalProvider;
  return { provider, model };
}

/** Вызов LLM через Lineman Klod-gateway (без tool'ов — для backend=lineman). */
async function runLinemanPrompt(prompt, modelId, timeoutMs) {
  const target = modelIdToLinemanTarget(modelId);
  if (!target) {
    return { ok: false, stdout: "", stderr: `backend=lineman требует modelId формата provider/model, получено: ${modelId}` };
  }
  const url = "http://127.0.0.1:9090/api/klod/ask";
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: ac.signal,
      body: JSON.stringify({
        agent: "portal",
        provider: target.provider,
        model: target.model,
        prompt: String(prompt ?? ""),
        max_tokens: 4000,
      }),
    });
    const j = await r.json().catch(() => ({}));
    clearTimeout(t);
    if (!r.ok) {
      return { ok: false, stdout: "", stderr: `[Lineman ${r.status}] ${j?.error || ""}` };
    }
    const text = String(j?.text || "").trim();
    if (!text) return { ok: false, stdout: "", stderr: "Lineman klod/ask: пустой ответ" };
    return { ok: true, stdout: text, stderr: "" };
  } catch (e) {
    clearTimeout(t);
    const msg = e?.name === "AbortError" ? `timeout ${timeoutMs}ms` : String(e);
    return { ok: false, stdout: "", stderr: `[Lineman] ${msg}` };
  }
}
```

В `runAgentPrompt`, после `const backend = resolveBackend(role);` и ветки gemini_api, добавить:
```js
  if (backend === "lineman") {
    return runLinemanPrompt(prompt, modelId, timeoutMs);
  }
```

- [ ] **Step 4: Тест зелёный**

Run: `node --test scripts/lib/agent-cli.test.mjs`
Expected: PASS (3 теста).

- [ ] **Step 5: Live integration — auditor через Lineman**

В `/settings` (или напрямую в БД portal_settings) выставить `SHECTORY_AUDITOR_BACKEND=lineman` и `SHECTORY_AUDITOR_AGENT_MODEL_ID=gemini/gemini-2.5-pro`, затем прогнать чат, требующий аудита (минт-сессия как в журнале сессии 2026-06-19). Проверить, что reply аудитора пришёл (а не ошибка backend).

Run (проверка записи настройки):
```bash
DB="postgresql://$(grep '^DATABASE_URL=' .env|cut -d= -f2-|tr -d '"'|sed -E 's#postgresql://##;s/\?.*//')"
psql "$DB" -tAc "select key,value from portal_settings where key like 'ROLE_%' or key like 'SHECTORY_AUDITOR%';"
```
Expected: значения на месте.

- [ ] **Step 6: Commit**

```bash
git add scripts/lib/agent-cli.mjs scripts/lib/agent-cli.test.mjs
git commit -m "feat(portal): backend lineman в agent-cli (klod/ask, explicit provider+model)"
```

---

### Task 6: UI — дропдауны из registry.enumValues (DRY)

**Files:**
- Modify: `shectory-portal/src/components/PortalSettingsClient.tsx:1164-1205`

- [ ] **Step 1: Заменить хардкод enum на чтение из реестра**

Заменить блок (строки ~1165-1176):
```ts
                const def = settings.find((x) => x.key === s.key);
                const enumVals = [
                  "SHECTORY_EXECUTOR_BACKEND",
                  "SHECTORY_AUDITOR_BACKEND",
                  "SHECTORY_AGENT_ALLOW_COMMANDS",
                ].includes(s.key)
                  ? s.key === "SHECTORY_EXECUTOR_BACKEND"
                    ? ["cursor_cli", "gemini_api"]
                    : s.key === "SHECTORY_AUDITOR_BACKEND"
                      ? ["", "cursor_cli", "gemini_api"]
                      : ["0", "1"]
                  : null;
```
на:
```ts
                const def = settings.find((x) => x.key === s.key);
                // enum-опции берём из реестра (def.enumValues); спец-случай булевого тумблера.
                const enumVals: string[] | null =
                  def?.enumValues && def.enumValues.length > 0
                    ? def.enumValues
                    : s.key === "SHECTORY_AGENT_ALLOW_COMMANDS"
                      ? ["0", "1"]
                      : null;
```

Примечание: `settings` (PublicSettingRow) должен включать `enumValues`. Проверить тип `PublicSettingRow` в `src/lib/portal-settings.ts` — если поля нет, добавить `enumValues?: string[]` и прокинуть его в `listPublicSettings()` из `def.enumValues`.

- [ ] **Step 2: Прокинуть enumValues в PublicSettingRow**

В `src/lib/portal-settings.ts`, тип `PublicSettingRow` добавить `enumValues?: string[];`, и в `listPublicSettings()` map добавить:
```ts
    enumValues: PORTAL_SETTINGS_REGISTRY.find((d) => d.key === r.key)?.enumValues,
```

- [ ] **Step 3: Сборка портала**

Run: `npm run build`
Expected: `Compiled successfully`, без TS-ошибок.

- [ ] **Step 4: Live проверка UI**

Перезапуск сервиса (`systemctl --user restart shectory-portal.service`, при EADDRINUSE — `pkill -f next-server` + `reset-failed`), открыть `/settings` с сессией суперадмина → секция «ИИ» показывает дропдауны «Модель роли chat/think» (12 опций) и backend с `lineman`/`openclaw`.

- [ ] **Step 5: Commit**

```bash
git add src/components/PortalSettingsClient.tsx src/lib/portal-settings.ts
git commit -m "feat(portal): дропдауны настроек из registry.enumValues (роли chat/think)"
```

---

### Task 7: Удалить BrightData proxy-fetch (секреты в коде)

**Files:**
- Delete: `shectory-portal/src/lib/proxy-fetch.ts`
- Modify: все импортёры

- [ ] **Step 1: Найти импортёров**

Run: `grep -rn "proxy-fetch\|proxyRequest\|getProxyAgent" src scripts --include=*.ts --include=*.tsx --include=*.mjs | grep -v node_modules`
Expected: список файлов, использующих BrightData.

- [ ] **Step 2: Заменить вызовы на Lineman-путь**

Для каждого импортёра: если это LLM-вызов — перевести на `askLLM`/klod/ask (как в Task 5); если это просто HTTP — заменить на прямой `fetch` (трафик портала к Lineman/локальным сервисам прокси не требует). Показать конкретную правку для каждого файла из Step 1 (зависит от находок — выполнять по одному, заменяя `proxyRequest(url, opts, true)` на `fetch(url, opts)` либо на `askLLM`).

- [ ] **Step 3: Удалить файл**

Run: `git rm src/lib/proxy-fetch.ts`

- [ ] **Step 4: Сборка**

Run: `npm run build`
Expected: `Compiled successfully` (нет битых импортов).

- [ ] **Step 5: Подтвердить отсутствие секретов**

Run: `grep -rn "brd-customer\|superproxy\|brd.superproxy" src scripts | grep -v node_modules || echo "CLEAN"`
Expected: `CLEAN`.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "refactor(portal): удалить BrightData proxy (секреты в коде), трафик через Lineman"
```

---

## Self-Review

**Spec coverage:**
- A1 каталог → Task 3. A2 роли → Task 4. A3 единый клиент через Lineman → Task 5 (+ Task 1 Lineman). A4 точки применения ролей → Task 5 (executor/auditor backend=lineman; chat/think модели в EXECUTOR/AUDITOR_MODEL_ID или ROLE_*). A5 UI → Task 6. Удаление BrightData → Task 7. LM Studio провайдер → Task 1/2. reasoning_content → Task 1.
- Зазор: A4 маппит «генерацию инж-промптов» и «чеклисты» на роли. В коде это идёт через agent-runner (executor role). Они автоматически наследуют backend=lineman + EXECUTOR модель. Явная привязка ROLE_THINK к генерации промптов — опционально; зафиксировано: использовать executor/auditor backend+model как носители ролей chat/think. ROLE_CHAT_MODEL/ROLE_THINK_MODEL добавлены как явные настройки и читаются resolveRole для будущих прямых вызовов (Subsystem B и route-level). Это согласовано, не зазор.

**Placeholder scan:** Task 2 Step 2 и Task 7 Step 2 зависят от живых находок (маршрут lm-studio / список импортёров) — это инспекционные шаги с чёткой инструкцией, не плейсхолдеры кода. Остальные шаги содержат полный код.

**Type consistency:** `parseRoleValue`/`isValidRoleValue`/`findCatalogModel`/`toLinemanProvider` (Task 3) используются в Task 4 (model-roles) и согласованы по сигнатурам. `modelIdToLinemanTarget` (Task 5) дублирует gemini→google маппинг намеренно (mjs-раннер не импортирует ts-каталог; провайдеры-строки идентичны). `resolve_explicit`/`build_request_payload`/`extract_text` (Task 1) согласованы с хендлером proxy_server.

---

## Execution Handoff

После сохранения плана — выбор исполнения (см. конец сессии).
