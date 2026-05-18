# Agent Token Optimization — Design Spec
**Date:** 2026-05-18
**Status:** Approved for implementation

## Problem

Censor data shows two compounding issues on smain OpenClaw agents:

1. **Context bloat**: `main` agent accumulates 134–146k bytes per request (35k tokens), growing ~2-4k bytes per turn. History ("tail") dominates the request body -- far exceeding the 30% threshold.
2. **System prompt bloat**: `main` agent loads 711 lines across 6 files per session (AGENTS.md 308 + SOUL.md 47 + IDENTITY.md 24 + HEARTBEAT.md 27 + TOOLS.md 97 + USER.md 48 + MEMORY.md 160). Other agents: 100–200 lines each.
3. **Retry flood**: `hoster:?` runs 80%+ retry rate (144/174 requests with high_retry_count). `smain:?` hits 372k session tokens in 30 min.

## Metric

**Tail ≤ 30% of useful request.** Where:
- `useful` = system prompt tokens + current user message tokens
- `tail` = all history messages (prior turns)

System prompts must be critically trimmed so "useful" is maximally dense -- no filler.

## Approach

**B: Parallel execution** -- Lineman middleware + all 12 agent prompts simultaneously.

---

## Component 1: `summarise_addendums` Middleware

### Location
`/home/shectory/workspaces/infra/lineman/reverse_proxy.py`

### Insertion point
After dedup cache check, before `session.request()` call (~line 260). Body is accessible, circuit breaker already passed.

### Algorithm
```
1. json.loads(req_body) → messages[]
2. If len(messages) < 4: skip
3. system_tokens  = sum(len(m["content"]) // 4 for m in messages if role=="system")
4. last_user      = last message where role=="user"
5. user_tokens    = len(last_user["content"]) // 4
6. useful         = system_tokens + user_tokens
7. tail_msgs      = all messages except system + last_user
8. tail_tokens    = sum(len(m["content"]) // 4 for m in tail_msgs)
9. if tail_tokens <= 0.3 * useful: skip
10. summary = await _call_summarizer(tail_msgs)  # direct DeepSeek call, no Lineman
11. Replace tail_msgs with single {"role":"user","content":"[Context summary]: {summary}"}
12. json.dumps → new req_body
13. fwd_headers["content-length"] = str(len(new_req_body))
```

### `_call_summarizer`
- Direct HTTP POST to `https://api.deepseek.com/v1/chat/completions` via iProyal
- Model: `deepseek-chat` (cheapest)
- Timeout: 8s -- on any error, return original body unchanged (silent fallback)
- Prompt: `"Summarize this conversation in 5 bullet points. Preserve: decisions made, tool results, unresolved questions, key facts. Be terse."`
- Target output: ~150–200 tokens

### Content handling
- String content: `len(content) // 4`
- List content (multimodal blocks): sum text blocks only
- Non-messages requests (embed, image): skip entirely (no `messages` key)

### Logging additions to DB row
```python
"compression_applied": 1 if compressed else 0,
"tail_tokens_before": tail_tokens,
"tail_tokens_after":  summary_tokens if compressed else tail_tokens,
```
Requires adding these columns to `request_log` schema + censor_exporter query.

### CONNECT tunnel guard
Add to `handle_tunnel` in `_http_raw.py`: if `llm_provider_from_host(host) is not None`, emit `logger.warning("llm_via_connect_tunnel", host=host)` and write a DB row flagging it. Current traffic shows 0 OpenClaw LLM calls via CONNECT (all use `/proxy/`), so this is a safety net only.

---

## Component 2: System Prompt Rewriting

### `main` agent (`/home/shectory/`)

**AGENTS.md: 308 → ~90 lines**

| Section | Current | Action |
|---------|---------|--------|
| Google Drive sync | 50 lines | Compress to 5 lines (rule + 2 commands) |
| Heartbeat detail | 75 lines | Strip to 3 lines, move detail to HEARTBEAT.md |
| Group chat rules | 28 lines | Keep 6 core rules, cut examples |
| Memory maintenance | 30 lines | Cut to 4 lines |
| React like human | 15 lines | Cut to 2 lines |
| Red lines / external | 15 lines | Keep, already compact |
| Session startup | 20 lines | Cut to 8 lines |

**Add to every agent AGENTS.md (anti-flood block, ~8 lines):**
```markdown
## Limits
- Max 3 tool calls per turn. If stuck: stop, report to Boris.
- Never repeat identical tool call twice in a row.
- On LLM error: report once, do not retry.
- Responses: terse, no filler.
```

**TOOLS.md: 97 → ~40 lines** -- remove inline code examples, keep command names + one-line descriptions only.

**SOUL.md: 47 → 25 lines** -- strip repeated phrases, keep personality core.

**USER.md: 48 lines** -- do not touch (personal context, dense by design).

**MEMORY.md: 160 lines** -- do not touch (curated memory, not injected every turn in non-main sessions).

### Other 11 agents

Per-agent target: AGENTS.md trim 30-40%, add anti-flood block. Priority order by session_tokens from Censor:

| Agent | AGENTS.md now | Target |
|-------|--------------|--------|
| main | 308 | 90 |
| keymaster | 67 | 45 |
| titan | 75 | 50 |
| qaper | 63 | 42 |
| selfcoder | 52 | 35 |
| virtual-boris | 43 | 30 |
| inbox | 41 | 28 |
| guilya | 37 | 25 |
| nurse | ~40 | 28 |
| interview-coach | ~40 | 28 |
| jobsearch-scanner | ~40 | 28 |
| resume-editor | ~40 | 28 |

---

## What We Are NOT Doing

- TLS interception of CONNECT tunnels (not needed -- OpenClaw uses /proxy/ already)
- Parking CONNECT entirely (Telegram API needs it)
- Modifying OpenClaw source code
- Touching USER.md or MEMORY.md (dense by design, personal)

---

## Testing / Acceptance

1. **Middleware**: After deploy, check `censor/reports/` next 30-min window. `tail_tokens_after / tail_tokens_before` should be < 0.3 for triggered requests.
2. **Prompts**: After restart, next censor report should show `session_tokens_in` drop for smain agents. Target: smain session stays < 50k tokens per 30-min window.
3. **Retry rate**: `hoster:?` retry rate target < 20% (from current 80%).

---

## Files Changed

**Lineman:**
- `reverse_proxy.py` -- add `summarise_addendums`, `_call_summarizer`, CONNECT guard
- `_http_raw.py` -- add CONNECT LLM warning
- `db.py` -- add 3 schema columns
- `censor_exporter.py` -- read new columns

**Agent workspaces (smain):**
- `/home/shectory/AGENTS.md`
- `/home/shectory/TOOLS.md`
- `/home/shectory/SOUL.md`
- `/home/shectory/HEARTBEAT.md`
- `/home/shectory/workspaces/*/AGENTS.md` (11 agents)
