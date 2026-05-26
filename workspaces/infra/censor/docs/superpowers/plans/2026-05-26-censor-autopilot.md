# Censor Autopilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Autonomous anomaly detection → Opus root-cause → patch config files → git commit → Telegram alert.

**Architecture:** `censor_watchdog.py` (cron */10) reads last 10 min JSONL, triggers `censor_investigator.py` on threshold breach, which calls Claude Opus, then `patch_applier.py` applies JSON patches and commits. `censor_analyzer.py` keeps running as 6h summary.

**Tech Stack:** Python 3, sqlite3, subprocess (claude CLI), urllib (no extra deps), pytest, git, pm2

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `censor_analyzer.py` | Modify | Change WINDOW_MINUTES 30→360, update system prompt |
| `censor_watchdog.py` | Create | 10-min cron, threshold check, dedup, spawn investigator |
| `censor_investigator.py` | Create | Evidence collection, Opus call, call patch_applier |
| `patch_applier.py` | Create | Apply patches, backup, git commit, Telegram |
| `tests/test_watchdog.py` | Create | Unit tests for metrics + threshold logic |
| `tests/test_investigator.py` | Create | Unit tests for DB query, config redaction, prompt build |
| `tests/test_patch_applier.py` | Create | Unit tests for patch application, backup, rollback |
| `active_investigations.json` | Runtime | Dedup state (created by watchdog at runtime) |
| `~/logs/censor/fixes.jsonl` | Runtime | Fix KPI log (created by patch_applier at runtime) |

All files live at `~/workspaces/infra/censor/` on smain.
Run tests: `ssh smain "cd ~/workspaces/infra/censor && python3 -m pytest tests/ -v"`

---

### Task 1: Modify censor_analyzer.py

**Files:**
- Modify: `~/workspaces/infra/censor/censor_analyzer.py`

- [ ] **Step 1: Change WINDOW_MINUTES and system prompt**

In `censor_analyzer.py`:
- Line `WINDOW_MINUTES = 30` → `WINDOW_MINUTES = 360`
- In `SYSTEM_PROMPT` replace `"за 30 минут"` → `"за 6 часов"` and `"30 minutes"` → `"6h"`
- In `build_tg_digest` the f-string already uses `WINDOW_MINUTES` so it auto-updates

- [ ] **Step 2: Verify change**

```bash
ssh smain "grep -n 'WINDOW_MINUTES\|30 минут\|30 min' ~/workspaces/infra/censor/censor_analyzer.py"
```
Expected: only `WINDOW_MINUTES = 360`

- [ ] **Step 3: Commit**

```bash
ssh smain "cd ~ && git add workspaces/infra/censor/censor_analyzer.py && git commit -m 'feat(censor): extend analyzer window 30m→6h, cron will be updated in Task 5'"
```

---

### Task 2: censor_watchdog.py (TDD)

**Files:**
- Create: `~/workspaces/infra/censor/tests/test_watchdog.py`
- Create: `~/workspaces/infra/censor/censor_watchdog.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_watchdog.py`:

```python
"""Tests for censor_watchdog — metrics computation and threshold detection."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from censor_watchdog import compute_metrics, check_thresholds, is_recent, load_active

from datetime import datetime, timezone, timedelta


SAMPLE_ROWS = [
    {"source_host": "smain", "source_agent": "main", "retry_score": 1.0, "error": None, "tokens_in": 18000, "session_tokens_in": 18000},
    {"source_host": "smain", "source_agent": "main", "retry_score": 1.0, "error": None, "tokens_in": 18000, "session_tokens_in": 36000},
    {"source_host": "smain", "source_agent": "main", "retry_score": 0.95, "error": None, "tokens_in": 18000, "session_tokens_in": 54000},
    {"source_host": "smain", "source_agent": "main", "retry_score": 0.0, "error": "timeout", "tokens_in": 500, "session_tokens_in": 54500},
    {"source_host": "sdev", "source_agent": "coder", "retry_score": 0.0, "error": None, "tokens_in": 5000, "session_tokens_in": 5000},
]


def test_compute_metrics_retry_rate():
    metrics = compute_metrics(SAMPLE_ROWS)
    m = metrics["smain:main"]
    # 3 out of 4 have retry_score >= 0.85
    assert m["retry_rate"] == 0.75


def test_compute_metrics_error_rate():
    metrics = compute_metrics(SAMPLE_ROWS)
    m = metrics["smain:main"]
    assert m["error_rate"] == 0.25


def test_compute_metrics_tokens_in():
    metrics = compute_metrics(SAMPLE_ROWS)
    assert metrics["smain:main"]["tokens_in"] == 18000 * 3 + 500


def test_compute_metrics_clean_agent():
    metrics = compute_metrics(SAMPLE_ROWS)
    m = metrics["sdev:coder"]
    assert m["retry_rate"] == 0.0
    assert m["error_rate"] == 0.0


def test_check_thresholds_retry_triggers():
    metrics = {"smain:main": {"retry_rate": 0.76, "error_rate": 0.0, "tokens_in": 100, "max_session_tokens": 0}}
    assert "smain:main" in check_thresholds(metrics)


def test_check_thresholds_tokens_triggers():
    metrics = {"smain:main": {"retry_rate": 0.0, "error_rate": 0.0, "tokens_in": 900_000, "max_session_tokens": 0}}
    assert "smain:main" in check_thresholds(metrics)


def test_check_thresholds_session_triggers():
    metrics = {"smain:main": {"retry_rate": 0.0, "error_rate": 0.0, "tokens_in": 100, "max_session_tokens": 250_000}}
    assert "smain:main" in check_thresholds(metrics)


def test_check_thresholds_clean_passes():
    metrics = {"sdev:coder": {"retry_rate": 0.1, "error_rate": 0.0, "tokens_in": 5000, "max_session_tokens": 10000}}
    assert check_thresholds(metrics) == []


def test_is_recent_fresh():
    ts = datetime.now(timezone.utc).isoformat()
    assert is_recent(ts, minutes=30) is True


def test_is_recent_stale():
    ts = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
    assert is_recent(ts, minutes=30) is False


def test_load_active_missing(tmp_path, monkeypatch):
    import censor_watchdog
    monkeypatch.setattr(censor_watchdog, "ACTIVE_INVESTIGATIONS", tmp_path / "active.json")
    assert load_active() == {}
```

- [ ] **Step 2: Run to verify FAIL**

```bash
ssh smain "cd ~/workspaces/infra/censor && python3 -m pytest tests/test_watchdog.py -v 2>&1 | head -20"
```
Expected: `ModuleNotFoundError: No module named 'censor_watchdog'`

- [ ] **Step 3: Implement censor_watchdog.py**

Create `~/workspaces/infra/censor/censor_watchdog.py`:

```python
"""
censor_watchdog.py — fast anomaly detector, cron */10 * * * *.
Reads last 10 min of JSONL, computes per-agent metrics.
Triggers censor_investigator.py if any threshold exceeded.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOG_DIR = Path.home() / "logs" / "censor"
CENSOR_DIR = Path(__file__).resolve().parent
ACTIVE_INVESTIGATIONS = CENSOR_DIR / "active_investigations.json"
INVESTIGATOR = CENSOR_DIR / "censor_investigator.py"

WINDOW_MINUTES = 10
DEDUP_MINUTES = 30
RETRY_SCORE_THRESH = 0.85   # row is a retry if retry_score >= this
RETRY_RATE_THRESH = 0.50
SESSION_TOKENS_THRESH = 200_000
ERROR_RATE_THRESH = 0.25
TOKENS_IN_THRESH = 800_000


def load_active() -> dict:
    if ACTIVE_INVESTIGATIONS.exists():
        try:
            return json.loads(ACTIVE_INVESTIGATIONS.read_text())
        except Exception:
            pass
    return {}


def save_active(data: dict) -> None:
    ACTIVE_INVESTIGATIONS.write_text(json.dumps(data, indent=2))


def is_recent(ts_str: str, minutes: int = DEDUP_MINUTES) -> bool:
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() < minutes * 60
    except Exception:
        return False


def load_recent_rows(since: datetime) -> list[dict]:
    rows = []
    dates = {since.strftime("%Y-%m-%d"), datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    for date in sorted(dates):
        path = LOG_DIR / f"{date}.jsonl"
        if not path.exists():
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if row.get("timestamp", "") >= since.isoformat():
                        rows.append(row)
                except Exception:
                    pass
    return rows


def compute_metrics(rows: list[dict]) -> dict[str, dict]:
    agents: dict[str, dict] = defaultdict(lambda: {
        "requests": 0, "retries": 0, "errors": 0,
        "tokens_in": 0, "max_session_tokens": 0,
    })
    for r in rows:
        key = f"{r.get('source_host') or '?'}:{r.get('source_agent') or '?'}"
        a = agents[key]
        a["requests"] += 1
        if (r.get("retry_score") or 0) >= RETRY_SCORE_THRESH:
            a["retries"] += 1
        if r.get("error"):
            a["errors"] += 1
        a["tokens_in"] += r.get("tokens_in") or 0
        sess = r.get("session_tokens_in") or 0
        if sess > a["max_session_tokens"]:
            a["max_session_tokens"] = sess
    result = {}
    for key, a in agents.items():
        n = a["requests"]
        result[key] = {
            "requests": n,
            "retry_rate": round(a["retries"] / n, 3) if n else 0.0,
            "error_rate": round(a["errors"] / n, 3) if n else 0.0,
            "tokens_in": a["tokens_in"],
            "max_session_tokens": a["max_session_tokens"],
        }
    return result


def check_thresholds(metrics: dict) -> list[str]:
    triggered = []
    for agent, m in metrics.items():
        if (
            m["retry_rate"] > RETRY_RATE_THRESH
            or m["max_session_tokens"] > SESSION_TOKENS_THRESH
            or m["error_rate"] > ERROR_RATE_THRESH
            or m["tokens_in"] > TOKENS_IN_THRESH
        ):
            triggered.append(agent)
    return triggered


def main() -> None:
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=WINDOW_MINUTES)
    rows = load_recent_rows(since)
    if not rows:
        return
    metrics = compute_metrics(rows)
    triggered = check_thresholds(metrics)
    if not triggered:
        return
    active = load_active()
    active = {k: v for k, v in active.items() if is_recent(v)}
    new_active = dict(active)
    for agent in triggered:
        if agent in active:
            print(f"[watchdog] skip {agent}: active investigation <{DEDUP_MINUTES}min", file=sys.stderr)
            continue
        m = metrics[agent]
        print(f"[watchdog] ANOMALY {agent}: retry={m['retry_rate']:.0%} err={m['error_rate']:.0%} tok={m['tokens_in']:,} sess={m['max_session_tokens']:,}")
        new_active[agent] = now.isoformat()
        subprocess.Popen([sys.executable, str(INVESTIGATOR), "--agent", agent, "--since", since.isoformat()])
    save_active(new_active)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
ssh smain "cd ~/workspaces/infra/censor && python3 -m pytest tests/test_watchdog.py -v"
```
Expected: all 11 tests PASS

- [ ] **Step 5: Commit**

```bash
ssh smain "cd ~ && git add workspaces/infra/censor/censor_watchdog.py workspaces/infra/censor/tests/test_watchdog.py && git commit -m 'feat(censor): add censor_watchdog with threshold detection'"
```

---

### Task 3: censor_investigator.py (TDD)

**Files:**
- Create: `~/workspaces/infra/censor/tests/test_investigator.py`
- Create: `~/workspaces/infra/censor/censor_investigator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_investigator.py`:

```python
"""Tests for censor_investigator — redaction, prompt build, response parsing."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from censor_investigator import redact_keys, parse_opus_response, build_opus_prompt


def test_redact_keys_api_key():
    d = {"model": "gpt-4", "key": "sk-abc123", "name": "main"}
    result = redact_keys(d)
    assert result["key"] == "[REDACTED]"
    assert result["model"] == "gpt-4"
    assert result["name"] == "main"


def test_redact_keys_nested():
    d = {"profiles": {"default": {"key": "sk-secret", "url": "https://api.example.com"}}}
    result = redact_keys(d)
    assert result["profiles"]["default"]["key"] == "[REDACTED]"
    assert result["profiles"]["default"]["url"] == "https://api.example.com"


def test_redact_keys_token_field():
    d = {"token": "abc", "data": "ok"}
    result = redact_keys(d)
    assert result["token"] == "[REDACTED]"


def test_parse_opus_response_valid():
    raw = json.dumps({
        "root_cause": "Agent stuck in retry loop",
        "severity": "critical",
        "patches": [{"file": "/tmp/x.json", "description": "fix", "type": "json_key", "old": "null", "new": "15"}],
        "restart_pm2": [],
        "expected_improvement": "retry 76% → <5%",
    })
    result = parse_opus_response(raw)
    assert result["severity"] == "critical"
    assert len(result["patches"]) == 1


def test_parse_opus_response_with_fences():
    raw = "```json\n" + json.dumps({"root_cause": "x", "severity": "high", "patches": [], "restart_pm2": [], "expected_improvement": "y"}) + "\n```"
    result = parse_opus_response(raw)
    assert result["root_cause"] == "x"


def test_parse_opus_response_invalid():
    result = parse_opus_response("not json at all")
    assert result is None


def test_build_opus_prompt_contains_agent():
    bodies = [
        {"id": 1, "timestamp": "2026-05-26T07:00:00Z", "tokens_in": 18000, "request_size": 69000, "status_code": 200, "error": None, "request_body": "test body"},
    ]
    configs = {"openclaw.json": '{"gateway": {"port": 18789}}'}
    prompt = build_opus_prompt("smain:main", "2026-05-26T07:00:00Z", bodies, configs)
    assert "smain:main" in prompt
    assert "2026-05-26T07:00:00Z" in prompt
    assert "openclaw.json" in prompt


def test_build_opus_prompt_identical_bodies_detected():
    bodies = [
        {"id": 1, "timestamp": "2026-05-26T07:00:00Z", "tokens_in": 18000, "request_size": 69000, "status_code": 200, "error": None, "request_body": "same body"},
        {"id": 2, "timestamp": "2026-05-26T07:01:00Z", "tokens_in": 18000, "request_size": 69000, "status_code": 200, "error": None, "request_body": "same body"},
    ]
    configs = {}
    prompt = build_opus_prompt("smain:main", "2026-05-26T07:00:00Z", bodies, configs)
    assert "IDENTICAL" in prompt
```

- [ ] **Step 2: Run to verify FAIL**

```bash
ssh smain "cd ~/workspaces/infra/censor && python3 -m pytest tests/test_investigator.py -v 2>&1 | head -10"
```
Expected: `ModuleNotFoundError: No module named 'censor_investigator'`

- [ ] **Step 3: Implement censor_investigator.py**

Create `~/workspaces/infra/censor/censor_investigator.py`:

```python
"""
censor_investigator.py — evidence collector + Opus root-cause analyst.
Called by watchdog: python3 censor_investigator.py --agent <key> --since <iso-ts>
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CENSOR_DIR = Path(__file__).resolve().parent
LINEMAN_DB = CENSOR_DIR.parent / "lineman" / "lineman.db"
PATCH_APPLIER = CENSOR_DIR / "patch_applier.py"
FIXES_LOG = Path.home() / "logs" / "censor" / "fixes.jsonl"

BORIS_CHAT_ID = "36910539"
LINEMAN_TG_URL = "http://localhost:9090/api/tg/send"
CLAUDE_BIN = "/usr/bin/claude"
MAX_BODY_SAMPLES = 20
_KEY_PATTERNS = {"key", "secret", "token", "password", "apikey", "api_key"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agent", required=True)
    p.add_argument("--since", required=True)
    return p.parse_args()


def redact_keys(obj, depth: int = 0):
    if depth > 20:
        return obj
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if any(p in k.lower() for p in _KEY_PATTERNS) else redact_keys(v, depth + 1)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact_keys(i, depth + 1) for i in obj]
    return obj


def read_config_safe(path: Path) -> str:
    if not path.exists():
        return f"[not found: {path}]"
    try:
        text = path.read_text()
    except Exception as exc:
        return f"[read error: {exc}]"
    if path.suffix == ".json":
        try:
            text = json.dumps(redact_keys(json.loads(text)), indent=2)
        except Exception:
            pass
    return text


def fetch_request_bodies(agent_key: str, since_ts: str) -> list[dict]:
    host, _, agent = agent_key.partition(":")
    try:
        conn = sqlite3.connect(str(LINEMAN_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, timestamp, tokens_in, tokens_out, status_code, error,
                   request_body, request_size, latency_ms
            FROM request_log
            WHERE source_host = ? AND source_agent = ? AND timestamp >= ?
            ORDER BY id DESC LIMIT ?
            """,
            (host, agent, since_ts, MAX_BODY_SAMPLES),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as exc:
        print(f"[investigator] DB error: {exc}", file=sys.stderr)
        return []


def collect_configs() -> dict[str, str]:
    home = Path.home()
    openclaw = home / ".openclaw"
    configs: dict[str, str] = {}
    configs["openclaw.json"] = read_config_safe(openclaw / "openclaw.json")
    agents_dir = openclaw / "agents"
    if agents_dir.exists():
        for agent_dir in sorted(agents_dir.iterdir()):
            agent_subdir = agent_dir / "agent"
            for fname in ["config.json", "system-prompt.md", "auth-profiles.json"]:
                fpath = agent_subdir / fname
                if fpath.exists():
                    configs[f"agents/{agent_dir.name}/agent/{fname}"] = read_config_safe(fpath)
    configs["lineman/config.json"] = read_config_safe(
        home / "workspaces" / "infra" / "lineman" / "config.json"
    )
    configs[".pm2/dump.pm2"] = read_config_safe(home / ".pm2" / "dump.pm2")
    return configs


def build_opus_prompt(agent_key: str, since_ts: str, bodies: list[dict], configs: dict[str, str]) -> str:
    samples = []
    for i, b in enumerate(bodies[:5]):
        body_preview = (b.get("request_body") or "")[:2000]
        samples.append(
            f"Request {i+1} (id={b['id']}, ts={b['timestamp']}, "
            f"tokens_in={b['tokens_in']}, size={b['request_size']}, "
            f"status={b['status_code']}, error={b['error']}):\n{body_preview}"
        )

    diff_section = ""
    if len(bodies) >= 2:
        first = bodies[-1].get("request_body") or ""
        last = bodies[0].get("request_body") or ""
        if first == last:
            diff_section = "First and last request bodies are IDENTICAL (strong retry indicator)."
        else:
            diff_section = f"First body (oldest):\n{first[:500]}\n\nLast body (newest):\n{last[:500]}"

    configs_text = "\n\n".join(
        f"=== {k} ===\n{v[:3000]}" for k, v in list(configs.items())[:12]
    )

    return f"""You are an LLM agent anomaly analyst. Agent "{agent_key}" triggered anomaly detection at {since_ts}.

ANOMALY EVIDENCE ({len(bodies)} samples):
{"".join(samples)}

BODY COMPARISON:
{diff_section}

SYSTEM CONFIGS:
{configs_text}

Identify the root cause. Respond with ONLY valid JSON (no markdown fences):
{{
  "root_cause": "1-3 sentences explaining the anomaly cause",
  "severity": "critical|high|medium",
  "patches": [
    {{
      "file": "/absolute/path/to/file",
      "description": "what and why",
      "type": "json_key|text_replace|file_append",
      "old": "exact current value",
      "new": "exact replacement value"
    }}
  ],
  "restart_pm2": ["process-name-if-needed"],
  "expected_improvement": "e.g. retry_rate 76% -> <5%"
}}
If no safe clear fix exists, return patches: []. Only reference files visible in SYSTEM CONFIGS above."""


def call_opus(prompt: str) -> str:
    result = subprocess.run(
        [CLAUDE_BIN, "--model", "claude-opus-4-7", "--print", "--bare"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "CLAUDE_CODE_SIMPLE": "1"},
    )
    if result.returncode != 0:
        print(f"[investigator] claude stderr: {result.stderr[:300]}", file=sys.stderr)
    return result.stdout.strip()


def parse_opus_response(text: str) -> dict | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        cleaned = "\n".join(lines[1:end])
    try:
        return json.loads(cleaned)
    except Exception as exc:
        print(f"[investigator] JSON parse error: {exc}\nRaw: {text[:300]}", file=sys.stderr)
        return None


def send_tg(text: str) -> None:
    payload = json.dumps({"chat_id": BORIS_CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(
        LINEMAN_TG_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:
        print(f"[investigator] TG failed: {exc}", file=sys.stderr)


def main() -> None:
    args = parse_args()
    print(f"[investigator] {args.agent} since {args.since}")

    bodies = fetch_request_bodies(args.agent, args.since)
    print(f"[investigator] {len(bodies)} bodies, collecting configs...")
    configs = collect_configs()

    prompt = build_opus_prompt(args.agent, args.since, bodies, configs)
    print("[investigator] calling Opus...")
    raw = call_opus(prompt)
    analysis = parse_opus_response(raw)

    if not analysis:
        send_tg(f"[Autopilot] Аномалия: {args.agent}\nOpus вернул невалидный JSON. Ручной разбор нужен.\n{raw[:200]}")
        return

    patches = analysis.get("patches", [])
    if not patches:
        send_tg(
            f"[Autopilot] Аномалия: {args.agent}\n"
            f"Opus: {analysis.get('root_cause', '?')}\n"
            f"Автофикс не применён — причина неоднозначна.\n"
            f"Требует ручного разбора: ~/logs/censor/reports/"
        )
        return

    result = subprocess.run(
        [sys.executable, str(PATCH_APPLIER)],
        input=json.dumps({"agent": args.agent, "since": args.since, "analysis": analysis}),
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f"[investigator] patch_applier failed: {result.stderr}", file=sys.stderr)
        send_tg(
            f"[Autopilot] Аномалия: {args.agent}\n"
            f"Root cause: {analysis.get('root_cause')}\n"
            f"Patch_applier упал: {result.stderr[:200]}"
        )
    else:
        print(f"[investigator] done: {result.stdout.strip()}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
ssh smain "cd ~/workspaces/infra/censor && python3 -m pytest tests/test_investigator.py -v"
```
Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
ssh smain "cd ~ && git add workspaces/infra/censor/censor_investigator.py workspaces/infra/censor/tests/test_investigator.py && git commit -m 'feat(censor): add censor_investigator with Opus root-cause analysis'"
```

---

### Task 4: patch_applier.py (TDD)

**Files:**
- Create: `~/workspaces/infra/censor/tests/test_patch_applier.py`
- Create: `~/workspaces/infra/censor/patch_applier.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_patch_applier.py`:

```python
"""Tests for patch_applier — json_key, text_replace, file_append, rollback."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from patch_applier import apply_json_key, apply_text_replace, apply_file_append, backup_file, replace_in_dict


def test_replace_in_dict_top_level():
    d = {"max_iterations": None, "model": "gpt-4"}
    assert replace_in_dict(d, "None", "15") is True
    assert d["max_iterations"] == "15"


def test_replace_in_dict_nested():
    d = {"settings": {"tool_error_exit": False}}
    assert replace_in_dict(d, "False", True) is True
    assert d["settings"]["tool_error_exit"] is True


def test_replace_in_dict_not_found():
    d = {"key": "value"}
    assert replace_in_dict(d, "missing", "x") is False


def test_apply_json_key(tmp_path):
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"max_iterations": None, "model": "deepseek"}))
    apply_json_key(f, "None", 15)
    d = json.loads(f.read_text())
    assert d["max_iterations"] == 15


def test_apply_json_key_not_found_raises(tmp_path):
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"key": "value"}))
    try:
        apply_json_key(f, "nonexistent", "new")
        assert False, "should raise"
    except ValueError:
        pass


def test_apply_text_replace(tmp_path):
    f = tmp_path / "prompt.md"
    f.write_text("You are a helpful assistant. Call tool X always.")
    apply_text_replace(f, "Call tool X always.", "Use tool X when needed.")
    assert "Use tool X when needed." in f.read_text()


def test_apply_text_replace_not_found_raises(tmp_path):
    f = tmp_path / "prompt.md"
    f.write_text("hello world")
    try:
        apply_text_replace(f, "missing string", "new")
        assert False, "should raise"
    except ValueError:
        pass


def test_apply_file_append(tmp_path):
    f = tmp_path / "config.txt"
    f.write_text("existing content\n")
    apply_file_append(f, "new line")
    assert f.read_text().endswith("new line\n")


def test_backup_file(tmp_path):
    f = tmp_path / "config.json"
    f.write_text('{"key": "value"}')
    backup = backup_file(f, "20260526T070000")
    assert backup.exists()
    assert backup.read_text() == '{"key": "value"}'
    assert "censor-backup-20260526T070000" in backup.name


def test_json_rollback_on_invalid(tmp_path):
    """If json_key patch produces invalid JSON, file is restored."""
    f = tmp_path / "config.json"
    original = '{"max_iterations": null}'
    f.write_text(original)
    # apply_json_key replaces value by str match; test that backup works
    backup = backup_file(f, "ts")
    f.write_text("not valid json {{{")
    try:
        json.loads(f.read_text())
    except Exception:
        import shutil
        shutil.copy2(backup, f)
    assert f.read_text() == original
```

- [ ] **Step 2: Run to verify FAIL**

```bash
ssh smain "cd ~/workspaces/infra/censor && python3 -m pytest tests/test_patch_applier.py -v 2>&1 | head -10"
```
Expected: `ModuleNotFoundError: No module named 'patch_applier'`

- [ ] **Step 3: Implement patch_applier.py**

Create `~/workspaces/infra/censor/patch_applier.py`:

```python
"""
patch_applier.py — reads investigation JSON from stdin, applies patches, commits, notifies.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FIXES_LOG = Path.home() / "logs" / "censor" / "fixes.jsonl"
REPO_DIR = Path.home()
BORIS_CHAT_ID = "36910539"
LINEMAN_TG_URL = "http://localhost:9090/api/tg/send"
PM2_BIN = "/home/shectory/.npm/_npx/5f7878ce38f1eb13/node_modules/pm2/bin/pm2"


def send_tg(text: str) -> None:
    payload = json.dumps({"chat_id": BORIS_CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(
        LINEMAN_TG_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:
        print(f"[patch_applier] TG failed: {exc}", file=sys.stderr)


def backup_file(path: Path, ts: str) -> Path:
    backup = Path(f"{path}.censor-backup-{ts}")
    shutil.copy2(path, backup)
    return backup


def replace_in_dict(obj, old_val, new_val) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(v) == str(old_val):
                obj[k] = new_val
                return True
            if isinstance(v, (dict, list)) and replace_in_dict(v, old_val, new_val):
                return True
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if str(item) == str(old_val):
                obj[i] = new_val
                return True
            if isinstance(item, (dict, list)) and replace_in_dict(item, old_val, new_val):
                return True
    return False


def apply_json_key(path: Path, old_val, new_val) -> None:
    text = path.read_text()
    d = json.loads(text)
    if not replace_in_dict(d, old_val, new_val):
        raise ValueError(f"Value '{old_val}' not found in {path}")
    path.write_text(json.dumps(d, indent=2, ensure_ascii=False))


def apply_text_replace(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if old not in text:
        raise ValueError(f"String '{old[:50]}' not found in {path}")
    path.write_text(text.replace(old, new, 1))


def apply_file_append(path: Path, content: str) -> None:
    with open(path, "a") as f:
        f.write(content if content.endswith("\n") else content + "\n")


def apply_patch(patch: dict, ts: str) -> Path:
    fpath = Path(patch["file"])
    if not fpath.exists():
        raise FileNotFoundError(f"Patch target not found: {fpath}")
    backup = backup_file(fpath, ts)
    ptype = patch["type"]
    old = patch.get("old", "")
    new = patch.get("new", "")
    try:
        if ptype == "json_key":
            apply_json_key(fpath, old, new)
            json.loads(fpath.read_text())  # validate
        elif ptype == "text_replace":
            apply_text_replace(fpath, old, new)
        elif ptype == "file_append":
            apply_file_append(fpath, new)
        else:
            raise ValueError(f"Unknown patch type: {ptype}")
    except Exception:
        shutil.copy2(backup, fpath)
        backup.unlink(missing_ok=True)
        raise
    return fpath


def git_commit(files: list[Path], agent: str, root_cause: str, expected: str) -> str:
    short = root_cause[:60].replace("\n", " ")
    msg = f"censor-autopilot: fix {agent} — {short}\n\nExpected: {expected}"
    for f in files:
        subprocess.run(["git", "-C", str(REPO_DIR), "add", str(f)], check=True)
    result = subprocess.run(
        ["git", "-C", str(REPO_DIR), "commit", "-m", msg],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git commit failed: {result.stderr}")
    h = subprocess.run(
        ["git", "-C", str(REPO_DIR), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    )
    return h.stdout.strip()


def restart_pm2(processes: list[str]) -> None:
    for name in processes:
        result = subprocess.run([PM2_BIN, "restart", name], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[patch_applier] pm2 restart {name} failed: {result.stderr}", file=sys.stderr)


def log_fix(entry: dict) -> None:
    FIXES_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(FIXES_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    data = json.loads(sys.stdin.read())
    agent = data["agent"]
    since = data["since"]
    analysis = data["analysis"]
    patches = analysis.get("patches", [])
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    changed_files: list[Path] = []
    for patch in patches:
        try:
            changed_files.append(apply_patch(patch, ts))
            print(f"[patch_applier] patched {patch['file']}")
        except Exception as exc:
            print(f"[patch_applier] patch failed: {exc}", file=sys.stderr)

    if not changed_files:
        send_tg(
            f"[Autopilot] Аномалия: {agent}\n"
            f"Root cause: {analysis.get('root_cause')}\n"
            f"Все патчи провалились."
        )
        return

    commit = ""
    try:
        commit = git_commit(changed_files, agent, analysis.get("root_cause", ""), analysis.get("expected_improvement", ""))
    except Exception as exc:
        print(f"[patch_applier] git commit failed: {exc}", file=sys.stderr)

    restart_pm2(analysis.get("restart_pm2", []))

    log_fix({
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent, "since": since,
        "root_cause": analysis.get("root_cause"),
        "severity": analysis.get("severity"),
        "patches_applied": len(changed_files),
        "files_changed": [str(f) for f in changed_files],
        "commit": commit,
        "metrics_before": None, "metrics_after": None,
        "expected_improvement": analysis.get("expected_improvement"),
    })

    patch_lines = "".join(f"  {p['file']}\n    {p.get('old','')} → {p.get('new','')}\n" for p in patches)
    send_tg(
        f"[Autopilot] Аномалия: {agent}\n"
        f"Root cause: {analysis.get('root_cause', '?')}\n"
        f"Исправил:\n{patch_lines}"
        f"Коммит: {commit}\n"
        f"Ожидаемо: {analysis.get('expected_improvement', '?')}"
    )
    print(f"[patch_applier] done. commit={commit}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
ssh smain "cd ~/workspaces/infra/censor && python3 -m pytest tests/test_patch_applier.py -v"
```
Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
ssh smain "cd ~ && git add workspaces/infra/censor/patch_applier.py workspaces/infra/censor/tests/test_patch_applier.py && git commit -m 'feat(censor): add patch_applier with backup, rollback, git commit, Telegram'"
```

---

### Task 5: Update crontab

**Files:** crontab on smain (shectory user)

- [ ] **Step 1: Update crontab**

```bash
ssh smain "crontab -l | grep -v 'censor_analyzer\|censor_watchdog' > /tmp/crontab_new.txt && echo '0 */6 * * * /usr/bin/python3 ~/workspaces/infra/censor/censor_analyzer.py >> ~/logs/censor/analyzer.log 2>&1' >> /tmp/crontab_new.txt && echo '*/10 * * * * /usr/bin/python3 ~/workspaces/infra/censor/censor_watchdog.py >> ~/logs/censor/watchdog.log 2>&1' >> /tmp/crontab_new.txt && crontab /tmp/crontab_new.txt && crontab -l"
```
Expected: two censor lines visible, old `*/30` gone.

- [ ] **Step 2: Commit plan + docs**

```bash
ssh smain "cd ~ && git add workspaces/infra/censor/docs/ && git commit -m 'docs(censor): add autopilot implementation plan'"
```

---

### Task 6: Integration test + Telegram notification

- [ ] **Step 1: Run all tests**

```bash
ssh smain "cd ~/workspaces/infra/censor && python3 -m pytest tests/ -v"
```
Expected: all tests PASS

- [ ] **Step 2: Dry-run watchdog against 2026-05-26 anomaly data**

```bash
ssh smain "cd ~/workspaces/infra/censor && python3 -c \"
import json
from censor_watchdog import compute_metrics, check_thresholds, load_recent_rows
from datetime import datetime, timezone
rows = load_recent_rows(datetime.fromisoformat('2026-05-26T07:00:00+00:00'))
print('rows:', len(rows))
m = compute_metrics(rows)
for k, v in m.items():
    print(k, v)
print('triggered:', check_thresholds(m))
\""
```

- [ ] **Step 3: Send completion notification to Telegram**

```bash
ssh smain "curl -s -X POST http://localhost:9090/api/tg/send \
  -H 'Content-Type: application/json' \
  -d '{\"chat_id\":\"36910539\",\"text\":\"Censor Autopilot готов!\n\nЧто сделано:\n✓ censor_watchdog.py (cron */10) — порог: retry>50%, sess>200K, err>25%, tok>800K\n✓ censor_investigator.py — сбор доказательств + Opus root-cause\n✓ patch_applier.py — патчинг + git commit + backup\n✓ censor_analyzer.py — окно 30m→6h\n✓ Все тесты зелёные\n✓ Crontab обновлён\"  }'"
```
